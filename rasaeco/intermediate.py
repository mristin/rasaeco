"""Render the scenarios to the intermediate representation as XML files."""
import itertools
import json
import pathlib
import xml.etree.ElementTree as ET
from typing import List, Optional, MutableMapping, Set, Tuple, Protocol

import icontract
import marko

import rasaeco.et
import rasaeco.meta
import rasaeco.model


def as_xml_path(scenario_path: pathlib.Path) -> pathlib.Path:
    """Generate the corresponding XML path of the intermediate representation."""
    return scenario_path.parent / (scenario_path.stem + ".xml")


def _verify_all_tags_closed(xml_text: str) -> Optional[str]:
    """
    Verify that all the tags were properly closed in the XML given as text.

    Return error if any.
    """
    parser = ET.XMLPullParser(["start", "end"])
    parser.feed(xml_text.encode("utf-8"))

    open_tags = []  # type: List[ET.Element]

    iterator = parser.read_events()
    while True:
        try:
            event, element = next(iterator)
        except StopIteration:
            break
        except ET.ParseError as exception:
            lineno, _ = exception.position
            line = xml_text.splitlines()[lineno - 1]

            if exception.msg.startswith("mismatched tag:"):
                return (
                    f"{exception.msg}; the line was: {line!r}, "
                    f"the open tag(s) up to that point: "
                    f"{list(map(rasaeco.et.to_str, open_tags))}. "
                    f"Did you maybe forget to close the tag "
                    f"{rasaeco.et.to_str(open_tags[-1])}? "
                    f"See also https://github.com/mristin/rasaeco#known-issues "
                    f"in case you have missing or too many new lines."
                )
            else:
                return f"{exception.msg}; the line was: {line!r}"

        if event == "start":
            open_tags.append(element)
        elif event == "end":
            if len(open_tags) == 0:
                return (
                    f"Unexpected closing tag "
                    f"{rasaeco.et.to_str(element)} and no open tags"
                )

            elif open_tags[-1].tag != element.tag:
                return (
                    f"Unexpected closing tag "
                    f"{rasaeco.et.to_str(element)} as the last opened "
                    f"tag was: {rasaeco.et.to_str(open_tags[-1])}"
                )

            elif open_tags[-1].tag == element.tag:
                open_tags.pop()

            else:
                raise AssertionError(
                    f"Unhandled case: "
                    f"element.tag is {rasaeco.et.to_str(element)}, "
                    f"event: {event}, "
                    f"open tags: "
                    f"{list(map(rasaeco.et.to_str, open_tags))}"
                )
        else:
            raise AssertionError(f"Unhandled event: {event}")

    return None


@icontract.require(lambda scenario_path: scenario_path.suffix == ".md")
@icontract.require(lambda xml_path: xml_path.suffix == ".xml")
def _render_scenario_to_xml(
    scenario_path: pathlib.Path, xml_path: pathlib.Path
) -> List[str]:
    """Render the scenario to an intermediate XML representation."""
    try:
        text = scenario_path.read_text(encoding="utf-8")
    except Exception as exception:
        return [str(exception)]

    ##
    # Remove <rasaeco-meta>
    ##

    meta_range, meta_errors = rasaeco.meta.find_meta(text=text)
    if meta_errors:
        return meta_errors

    assert meta_range is not None

    text = text[: meta_range.block_start] + text[meta_range.block_end + 1 :]

    ##
    # Convert to HTML
    ##

    try:
        document = marko.convert(text)
    except Exception as exception:
        return [f"Failed to convert the scenario markdown to HTML: {exception}"]

    ##
    # Parse as HTML
    ##

    html_text = (
        f"<html>\n<body>\n"
        f"<div id='index'></div>\n"
        f"<div id='main'>{document}</div>\n"
        f"</body>\n</html>"
    )

    error = _verify_all_tags_closed(xml_text=html_text)
    if error:
        return [f"Failed to parse the scenario markdown converted to HTML: {error}"]

    try:
        root = ET.fromstring(html_text)
    except ET.ParseError as exception:
        lineno, _ = exception.position
        line = html_text.splitlines()[lineno - 1]

        return [
            f"Failed to parse the scenario markdown "
            f"converted to HTML: {exception}; the line was: {json.dumps(line)}"
        ]

    ##
    # Perform basic validation
    ##

    errors = []  # type: List[str]

    ##
    # Validate that all the tags have the "name" attribute which need to have one
    ##

    for element in itertools.chain(
        root.iter("model"),
        root.iter("def"),
        root.iter("test"),
        root.iter("acceptance"),
        root.iter("ref"),
        root.iter("modelref"),
        root.iter("testref"),
        root.iter("acceptanceref"),
        root.iter("phase"),
        root.iter("level"),
        root.iter("scenarioref"),
    ):
        if "name" not in element.attrib:
            errors.append(
                f"A <{element.tag}> lacks the `name` attribute in: {scenario_path}"
            )

    if errors:
        return errors

    try:
        xml_path.write_text(html_text)
    except Exception as error:
        return [
            f"Failed to store the intermediate XML representation "
            f"of a scenario {scenario_path} to {xml_path}: {error}"
        ]

    return []


