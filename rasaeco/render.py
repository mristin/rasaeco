"""Process the scenario files to obtain the ontology and render it as HTML."""
import dataclasses
import itertools
import json
import pathlib
import textwrap
import uuid
import xml.etree.ElementTree as ET
from typing import List, MutableMapping, Mapping, TypedDict

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
    except Exception as error:
        return [f"Failed to write the ontology to {pth}: {error}"]

    return []


def _render_volumetric_plot(
    plot_path: pathlib.Path, scenario: rasaeco.model.Scenario
) -> List[str]:
    """
    Render the 3D volumetric plot and store it as an image.

    Return errors if any.
    """
    # Prepare some coordinates
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

    # and plot everything
    fig = plt.figure()
    ax = fig.gca(projection="3d")
    ax.voxels(voxels, edgecolor="k")

    ax.set_xticks(list(range(len(rasaeco.model.PHASES) + 1)))
    ax.set_xticklabels([""] * (len(rasaeco.model.PHASES) + 1))

    for i, phase in enumerate(rasaeco.model.PHASES):
        ax.text(i + 0.5, -3.5, 0, phase, color="green", fontsize=8, zdir="y")

    ax.set_yticks(list(range(len(rasaeco.model.LEVELS) + 1)))
    ax.set_yticklabels([""] * (len(rasaeco.model.LEVELS) + 1))

    for i, level in enumerate(rasaeco.model.LEVELS):
        ax.text(len(rasaeco.model.PHASES) + 0.7, i, 0, level, color="red", fontsize=8)

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
    except Exception as error:
        return [f"Failed to save the volumetric plot to: {plot_path}"]

    # Crop manually
    with PIL.Image.open(plot_path) as image:
        # left, upper, right, lower
        image_crop = image.crop((141, 86, 567, 446))
        image_crop.save(plot_path)

    return []


