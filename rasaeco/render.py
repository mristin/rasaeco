"""Process the scenario files to obtain the ontology and render it as HTML."""
import dataclasses
import json
import pathlib
import re
import textwrap
import uuid
import xml.etree.ElementTree as ET
from typing import (
    List,
    TypedDict,
    Set,
    Optional,
    TypeVar,
    Dict,
)

import PIL
import icontract
import inflect
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import rasaeco.meta
import rasaeco.model
import rasaeco.template
import rasaeco.intermediate
import rasaeco.et


def _render_ontology_html(
    ontology: rasaeco.model.Ontology, scenarios_dir: pathlib.Path
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
        thumbnail_url: str

    class Edge(TypedDict):
        source: int
        target: int
        label: str

    class Dataset(TypedDict):
        nodes: List[Node]
        edges: List[Edge]

    nodes = []  # type: List[Node]
    for scenario in ontology.scenarios:
        rel_html_pth = scenario.relative_path.parent / (
            scenario.relative_path.stem + ".html"
        )

        rel_thumbnail_pth = scenario.relative_path.parent / "volumetric_thumb.svg"

        nodes.append(
            Node(
                name=scenario.title,
                url=rel_html_pth.as_posix(),
                thumbnail_url=rel_thumbnail_pth.as_posix(),
            )
        )

    edges = []  # type: List[Edge]
    for relation in ontology.relations:
        edges.append(
            Edge(
                source=scenario_index_map[relation.source],
                target=scenario_index_map[relation.target],
                label=relation.nature,
            )
        )

    dataset = Dataset(nodes=nodes, edges=edges)

    ##
    # Render to HTML
    ##

    pth = scenarios_dir / "ontology.html"

    ontology_html = rasaeco.template.ONTOLOGY_HTML_TPL.render(
        dataset=json.dumps(dataset, indent=2)
    )

    try:
        pth.write_text(ontology_html, encoding="utf-8")
    except Exception as exception:
        return [f"Failed to write the ontology to {pth}: {exception}"]

    ##
    # Render to DOT
    ##

    pth = scenarios_dir / "ontology.dot"

    for node in nodes:
        assert (
            " " not in node["url"]
        ), f"Unexpected double quote in the URL of a node: {node['url']}"

    ontology_dot = rasaeco.template.ONTOLOGY_DOT_TPL.render(
        dataset=dataset, dumps=json.dumps
    )

    try:
        pth.write_text(ontology_dot, encoding="utf-8")
    except Exception as exception:
        return [f"Failed to write the ontology to {pth}: {exception}"]

    return []


def _render_volumetric_plot(
    plot_path: pathlib.Path,
    plot_thumbnail_path: pathlib.Path,
    scenario: rasaeco.model.Scenario,
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

    # Large volumetric
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
            plt.savefig(str(plot_path), pad_inches=0)
        except Exception as exception:
            return [f"Failed to save the volumetric plot to {plot_path}: {exception}"]
    finally:
        plt.close(fig)

    # Thumbnail
    fig = plt.figure()
    try:
        ax = fig.gca(projection="3d")

        if voxels is not None:
            ax.voxels(voxels, edgecolor="k")

        # No tick labels
        ax.set_xticks(list(range(len(rasaeco.model.PHASES) + 1)))
        ax.set_xticklabels([""] * (len(rasaeco.model.PHASES) + 1))

        ax.set_yticks(list(range(len(rasaeco.model.LEVELS) + 1)))
        ax.set_yticklabels([""] * (len(rasaeco.model.LEVELS) + 1))

        ax.set_zticks(range(len(rasaeco.model.ASPECTS) + 1))
        ax.set_zticklabels([""] * (len(rasaeco.model.ASPECTS) + 1))

        ax.set_xlabel("Phases", color="green", fontsize=25)
        ax.set_ylabel("Levels", color="red", fontsize=25)
        ax.set_zlabel("Aspects", color="blue", fontsize=25)

        try:
            plt.savefig(str(plot_thumbnail_path))
        except Exception as exception:
            return [f"Failed to save the volumetric plot to {plot_path}: {exception}"]
    finally:
        plt.close(fig)

    # Crop and resize manually
    if plot_path.suffix.lower() == ".png":
        with PIL.Image.open(plot_path) as image:
            # left, upper, right, lower
            image_crop = image.crop((139, 86, 567, 450))
            image_crop.save(plot_path)
    elif plot_path.suffix.lower() == ".svg":
        svg_text = plot_path.read_text(encoding="utf-8")

        # This is hacky, but gets the job done.
        # If matplotlib ever changes the SVG export, this will break.
        original_marker = (
            '<svg height="345.6pt" version="1.1" viewBox="0 0 460.8 345.6" '
            'width="460.8pt" xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
        )

        if original_marker not in svg_text:
            return [
                f"The SVG exported by matplotlib had unexpected structure. "
                f"Please create a GitHub issue and send the content "
                f"of the file: {plot_path}"
            ]

        replacement = (
            '<svg height="255" version="1.1" viewBox="103 61.554 300.49 263.392" '
            'width="300" xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
        )
        svg_text = svg_text.replace(original_marker, replacement)

        plot_path.write_text(svg_text, encoding="utf-8")
    else:
        raise NotImplementedError(f"Cropping and resizing of plot path: {plot_path}")

    # Crop and resize manually
    if plot_thumbnail_path.suffix.lower() == ".png":
        with PIL.Image.open(plot_thumbnail_path) as image:
            # left, upper, right, lower
            with image.crop((139, 86, 567, 450)) as image_crop:
                new_size = (round(143 * 0.5), round(121 * 0.5))
                with image_crop.resize(new_size) as image_resized:
                    image_resized.save(plot_thumbnail_path)
    elif plot_thumbnail_path.suffix.lower() == ".svg":
        svg_text = plot_thumbnail_path.read_text(encoding="utf-8")

        # This is hacky, but gets the job done.
        # If matplotlib ever changes the SVG export, this will break.
        original_marker = (
            '<svg height="345.6pt" version="1.1" viewBox="0 0 460.8 345.6" '
            'width="460.8pt" xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
        )

        if original_marker not in svg_text:
            return [
                f"The SVG exported by matplotlib had unexpected structure. "
                f"Please create a GitHub issue and send the content "
                f"of the file: {plot_thumbnail_path}"
            ]

        replacement = (
            '<svg height="75" version="1.1" viewBox="114.314 57.873 294.953 266.05" '
            'width="100" '
            'xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">'
        )
        svg_text = svg_text.replace(original_marker, replacement)

        plot_thumbnail_path.write_text(svg_text, encoding="utf-8")

    return []


def _new_element(
    tag: str,
    text: Optional[str] = None,
    attrib: Optional[Dict[str, str]] = None,
    tail: Optional[str] = None,
    children: Optional[List[ET.Element]] = None,
) -> ET.Element:
    """Create an element with text."""
    result = ET.Element(tag)
    result.text = text

    if attrib is not None:
        result.attrib = attrib

    if tail is not None:
        result.tail = tail

    if children is not None:
        for child in children:
            result.append(child)

    return result


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
        scenario_id, ref = rasaeco.et.parse_reference_element(element=element)

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
        lambda reference_tag: reference_tag in ["modelref", "testref", "acceptanceref"]
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
            scenario_id, name = rasaeco.et.parse_reference_element(element=element)

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
    # Convert <scenarioref>s to links
    ##

    for element in root.iter("scenarioref"):
        scenario_id = element.attrib["name"]

        target_scenario = ontology.scenario_map[scenario_id]

        href = _html_path(
            scenario_path=rel_pth_to_scenario_dir / target_scenario.relative_path
        ).as_posix()

        element.tag = "a"
        element.attrib = {"href": href, "class": "scenarioref"}

        if len(element) == 0 and not element.text:
            element.text = f'"{target_scenario.title}"'

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

        # Assume that paragraphs are rendered as <p> from markdown to html.
        contains_paragraph = False if next(element.iter("p"), None) is None else True

        element.tag = "span" if not contains_paragraph else "div"
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

        # Assume that paragraphs are rendered as <p> from markdown to html.
        contains_paragraph = False if next(element.iter("p"), None) is None else True

        element.tag = "span" if not contains_paragraph else "div"
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
                f"{rasaeco.et.to_str(element)} with text {element.text}"
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
        
                span.phase, div.phase {
                    background-color: #eefbfb;
                }
        
                span.level, div.level {
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
            li.append(_new_element("span", f"{scenario.title} → {relation.nature} → "))

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
        main_div.insert(0, _new_element(tag="h2", text="Relations to Other Scenarios"))

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
            li.append(_new_element("span", f" ← {relation.nature} ← {scenario.title}"))

            ul.append(li)

        main_div.insert(0, ul)
        main_div.insert(
            0, _new_element(tag="h2", text="Relations from Other Scenarios")
        )

    ##
    # Insert volumetric plot
    ##

    index_div.insert(
        0,
        _new_element(
            "p",
            children=[
                _new_element(
                    "img",
                    attrib={
                        "src": "volumetric.svg",
                        "style": "border: 1px solid #EEEEEE; padding: "
                        "10px; margin: 0px;",
                    },
                )
            ],
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


PathT = TypeVar("PathT", pathlib.Path, pathlib.PurePosixPath)


def _html_path(scenario_path: PathT) -> PathT:
    """Generate the corresponding path of the HTML representation."""
    return scenario_path.parent / (scenario_path.stem + ".html")


def once(scenarios_dir: pathlib.Path) -> List[str]:
    """
    Render the scenarios and the ontology.

    Return errors if any.
    """
    errors = rasaeco.intermediate.render_scenarios_to_xml(scenarios_dir=scenarios_dir)
    if errors:
        return errors

    ontology, errors = rasaeco.intermediate.load_ontology(scenarios_dir=scenarios_dir)
    if errors:
        return errors

    assert ontology is not None

    for scenario in ontology.scenarios:
        for suffix in [".png", ".svg"]:
            plot_pth = (
                scenarios_dir / scenario.relative_path.parent / f"volumetric{suffix}"
            )

            plot_thumbnail_pth = (
                scenarios_dir
                / scenario.relative_path.parent
                / f"volumetric_thumb{suffix}"
            )

            _render_volumetric_plot(
                plot_path=plot_pth,
                plot_thumbnail_path=plot_thumbnail_pth,
                scenario=scenario,
            )

    _render_ontology_html(ontology=ontology, scenarios_dir=scenarios_dir)

    for scenario in ontology.scenarios:
        pth = scenarios_dir / scenario.relative_path

        render_errors = _render_scenario(
            scenario=scenario,
            ontology=ontology,
            xml_path=rasaeco.intermediate.as_xml_path(pth),
            html_path=_html_path(pth),
        )

        for error in render_errors:
            errors.append(f"When rendering {pth}: {error}")

    if errors:
        return errors

    return []
