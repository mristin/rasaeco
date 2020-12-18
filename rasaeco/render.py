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
from typing import List, MutableMapping, Mapping, TypedDict, Set, Optional

import PIL
import icontract
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

    cubes = []
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

    voxels = cubes[0]
    for cube in cubes[1:]:
        voxels = voxels | cube

    fig = plt.figure()
    try:
        ax = fig.gca(projection="3d")
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


def _element_with_text(tag: str, text: str) -> ET.Element:
    """Create an element with text."""
    result = ET.Element(tag)
    result.text = text
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
                    f"Did you maybe forget to close the tag {_element_to_str(open_tags[-1])}?"
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


@dataclasses.dataclass
class _Token:
    identifier: str
    text: str


@icontract.require(lambda scenario_path: scenario_path.suffix == ".md")
def _render_scenario(
    scenario: rasaeco.model.Scenario,
    ontology: rasaeco.model.Ontology,
    scenario_path: pathlib.Path,
    scenarios_dir: pathlib.Path,
) -> List[str]:
    """Render a single scenario as HTML."""
    try:
        text = scenario_path.read_text(encoding="utf-8")
    except Exception as exception:
        return [f"Failed to read the scenario {scenario_path}: {exception}"]

    ##
    # Remove <rasaeco-meta>
    ##

    meta_range, errors = rasaeco.meta.find_meta(text=text)
    assert len(errors) == 0, errors
    assert meta_range is not None

    text = text[: meta_range.block_start] + text[meta_range.block_end + 1 :]

    ##
    # Convert to HTML
    ##

    try:
        document = marko.convert(text)
    except Exception as exception:
        return [
            f"Failed to convert the scenario markdown {scenario_path} to HTML: {exception}"
        ]

    ##
    # Parse as HTML
    ##

    html_text = f"<html>\n<body>\n{document}\n</body>\n</html>"

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
    # Transform
    ##

    body = root.find("body")
    assert body is not None

    ##
    # Add anchors for models
    ##

    model_set = set()  # type: Set[str]
    in_models = False

    for element in body:
        if element.tag == "h2":
            if in_models:
                in_models = False
            else:
                if (
                    element.text is not None
                    and element.text.strip().lower() == "models"
                ):
                    in_models = True

        elif in_models and element.tag == "h3":
            name = element.text.strip() if element.text is not None else ""
            model_set.add(name)

            anchor_id = f"model-{name}"

            link_el = ET.Element(
                "a", attrib={"href": f"#{anchor_id}", "class": "anchor"}
            )
            link_el.append(ET.Element("a", attrib={"id": anchor_id}))
            link_el.text = "🔗"
            link_el.tail = element.text

            element.insert(0, link_el)
            element.text = ""
        else:
            pass

    ##
    # Add anchors for defs
    ##

    def_set = set()  # type: Set[str]
    in_defs = False

    for element in body:
        if element.tag == "h2":
            if in_defs:
                in_defs = False
            else:
                if (
                    element.text is not None
                    and element.text.strip().lower() == "definitions"
                ):
                    in_defs = True

        elif in_defs and element.tag == "h3":
            name = element.text.strip() if element.text is not None else ""
            def_set.add(name)

            anchor_id = f"def-{name}"

            link_el = ET.Element(
                "a", attrib={"href": f"#{anchor_id}", "class": "anchor"}
            )
            link_el.append(ET.Element("a", attrib={"id": anchor_id}))
            link_el.text = "🔗"
            link_el.tail = element.text

            element.insert(0, link_el)
            element.text = ""
        else:
            pass

    ##
    # Validate that all the tags have the "name" attribute which need to have one
    ##

    for element in itertools.chain(
        root.iter("ref"),
        root.iter("modelref"),
        root.iter("phase"),
        root.iter("level"),
    ):
        if "name" not in element.attrib:
            errors.append(
                f"A <{element.tag}> lacks the `name` attribute in: {scenario_path}"
            )

    if errors:
        return errors

    ##
    # Validate that all modelrefs have the model defined
    ##

    for element in root.iter("modelref"):
        modelref = element.attrib["name"]
        if modelref not in model_set:
            errors.append(f"The modelref is invalid: {modelref!r}")

    ##
    # Validate that all refs have the def defined
    ##

    for element in root.iter("ref"):
        ref = element.attrib["name"]
        if ref not in def_set:
            errors.append(f"The ref is invalid: {ref!r}")

    if errors:
        return errors

    ##
    # Replace <ref> tags with proper HTML
    ##

    for element in root.iter("ref"):
        anchor_name = element.attrib["name"]

        element.tag = "a"
        element.attrib = {"href": f"#def-{anchor_name}", "class": "ref"}

        if len(element) == 0 and not element.text:
            element.text = anchor_name

    ##
    # Replace <modelref> tags with proper HTML
    ##

    for element in root.iter("modelref"):
        anchor_name = element.attrib["name"]

        element.tag = "a"
        element.attrib = {"href": f"#model-{anchor_name}", "class": "modelref"}

        if len(element) == 0 and not element.text:
            element.text = anchor_name

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

        element.tag = "span"
        element.attrib = {"class": "phase", "data-text": name}

        sup_el = ET.Element("sup")
        sup_el.text = name
        element.append(sup_el)

        anchor = f"phase-anchor-{uuid.uuid4()}"
        anchor_el = ET.Element("a", attrib={"id": anchor})
        element.insert(0, anchor_el)
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

        sup_el = ET.Element("sup")
        sup_el.text = name
        element.append(sup_el)

        anchor = f"level-anchor-{uuid.uuid4()}"
        anchor_el = ET.Element("a", attrib={"id": anchor})
        element.insert(0, anchor_el)
        level_anchors.append(LevelAnchor(identifier=anchor, level=name))

    ##
    # Append phase index
    ##

    if phase_anchors:
        heading_el = ET.Element("h2")
        heading_el.text = "Phase Index"
        body.append(heading_el)

        list_el = ET.Element("ul")
        for phase_anch in phase_anchors:
            link_el = ET.Element("a", attrib={"href": f"#{phase_anch.identifier}"})
            link_el.text = phase_anch.phase

            item_el = ET.Element("li")
            item_el.append(link_el)

            list_el.append(item_el)

        body.append(list_el)

    ##
    # Append level index
    ##

    if level_anchors:
        heading_el = ET.Element("h2")
        heading_el.text = "Level Index"
        body.append(heading_el)

        list_el = ET.Element("ul")
        for level_anch in level_anchors:
            link_el = ET.Element("a", attrib={"href": f"#{level_anch.identifier}"})
            link_el.text = level_anch.level

            item_el = ET.Element("li")
            item_el.append(link_el)

            list_el.append(item_el)

        body.append(list_el)

    ##
    # Construct <head>
    ##

    head_el = ET.Element("head")

    meta = ET.Element("meta")
    meta.attrib["charset"] = "utf-8"
    head_el.append(meta)

    live_script = ET.Element("script")
    live_script.attrib["src"] = "https://livejs.com/live.js"
    live_script.text = " "
    head_el.append(live_script)

    title_el = ET.Element("title")
    title_el.text = scenario.title
    head_el.append(title_el)

    style_el = ET.Element("style")
    style_el.text = textwrap.dedent(
        """\
        body {
            margin-right: 5%;
            margin-left: 5%;
            margin-top: 5%;
            margin-bottom: 5%;
            padding: 1%;
            border: 1px solid black;
        }
        
        a {
            text-decoration: none;
        }
        
        a.anchor {
            text-decoration: none;
            font-size: x-small;
            margin-right: 1em;
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
    )
    head_el.append(style_el)

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
            li.append(
                _element_with_text("span", f"{scenario.title} {relation.nature} ")
            )

            target = ontology.scenario_map[relation.target]
            link = ET.Element("a")

            target_url = (
                pathlib.PurePosixPath(
                    *([".."] * len(scenario.relative_path.parent.parts))
                )
                / target.relative_path.parent
                / f"{target.relative_path.stem}.html"
            ).as_posix()

            link.attrib["href"] = target_url
            link.text = target.title
            li.append(link)

            ul.append(li)

        ul.tail = "\n"
        body.insert(0, ul)
        body.insert(
            0, _element_with_text(tag="h2", text="Relations from Other Scenarios")
        )

    if len(relations_to) > 0:
        ul = ET.Element("ul")
        for relation in relations_to:
            assert relation.target == scenario.identifier

            li = ET.Element("li")
            link = ET.Element("a")
            source = ontology.scenario_map[relation.source]

            source_url = (
                pathlib.PurePosixPath(
                    *([".."] * len(scenario.relative_path.parent.parts))
                )
                / source.relative_path.parent
                / f"{source.relative_path.stem}.html"
            ).as_posix()

            link.attrib["href"] = source_url
            link.text = source.title
            li.append(link)

            li.append(
                _element_with_text("span", f" {relation.nature} {scenario.title}")
            )

            ul.append(li)

        body.insert(0, ul)
        body.insert(
            0, _element_with_text(tag="h2", text="Relations to Other Scenarios")
        )

    ##
    # Insert volumetric plot
    ##

    img = ET.Element("img")
    img.attrib["src"] = "volumetric.png"
    img.attrib["style"] = "border: 1px solid #EEEEEE; padding: 10px;"

    body.insert(0, img)

    ##
    # Insert the title
    ##

    body.insert(0, _element_with_text(tag="h1", text=scenario.title))

    ##
    # Insert back button
    ##

    back_link = ET.Element("a")

    back_url = (
        pathlib.PurePosixPath(
            *([".."] * len(scenario_path.parent.relative_to(scenarios_dir).parts))
        )
        / "ontology.html"
    ).as_posix()

    back_link.attrib["href"] = back_url
    back_link.text = "Back to ontology"
    body.insert(0, back_link)

    ##
    # Save
    ##

    target_pth = scenario_path.parent / (scenario_path.stem + ".html")

    try:
        target_pth.write_bytes(ET.tostring(root, encoding="utf-8"))
    except Exception as exception:
        return [f"Failed to write generated HTML code to {target_pth}: {exception}"]

    return []


def once(scenarios_dir: pathlib.Path) -> List[str]:
    """
    Render the scenarios and the ontology.

    Return errors if any.
    """
    path_map = dict()  # type: MutableMapping[str, pathlib.Path]
    meta_map = dict()  # type: MutableMapping[str, rasaeco.meta.Meta]

    errors = []  # type: List[str]
    for pth in sorted(scenarios_dir.glob("**/*.md")):
        meta, meta_errors = rasaeco.meta.extract_meta(
            text=pth.read_text(encoding="utf-8")
        )

        for error in meta_errors:
            errors.append(f"In file {pth}: {error}")

        if meta_errors:
            continue

        assert meta is not None

        if meta["identifier"] in path_map:
            errors.append(
                f"In file {pth}: Identifier conflicts with the file {path_map[meta['identifier']]}"
            )

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

        meta_map[meta["identifier"]] = meta
        path_map[meta["identifier"]] = pth

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

        scenario = rasaeco.model.Scenario(
            identifier=identifier,
            title=meta["title"],
            volumetric=volumetric,
            relative_path=path_map[identifier].relative_to(scenarios_dir),
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
        render_errors = _render_scenario(
            scenario=scenario,
            ontology=ontology,
            scenario_path=pth,
            scenarios_dir=scenarios_dir,
        )

        for error in render_errors:
            errors.append(f"When rendering {pth}: {error}")

    if errors:
        return errors

    return []
