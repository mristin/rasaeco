"""Provide common operation on element trees."""

import xml.etree.ElementTree as ET
import xml.sax.saxutils
from typing import Tuple, Optional

import icontract


def to_str(element: ET.Element) -> str:
    """Dump the element to a string."""
    attribs_as_str = " ".join(
        f"{key}={xml.sax.saxutils.quoteattr(value)}"
        for key, value in element.attrib.items()
    )
    if attribs_as_str:
        return f"<{element.tag} {attribs_as_str}>"
    else:
        return f"<{element.tag}>"


@icontract.require(
    lambda element: element.tag in ["ref", "modelref", "testref", "acceptanceref"]
)
def parse_reference_element(element: ET.Element) -> Tuple[Optional[str], str]:
    """Extract the scenario identifier and the name from a reference element."""
    name_attribute = element.attrib["name"]
    if "#" in name_attribute:
        scenario_id, name = name_attribute.split("#", 1)
        return scenario_id, name
    else:
        return None, name_attribute