@icontract.require(lambda scenario_path: scenario_path.suffix == ".md")
def _render_scenario(
    scenario: rasaeco.model.Scenario,
    scenario_path: pathlib.Path,
    scenarios_dir: pathlib.Path,
) -> List[str]:
    """Render a single scenario as HTML."""
    try:
        text = scenario_path.read_text(encoding="utf-8")
    except Exception as error:
        return [f"Failed to read the scenario {scenario_path}: {error}"]

    try:
        document = marko.convert(text)
    except Exception as error:
        return [
            f"Failed to convert the scenario markdown {scenario_path} to HTML: {error}"
        ]

    html_text = f"<html>\n<body>\n{document}\n</body>\n</html>"

    root = ET.fromstring(html_text)

    ##
    # Remove <rasaeco-meta>
    ##

    body = root.find("body")
    assert body is not None

    meta = body.find("rasaeco-meta")
    assert meta is not None
    body.remove(meta)

    ##
    # Validate that all <def>, <ref>, <phase> and <level> have the name attribute
    ##

    for element in itertools.chain(
        root.iter("def"),
        root.iter("ref"),
        root.iter("model"),
        root.iter("modelref"),
        root.iter("phase"),
        root.iter("level"),
    ):
        if "name" not in element.attrib:
            return [f"A <{element.tag}> lacks the `name` attribute in: {scenario_path}"]

    # Replace <def> tags with proper HTML
    for element in root.iter("def"):
        anchor_name = element.attrib.get("name")

        # Transform
        element.tag = "div"
        element.attrib = {"class": "definition"}

        anchor_id = f"def-{anchor_name}"

        link_el = ET.Element("a", attrib={"href": f"#{anchor_id}", "class": "anchor"})
        link_el.append(ET.Element("a", attrib={"id": anchor_id}))
        link_el.text = "🔗"
        link_el.tail = anchor_name

        heading_el = ET.Element("h3")
        heading_el.insert(0, link_el)

        element.insert(0, heading_el)

    # Replace <model> tags with proper HTML
    for element in root.iter("model"):
        anchor_name = element.attrib.get("name")

        # Transform
        element.tag = "div"
        element.attrib = {"class": "model"}

        heading_el = ET.Element("h3")
        heading_el.text = anchor_name

        anchor_id = f"model-{anchor_name}"

        link_el = ET.Element("a", attrib={"href": f"#{anchor_id}", "class": "anchor"})
        link_el.append(ET.Element("a", attrib={"id": anchor_id}))
        link_el.text = "🔗"
        link_el.tail = anchor_name

        heading_el = ET.Element("h3")
        heading_el.insert(0, link_el)

        element.insert(0, heading_el)

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
        body = next(root.iter("body"))

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
        body = next(root.iter("body"))

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
    # Insert back button
    ##

    back_link = ET.Element("a")

    back_url = "/".join(
        [".."] * len(scenario_path.parent.relative_to(scenarios_dir).parts)
        + ["ontology.html"]
    )

    back_link.attrib["href"] = back_url
    back_link.text = "Back to ontology"

    body = root.find("body")
    assert body is not None
    for i, child in enumerate(body):
        if child.tag == "h1":
            body.insert(i, back_link)
            break

    ##
    # Insert volumetric plot
    ##

    img = ET.Element("img")
    img.attrib["src"] = "volumetric.png"
    img.attrib["style"] = "border: 1px solid #EEEEEE; padding: 10px;"

    body = root.find("body")
    assert body is not None
    for i, child in enumerate(body):
        if child.tag == "h1":
            body.insert(i + 1, img)
            break

    ##
    # Save
    ##

    target_pth = scenario_path.parent / (scenario_path.stem + ".html")

    try:
        target_pth.write_bytes(ET.tostring(root, encoding="utf-8"))
    except Exception as error:
        return [f"Failed to write generated HTML code to {target_pth}: {error}"]

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

            if cubelet["aspect_from"] not in rasaeco.model.ASPECT_SET:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid start of an aspect range: {cubelet['aspect_from']}"
                )

            if cubelet["aspect_to"] not in rasaeco.model.ASPECT_SET:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid end of an aspect range: {cubelet['aspect_to']}"
                )

            aspect_range_error = rasaeco.model.verify_aspect_range(
                cubelet["aspect_from"], cubelet["aspect_to"]
            )
            if aspect_range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid aspect range: {aspect_range_error}"
                )

            ##
            # Verify phase range
            ##

            if cubelet["phase_from"] not in rasaeco.model.PHASE_SET:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid start of a phase range: {cubelet['phase_from']}"
                )

            if cubelet["phase_to"] not in rasaeco.model.PHASE_SET:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid end of a phase range: {cubelet['phase_to']}"
                )

            phase_range_error = rasaeco.model.verify_phase_range(
                cubelet["phase_from"], cubelet["phase_to"]
            )
            if phase_range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid phase range: {phase_range_error}"
                )
            ##
            # Verify level range
            ##

            if cubelet["level_from"] not in rasaeco.model.LEVEL_SET:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid start of a level range: {cubelet['level_from']}"
                )

            if cubelet["level_to"] not in rasaeco.model.LEVEL_SET:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid end of a level range: {cubelet['level_to']}"
                )

            level_range_error = rasaeco.model.verify_level_range(
                cubelet["level_from"], cubelet["level_to"]
            )
            if level_range_error:
                errors.append(
                    f"In file {pth} and cubelet {i + 1}: "
                    f"Invalid level range: {level_range_error}"
                )

        meta_map[meta["identifier"]] = meta
        path_map[meta["identifier"]] = pth

    scenario_id_set = set(meta_map.keys())

    for identifier, meta in meta_map.items():
        for relate_to in meta["relations"]:
            if relate_to["target"] not in scenario_id_set:
                errors.append(
                    f"In file {path_map[identifier]}: "
                    f"The relation f{relate_to['nature']} is invalid as the identifier "
                    f"of the target scenario can not be found: {relate_to['target']}"
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
            identifier=identifier, title=meta["title"], volumetric=volumetric
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
        _render_scenario(
            scenario=scenario,
            scenario_path=path_map[scenario.identifier],
            scenarios_dir=scenarios_dir,
        )

    return []