def render_scenarios_to_xml(scenarios_dir: pathlib.Path) -> List[str]:
    """
    Render all the scenarios to the intermediate XML representation.

    Return errors if any.
    """
    errors = []  # type: List[str]

    scenario_pths = sorted(scenarios_dir.glob("**/scenario.md"))
    for pth in scenario_pths:
        to_xml_errors = _render_scenario_to_xml(
            scenario_path=pth, xml_path=as_xml_path(pth)
        )
        for error in to_xml_errors:
            errors.append(
                f"When rendering {pth} to intermediate XML representation: {error}"
            )

        if errors:
            continue

    return errors


@icontract.require(lambda xml_path: xml_path.suffix == ".xml")
def _extract_definitions(
    xml_path: pathlib.Path,
) -> Tuple[Optional[rasaeco.model.Definitions], List[str]]:
    """
    Extract the definitions from the intermediate representation of a scenario.

    Return (definitions, errors if any).
    """
    try:
        text = xml_path.read_text(encoding="utf-8")
    except Exception as exception:
        return None, [
            f"Failed to read the intermediate representation "
            f"of the scenario {xml_path}: {exception}"
        ]

    root = ET.fromstring(text)

    def collect_set_of_named_references(tag: str) -> Set[str]:
        """Collect the set of references for the given specification tag."""
        result = set()  # type: Set[str]
        for element in root.iter(tag):
            name = element.attrib["name"]
            result.add(name)
        return result

    return (
        rasaeco.model.Definitions(
            model_set=collect_set_of_named_references(tag="model"),
            def_set=collect_set_of_named_references(tag="def"),
            test_set=collect_set_of_named_references(tag="test"),
            acceptance_set=collect_set_of_named_references(tag="acceptance"),
        ),
        [],
    )


@icontract.require(lambda xml_path: xml_path.suffix == ".xml")
def _validate_references(
    scenario: rasaeco.model.Scenario,
    ontology: rasaeco.model.Ontology,
    xml_path: pathlib.Path,
) -> List[str]:
    """Validate that all the references are valid in the given scenario."""
    try:
        text = xml_path.read_text(encoding="utf-8")
    except Exception as exception:
        return [
            f"Failed to read the intermediate representation "
            f"of the scenario {xml_path}: {exception}"
        ]

    root = ET.fromstring(text)

    ##
    # Validate the references for different tags
    ##

    class SetGetterForScenario(Protocol):
        def __call__(self, scenario_id: str) -> Set[str]:
            ...

    @icontract.require(
        lambda reference_tag: reference_tag
        in ["modelref", "ref", "testref", "acceptanceref"]
    )
    def validate_references_for_tag(
        reference_tag: str, set_getter_for_scenario: SetGetterForScenario
    ) -> List[str]:
        """Validate that the reference tags refer to the actual definitions."""
        errors = []  # type: List[str]

        for element in root.iter(reference_tag):
            scenario_id, name = rasaeco.et.parse_reference_element(element=element)
            scenario_id = (
                scenario_id if scenario_id is not None else scenario.identifier
            )

            if scenario_id not in ontology.scenario_map:
                errors.append(
                    f"The {reference_tag} is invalid: {rasaeco.et.to_str(element)}; "
                    f"the scenario with the identifier {scenario_id} does not exist."
                )
            elif name not in set_getter_for_scenario(scenario_id=scenario_id):
                errors.append(
                    f"The {reference_tag} is invalid: {rasaeco.et.to_str(element)!r}; "
                    f"the specified target {name!r} is missing in the scenario {scenario_id}."
                )
            else:
                # The reference is valid.
                pass

        return errors

    errors = []  # type: List[str]

    errors.extend(
        validate_references_for_tag(
            reference_tag="modelref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.model_set,
        )
    )

    errors.extend(
        validate_references_for_tag(
            reference_tag="ref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.def_set,
        )
    )

    errors.extend(
        validate_references_for_tag(
            reference_tag="testref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.test_set,
        )
    )

    errors.extend(
        validate_references_for_tag(
            reference_tag="acceptanceref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.acceptance_set,
        )
    )

    ##
    # Validate the scenario references as a special case
    ##

    for element in root.iter("scenarioref"):
        scenario_id = element.attrib["name"]

        if scenario_id not in ontology.scenario_map:
            errors.append(
                f"The scenarioref is invalid: {rasaeco.et.to_str(element)}; "
                f"the scenario with the identifier {scenario_id} does not exist."
            )

    return errors


