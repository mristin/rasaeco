"""Process the scenario files to obtain the ontology and render it as HTML."""
import dataclasses
import itertools
import json
import pathlib
import re
import textwrap
import uuid
import xml.etree.ElementTree as ET
import xml.sax.saxutils
from typing import (
    List,
    MutableMapping,
    Mapping,
    TypedDict,
    Set,
    Optional,
    Tuple,
    TypeVar,
    Protocol,
    Dict,
)

import PIL
import icontract
import inflect
import marko
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import rasaeco.meta
import rasaeco.model
import rasaeco.template


def _render_ontology(
    ontology: rasaeco.model.Ontology,
    scenarios_dir: pathlib.Path,
    path_map: Mapping[str, pathlib.Path],
) -> List[str]:
    """
    Render the ontology as a HTML file.

    Return errors if any.
    """
    scenario_index_map = {
        scenario: i for i, scenario in enumerate(ontology.scenario_map)
    }

    class Node(TypedDict):
        name: str
        url: str

    class Edge(TypedDict):
        source: int
        target: int
        label: str

    class Dataset(TypedDict):
        nodes: List[Node]
        edges: List[Edge]

    nodes = []  # type: List[Node]
    for scenario in ontology.scenarios:
        scenario_pth = path_map[scenario.identifier]

        rel_md_pth = scenario_pth.relative_to(scenarios_dir)
        rel_html_pth = rel_md_pth.parent / (rel_md_pth.stem + ".html")

        nodes.append(Node(name=scenario.title, url=rel_html_pth.as_posix()))

    edges = []  # type: List[Edge]
    for relation in ontology.relations:
        edges.append(
            Edge(
                source=scenario_index_map[relation.source],
                target=scenario_index_map[relation.target],
                label=relation.nature,
            )
        )

    pth = scenarios_dir / "ontology.html"

    ontology_html = rasaeco.template.ONTOLOGY_HTML_TPL.render(
        dataset=json.dumps(Dataset(nodes=nodes, edges=edges), indent=2)
    )

    try:
        pth.write_text(ontology_html, encoding="utf-8")
    except Exception as exception:
        return [f"Failed to write the ontology to {pth}: {exception}"]

    return []


def _render_volumetric_plot(
    plot_path: pathlib.Path, scenario: rasaeco.model.Scenario
) -> List[str]:
    """
    Render the 3D volumetric plot and store it as an image.

    Return errors if any.
    """
    x, y, z = np.indices(
        (
            len(rasaeco.model.PHASES),
            len(rasaeco.model.LEVELS),
            len(rasaeco.model.ASPECTS),
        )
    )

    cubes = []  # type: List[np.ndarray]
    for cubelet in scenario.volumetric:
        phase_first_idx = rasaeco.model.PHASES.index(cubelet.phase_range.first)
        phase_last_idx = rasaeco.model.PHASES.index(cubelet.phase_range.last)

        level_first_idx = rasaeco.model.LEVELS.index(cubelet.level_range.first)
        level_last_idx = rasaeco.model.LEVELS.index(cubelet.level_range.last)

        aspect_first_idx = rasaeco.model.ASPECTS.index(cubelet.aspect_range.first)
        aspect_last_idx = rasaeco.model.ASPECTS.index(cubelet.aspect_range.last)

        cube = (
            (phase_first_idx <= x)
            & (x <= phase_last_idx)
            & (level_first_idx <= y)
            & (y <= level_last_idx)
            & (aspect_first_idx <= z)
            & (z <= aspect_last_idx)
        )

        cubes.append(cube)

    voxels = None  # type: Optional[np.ndarray]

    if cubes:
        voxels = cubes[0]
        for cube in cubes[1:]:
            voxels = voxels | cube

    fig = plt.figure()
    try:
        ax = fig.gca(projection="3d")

        if voxels is not None:
            ax.voxels(voxels, edgecolor="k")

        ax.set_xticks(list(range(len(rasaeco.model.PHASES) + 1)))
        ax.set_xticklabels([""] * (len(rasaeco.model.PHASES) + 1))

        for i, phase in enumerate(rasaeco.model.PHASES):
            ax.text(i + 0.5, -4.2, 0, phase, color="green", fontsize=8, zdir="y")

        ax.set_yticks(list(range(len(rasaeco.model.LEVELS) + 1)))
        ax.set_yticklabels([""] * (len(rasaeco.model.LEVELS) + 1))

        for i, level in enumerate(rasaeco.model.LEVELS):
            ax.text(
                len(rasaeco.model.PHASES) + 0.7, i, 0, level, color="red", fontsize=8
            )

        ax.set_zticks(range(len(rasaeco.model.ASPECTS) + 1))
        ax.set_zticklabels([""] * (len(rasaeco.model.ASPECTS) + 1))

        for i, aspect in enumerate(rasaeco.model.ASPECTS):
            ax.text(
                len(rasaeco.model.PHASES) + 0.4,
                len(rasaeco.model.LEVELS) + 1,
                i,
                aspect,
                color="blue",
                fontsize=8,
            )

        try:
            plt.savefig(str(plot_path))
        except Exception as exception:
            return [f"Failed to save the volumetric plot to {plot_path}: {exception}"]
    finally:
        plt.close(fig)

    # Crop manually
    with PIL.Image.open(plot_path) as image:
        # left, upper, right, lower
        image_crop = image.crop((139, 86, 567, 450))
        image_crop.save(plot_path)

    return []