@icontract.require(lambda scenarios_dir: scenarios_dir.is_dir())
def load_ontology(
    scenarios_dir: pathlib.Path,
) -> Tuple[Optional[rasaeco.model.Ontology], List[str]]:
    """
    Read the ontology from the scenarios already rendered as intermediate XML.

    Return (ontology, errors if any).
    """
    errors = []  # type: List[str]

    path_map = dict()  # type: MutableMapping[str, pathlib.Path]
    meta_map = dict()  # type: MutableMapping[str, rasaeco.meta.Meta]

    scenario_pths = sorted(scenarios_dir.glob("**/scenario.md"))

    for pth in scenario_pths:
        xml_pth = as_xml_path(scenario_path=pth)
        if not xml_pth.exists():
            errors.append(
                f"The intermediate XML representation for the scenario {pth} "
                f"does not exist: {xml_pth}; "
                f"did you render the scenarios to intermediate XML representation "
                f"already?"
            )

    if errors:
        return None, errors

    for pth in scenario_pths:
        meta, meta_errors = rasaeco.meta.extract_meta(
            text=pth.read_text(encoding="utf-8")
        )

        for error in meta_errors:
            errors.append(f"In file {pth}: {error}")

        if meta_errors:
            continue

        assert meta is not None

        for i, cubelet in enumerate(meta["volumetric"]):
            ##
            # Verify aspect range
            ##

            range_error = rasaeco.model.verify_aspect_range(
                first=cubelet["aspect_from"], last=cubelet["aspect_to"]
            )

            if range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid aspect range: {range_error}"
                )

            range_error = rasaeco.model.verify_phase_range(
                first=cubelet["phase_from"], last=cubelet["phase_to"]
            )

            if range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid phase range: {range_error}"
                )

            range_error = rasaeco.model.verify_level_range(
                first=cubelet["level_from"], last=cubelet["level_to"]
            )

            if range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid level range: {range_error}"
                )

        identifier = pth.parent.relative_to(scenarios_dir).as_posix()

        meta_map[identifier] = meta
        path_map[identifier] = pth

    scenario_id_set = set(meta_map.keys())

    for identifier, meta in meta_map.items():
        for relate_to in meta["relations"]:
            if relate_to["target"] not in scenario_id_set:
                errors.append(
                    f"In file {path_map[identifier]}: "
                    f"The relation {relate_to['nature']!r} is invalid "
                    f"as the identifier of the target scenario can not be found: "
                    f"{relate_to['target']!r}"
                )

    if errors:
        return None, errors

    scenarios = []  # type: List[rasaeco.model.Scenario]
    for identifier, meta in meta_map.items():
        volumetric = []  # type: List[rasaeco.model.Cubelet]
        for cubelet in meta["volumetric"]:
            volumetric.append(
                rasaeco.model.Cubelet(
                    aspect_range=rasaeco.model.AspectRange(
                        first=cubelet["aspect_from"], last=cubelet["aspect_to"]
                    ),
                    phase_range=rasaeco.model.PhaseRange(
                        first=cubelet["phase_from"], last=cubelet["phase_to"]
                    ),
                    level_range=rasaeco.model.LevelRange(
                        first=cubelet["level_from"], last=cubelet["level_to"]
                    ),
                )
            )

        pth = path_map[identifier]
        definitions, extraction_errors = _extract_definitions(xml_path=as_xml_path(pth))
        if extraction_errors:
            errors.extend(extraction_errors)
        else:
            assert definitions is not None

            scenario = rasaeco.model.Scenario(
                identifier=identifier,
                title=meta["title"],
                contact=meta["contact"],
                volumetric=volumetric,
                definitions=definitions,
                relative_path=pth.relative_to(scenarios_dir),
            )

            scenarios.append(scenario)

    relations = []  # type: List[rasaeco.model.Relation]
    for identifier, meta in meta_map.items():
        for relation in meta["relations"]:
            relations.append(
                rasaeco.model.Relation(
                    source=identifier,
                    target=relation["target"],
                    nature=relation["nature"],
                )
            )

    ontology = rasaeco.model.Ontology(scenarios=scenarios, relations=relations)

    for scenario in ontology.scenarios:
        pth = scenarios_dir / scenario.relative_path
        validation_errors = _validate_references(
            scenario=scenario, ontology=ontology, xml_path=as_xml_path(pth)
        )

        for error in validation_errors:
            errors.append(f"When validating references in {pth}: {error}")

    if errors:
        return None, errors

    return ontology, []