def _new_element(
    tag: str,
    text: Optional[str] = None,
    attrib: Optional[Dict[str, str]] = None,
    tail: Optional[str] = None,
) -> ET.Element:
    """Create an element with text."""
    result = ET.Element(tag)
    result.text = text

    if attrib is not None:
        result.attrib = attrib

    if tail is not None:
        result.tail = tail

    return result


def _element_to_str(element: ET.Element) -> str:
    """Dump the element to a string."""
    attribs_as_str = " ".join(
        f"{key}={xml.sax.saxutils.quoteattr(value)}"
        for key, value in element.attrib.items()
    )
    if attribs_as_str:
        return f"<{element.tag} {attribs_as_str}>"
    else:
        return f"<{element.tag}>"


def _verify_all_tags_closed(xml_text: str) -> Optional[str]:
    """
    Verify that all the tags were properly closed in the XML given as text.

    Return error if any.
    """
    parser = ET.XMLPullParser(["start", "end"])
    parser.feed(xml_text.encode("utf-8"))

    open_tags = []  # type: List[ET.Element]

    iter = parser.read_events()
    while True:
        try:
            event, element = next(iter)
        except StopIteration:
            break
        except ET.ParseError as exception:
            lineno, _ = exception.position
            line = xml_text.splitlines()[lineno - 1]

            if exception.msg.startswith("mismatched tag:"):
                return (
                    f"{exception.msg}; the line was: {line!r}, "
                    f"the open tag(s) up to that point: {list(map(_element_to_str, open_tags))}. "
                    f"Did you maybe forget to close the tag {_element_to_str(open_tags[-1])}? "
                    f"See also https://github.com/mristin/rasaeco#known-issues in case you "
                    f"have missing or too many new lines."
                )
            else:
                return f"{exception.msg}; the line was: {line!r}"

        if event == "start":
            open_tags.append(element)
        elif event == "end":
            if len(open_tags) == 0:
                return f"Unexpected closing tag {_element_to_str(element)} and no open tags"

            elif open_tags[-1].tag != element.tag:
                return (
                    f"Unexpected closing tag {_element_to_str(element)} "
                    f"as the last opened tag was: {_element_to_str(open_tags[-1])}"
                )

            elif open_tags[-1].tag == element.tag:
                open_tags.pop()

            else:
                raise AssertionError(
                    f"Unhandled case: "
                    f"element.tag is {_element_to_str(element)}, event: {event}, "
                    f"open tags: {list(map(_element_to_str, open_tags))}"
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


@icontract.require(
    lambda element: element.tag in ["ref", "modelref", "testref", "acceptanceref"]
)
def _parse_reference_element(element: ET.Element) -> Tuple[Optional[str], str]:
    """Extract the scenario identifier and the name from a reference element."""
    name_attribute = element.attrib["name"]
    if "#" in name_attribute:
        scenario_id, name = name_attribute.split("#")
        return scenario_id, name
    else:
        return None, name_attribute


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
            scenario_id, name = _parse_reference_element(element=element)
            scenario_id = (
                scenario_id if scenario_id is not None else scenario.identifier
            )

            if scenario_id not in ontology.scenario_map:
                errors.append(
                    f"The {reference_tag} is invalid: {_element_to_str(element)}; "
                    f"the scenario with the identifier {scenario_id} does not exist."
                )
            elif name not in set_getter_for_scenario(scenario_id=scenario_id):
                errors.append(
                    f"The {reference_tag} is invalid: {_element_to_str(element)!r}; "
                    f"the specified target {name!r} is missing in the scenario {scenario_id}."
                )
            else:
                # The reference is valid.
                pass

        return errors

    return (
        validate_references_for_tag(
            reference_tag="modelref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.model_set,
        )
        + validate_references_for_tag(
            reference_tag="ref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.def_set,
        )
        + validate_references_for_tag(
            reference_tag="testref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.test_set,
        )
        + validate_references_for_tag(
            reference_tag="acceptanceref",
            set_getter_for_scenario=lambda scenario_id: ontology.scenario_map[
                scenario_id
            ].definitions.acceptance_set,
        )
    )


_INFLECT_ENGINE = inflect.engine()


@icontract.require(lambda xml_path: xml_path.suffix == ".xml")
def _render_scenario(
    scenario: rasaeco.model.Scenario,
    ontology: rasaeco.model.Ontology,
    xml_path: pathlib.Path,
    html_path: pathlib.Path,
) -> List[str]:
    """Render a single scenario as HTML."""
    try:
        text = xml_path.read_text(encoding="utf-8")
    except Exception as exception:
        return [
            f"Failed to read the intermediate representation "
            f"of the scenario {xml_path}: {exception}"
        ]

    rel_pth_to_scenario_dir = pathlib.PurePosixPath(
        *([".."] * len(scenario.relative_path.parent.parts))
    )

    root = ET.fromstring(text)

    main_div = None  # type: Optional[ET.Element]
    for element in root.iter("div"):
        if "id" in element.attrib and element.attrib["id"] == "main":
            main_div = element
            break

    assert main_div is not None

    index_div = None  # type: Optional[ET.Element]
    for element in root.iter("div"):
        if "id" in element.attrib and element.attrib["id"] == "index":
            index_div = element
            break

    assert index_div is not None

    ##
    # Convert specification tags to proper HTML
    ##

    def convert_tags_to_html(tag: str, readable_title: bool) -> None:
        """Convert a specification tag, such as <model> to proper HTML."""
        for element in root.iter(tag):
            name = element.attrib["name"]

            element.tag = "div"
            element.attrib = {"class": tag}

            element.insert(
                0,
                _new_element(
                    tag="h3",
                    text=name.replace("_", " ") if readable_title else name,
                    attrib={"data-anchor": f"{tag}-{name}"},
                    tail="\n",
                ),
            )

    convert_tags_to_html(tag="model", readable_title=False)
    convert_tags_to_html(tag="def", readable_title=True)
    convert_tags_to_html(tag="test", readable_title=True)
    convert_tags_to_html(tag="acceptance", readable_title=True)

    ##
    # Convert references to proper HTML
    ##

    # <ref> is a special case as we need to pluralize and prettify.
    for element in root.iter("ref"):
        scenario_id, ref = _parse_reference_element(element=element)

        readable = ref.replace("_", " ")
        if element.tail is not None and element.tail.startswith("s"):
            element.tail = element.tail[1:]
            readable = _INFLECT_ENGINE.plural_noun(readable)

        if scenario_id is None:
            link_text = readable
            href = f"#def-{ref}"
        else:
            link_text = f"{readable} (from {scenario_id})"

            href_pth = _html_path(
                scenario_path=rel_pth_to_scenario_dir
                / ontology.scenario_map[scenario_id].relative_path
            )
            href = f"{href_pth.as_posix()}#def-{ref}"

        element.tag = "a"
        element.attrib = {"href": href, "class": "ref"}

        if len(element) == 0 and not element.text:
            element.text = link_text

    @icontract.require(
        lambda reference_tag: reference_tag
        in ["modelref", "ref", "testref", "acceptanceref"]
    )
    def convert_references_to_html(reference_tag: str) -> None:
        """Convert the reference tags to proper HTML."""
        if reference_tag == "modelref":
            target_tag = "model"
        elif reference_tag == "ref":
            target_tag = "def"
        elif reference_tag == "testref":
            target_tag = "test"
        elif reference_tag == "acceptanceref":
            target_tag = "acceptance"
        else:
            raise ValueError(f"Unexpected reference tag: {reference_tag!r}")

        for element in root.iter(reference_tag):
            scenario_id, name = _parse_reference_element(element=element)

            if scenario_id is None:
                link_text = name
                href = f"#{target_tag}-{name}"
            else:
                link_text = f"{name} (from {scenario_id})"

                href_pth = _html_path(
                    scenario_path=rel_pth_to_scenario_dir
                    / ontology.scenario_map[scenario_id].relative_path
                )
                href = f"{href_pth.as_posix()}#{target_tag}-{name}"

            element.tag = "a"
            element.attrib = {"href": href, "class": reference_tag}

            if len(element) == 0 and not element.text:
                element.text = link_text

    convert_references_to_html(reference_tag="modelref")
    convert_references_to_html(reference_tag="testref")
    convert_references_to_html(reference_tag="acceptanceref")

    ##
    # Replace <phase> tags with proper HTML
    ##

    @dataclasses.dataclass
    class PhaseAnchor:
        identifier: str
        phase: str

    phase_anchors = []  # type: List[PhaseAnchor]

    for element in root.iter("phase"):
        name = element.attrib["name"]
        readable = name.replace("_", " ")

        element.tag = "span"
        element.attrib = {"class": "phase", "data-text": name}

        element.append(_new_element(tag="sup", text=readable))

        anchor = f"phase-anchor-{uuid.uuid4()}"

        element.insert(0, _new_element(tag="a", attrib={"id": anchor}))

        phase_anchors.append(PhaseAnchor(identifier=anchor, phase=name))

    ##
    # Replace <level> tags with proper HTML
    ##

    @dataclasses.dataclass
    class LevelAnchor:
        identifier: str
        level: str

    level_anchors = []  # type: List[LevelAnchor]

    for element in root.iter("level"):
        name = element.attrib["name"]

        element.tag = "span"
        element.attrib = {"class": "level", "data-text": name}

        element.append(_new_element(tag="sup", text=name.replace("_", " ")))

        anchor = f"level-anchor-{uuid.uuid4()}"

        element.insert(0, _new_element(tag="a", attrib={"id": anchor}))

        level_anchors.append(LevelAnchor(identifier=anchor, level=name))

    ##
    # Anchor the remaining sections which have not been anchored so far
    ##

    section_anchor_set = set()  # type: Set[str]
    for element in main_div.iter():
        if re.match(r"^[hH]\d+$", element.tag) and "data-anchor" not in element.attrib:
            assert element.text is not None
            initial_anchor = f"section-{element.text.replace(' ', '_')}"

            anchor = initial_anchor
            i = 1
            while anchor in section_anchor_set:
                anchor = initial_anchor + str(i)
                i += 1

            element.attrib["data-anchor"] = anchor
            section_anchor_set.add(anchor)

    ##
    # Add anchor links for all the headings and collect data for the table-of-contents
    ##

    @dataclasses.dataclass
    class TocEntry:
        """Represent an entry in the table of contents."""

        text: str
        anchor: str
        level: int

    toc = []  # type: List[TocEntry]

    for element in main_div.iter():
        mtch = re.match(r"^[hH](?P<section_level>\d+)$", element.tag)
        if mtch:
            section_level = int(mtch.group("section_level"))

            assert "data-anchor" in element.attrib, (
                f"Unexpected tag without data-anchor: "
                f"{_element_to_str(element)} with text {element.text}"
            )

            anchor = element.attrib["data-anchor"]

            link_el = _new_element(
                "a",
                text=element.text,
                attrib={"class": "section-anchor", "href": f"#{anchor}"},
            )

            chain_el = _new_element("span", text="🔗", attrib={"class": "chain-symbol"})

            anchor_el = _new_element("a", attrib={"name": anchor})

            element.text = ""

            element.insert(0, chain_el)
            element.insert(0, link_el)
            element.insert(0, anchor_el)

            assert link_el.text is not None

            toc.append(TocEntry(text=link_el.text, anchor=anchor, level=section_level))

    ##
    # Generate the table of contents
    ##

    index_div.append(_new_element("h2", "Table of Contents"))
    ul_el = _new_element("ul", attrib={"class": "toc"})
    index_div.append(ul_el)

    toc_level_offset = min(entry.level for entry in toc) if len(toc) > 0 else 0

    for entry in toc:
        margin = 2.2 * (entry.level - toc_level_offset)
        li_el = _new_element("li", attrib={"style": f"padding-left: {margin:.2f}em"})

        link_el = _new_element(
            "a", text=entry.text, attrib={"href": f"#{entry.anchor}"}
        )
        li_el.append(link_el)

        ul_el.append(li_el)

    ##
    # Append phase index
    ##

    if phase_anchors:
        index_div.append(_new_element("h2", "Phase Index"))

        list_el = ET.Element("ul")
        for phase_anch in phase_anchors:
            link_el = _new_element("a", attrib={"href": f"#{phase_anch.identifier}"})
            link_el.text = phase_anch.phase

            item_el = ET.Element("li")
            item_el.append(link_el)

            list_el.append(item_el)

        index_div.append(list_el)

    ##
    # Append level index
    ##

    if level_anchors:
        index_div.append(_new_element("h2", "Level Index"))

        list_el = ET.Element("ul")
        for level_anch in level_anchors:
            item_el = ET.Element("li")
            item_el.append(
                _new_element(
                    tag="a",
                    text=level_anch.level,
                    attrib={"href": f"#{level_anch.identifier}"},
                )
            )

            list_el.append(item_el)

        index_div.append(list_el)

    ##
    # Construct <head>
    ##

    head_el = ET.Element("head")

    head_el.append(_new_element("meta", attrib={"charset": "utf-8"}))
    head_el.append(
        _new_element("script", text=" ", attrib={"src": "https://livejs.com/live.js"})
    )
    head_el.append(_new_element("title", text=scenario.title))

    head_el.append(
        _new_element(
            "style",
            text=textwrap.dedent(
                """\
                body {
                    margin-top: 2em;
                    padding: 0px;
                }
                
                #main {
                    float: left;
                    width: 50em;
                    margin-left: 3%;
                    border: 1px solid black;
                    padding: 2em;
                }
                
                #index {
                    float: left;
                    width: 30%;
                    border: 1px solid black;
                    padding: 1em;
                }
                
                ul.toc {
                    list-style-type: none;
                }
                
                ul.toc li {
                    margin-bottom: 0.5em;
                }
                
                a {
                    text-decoration: none;
                    color: blue;
                }
                
                a:visited {
                    color: blue;
                }
                
                a.section-anchor {
                    text-decoration: none;
                    color: black;
                }
                
                .chain-symbol {
                    display: none;
                    font-size: x-small;
                    margin-left: 0.5em;
                }
                a.section-anchor:hover + .chain-symbol {
                    display: inline-block;
                }
        
                span.phase {
                    background-color: #eefbfb;
                }
        
                span.level {
                    background-color: #eefbee;
                }
        
                pre {
                    background-color: #eeeefb;
                    padding: 1em;
                }
                """
            ),
        )
    )

    root.insert(0, head_el)

    ##
    # Insert the relations to other scenarios
    ##

    relations_from = ontology.relations_from.get(scenario, [])
    relations_to = ontology.relations_to.get(scenario, [])

    if len(relations_from) > 0:
        ul = ET.Element("ul")
        for relation in relations_from:
            assert relation.source == scenario.identifier

            li = ET.Element("li")
            li.append(_new_element("span", f"{scenario.title} {relation.nature} "))

            target = ontology.scenario_map[relation.target]

            target_url = (
                pathlib.PurePosixPath(
                    *([".."] * len(scenario.relative_path.parent.parts))
                )
                / target.relative_path.parent
                / f"{target.relative_path.stem}.html"
            ).as_posix()

            li.append(_new_element("a", text=target.title, attrib={"href": target_url}))

            ul.append(li)

        ul.tail = "\n"
        main_div.insert(0, ul)
        main_div.insert(
            0, _new_element(tag="h2", text="Relations from Other Scenarios")
        )

    if len(relations_to) > 0:
        ul = ET.Element("ul")
        for relation in relations_to:
            assert relation.target == scenario.identifier

            source = ontology.scenario_map[relation.source]

            source_url = (
                pathlib.PurePosixPath(
                    *([".."] * len(scenario.relative_path.parent.parts))
                )
                / source.relative_path.parent
                / f"{source.relative_path.stem}.html"
            ).as_posix()

            li = ET.Element("li")
            li.append(_new_element("a", text=source.title, attrib={"href": source_url}))
            li.append(_new_element("span", f" {relation.nature} {scenario.title}"))

            ul.append(li)

        main_div.insert(0, ul)
        main_div.insert(0, _new_element(tag="h2", text="Relations to Other Scenarios"))

    ##
    # Insert volumetric plot
    ##

    index_div.insert(
        0,
        _new_element(
            "img",
            attrib={
                "src": "volumetric.png",
                "style": "border: 1px solid #EEEEEE; padding: 10px;",
            },
        ),
    )

    ##
    # Insert the contact
    ##

    contact_parts = [part.strip() for part in scenario.contact.split(",")]
    contact_ul = ET.Element("ul")
    for part in contact_parts:
        contact_ul.append(_new_element("li", text=part))

    ##
    # Insert the title
    ##

    main_div.insert(0, _new_element(tag="h1", text=scenario.title))

    ##
    # Insert back button
    ##

    back_url = (
        pathlib.PurePosixPath(*([".."] * len(scenario.relative_path.parent.parts)))
        / "ontology.html"
    ).as_posix()

    index_div.insert(
        0, _new_element("a", text="Back to ontology", attrib={"href": back_url})
    )

    ##
    # Save
    ##

    try:
        html_path.write_bytes(ET.tostring(root, encoding="utf-8"))
    except Exception as exception:
        return [f"Failed to write generated HTML code to {html_path}: {exception}"]

    return []


def _xml_path(scenario_path: pathlib.Path) -> pathlib.Path:
    """Generate the corresponding XML path of the intermediate representation."""
    return scenario_path.parent / (scenario_path.stem + ".xml")


PathT = TypeVar("PathT", pathlib.Path, pathlib.PurePosixPath)


def _html_path(scenario_path: PathT) -> PathT:
    """Generate the corresponding path of the HTML representation."""
    return scenario_path.parent / (scenario_path.stem + ".html")


def once(scenarios_dir: pathlib.Path) -> List[str]:
    """
    Render the scenarios and the ontology.

    Return errors if any.
    """
    path_map = dict()  # type: MutableMapping[str, pathlib.Path]
    meta_map = dict()  # type: MutableMapping[str, rasaeco.meta.Meta]

    errors = []  # type: List[str]

    scenario_pths = sorted(scenarios_dir.glob("**/scenario.md"))
    for pth in scenario_pths:
        to_xml_errors = _render_scenario_to_xml(
            scenario_path=pth, xml_path=_xml_path(pth)
        )
        for error in to_xml_errors:
            errors.append(
                f"When rendering {pth} to intermediate XML representation: {error}"
            )

        if errors:
            continue

    if errors:
        return errors

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
                    f"In file {pth} and cubelet {i + 1}: Invalid aspect range: {range_error}"
                )

            range_error = rasaeco.model.verify_phase_range(
                first=cubelet["phase_from"], last=cubelet["phase_to"]
            )

            if range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: Invalid phase range: {range_error}"
                )

            range_error = rasaeco.model.verify_level_range(
                first=cubelet["level_from"], last=cubelet["level_to"]
            )

            if range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: Invalid level range: {range_error}"
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
                    f"The relation {relate_to['nature']!r} is invalid as the identifier "
                    f"of the target scenario can not be found: {relate_to['target']!r}"
                )

    if errors:
        return errors

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
        definitions, extraction_errors = _extract_definitions(xml_path=_xml_path(pth))
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

    for scenario in scenarios:
        plot_pth = path_map[scenario.identifier].parent / "volumetric.png"
        _render_volumetric_plot(plot_path=plot_pth, scenario=scenario)

    _render_ontology(ontology=ontology, scenarios_dir=scenarios_dir, path_map=path_map)

    for scenario in scenarios:
        pth = path_map[scenario.identifier]
        validation_errors = _validate_references(
            scenario=scenario, ontology=ontology, xml_path=_xml_path(pth)
        )

        for error in validation_errors:
            errors.append(f"When validating references in {pth}: {error}")

    if errors:
        return errors

    for scenario in scenarios:
        pth = path_map[scenario.identifier]

        render_errors = _render_scenario(
            scenario=scenario,
            ontology=ontology,
            xml_path=_xml_path(pth),
            html_path=_html_path(pth),
        )

        for error in render_errors:
            errors.append(f"When rendering {pth}: {error}")

    if errors:
        return errors

    return []
