"""Extract meta information from a scenario markdown."""
import json
import re
from typing import List, Tuple, Optional, Any, TypedDict

import typeguard


class RelatesTo(TypedDict):
    """Represent a relates-to link from a scenario."""

    target: str
    nature: str


class Cubelet(TypedDict):
    """Represent a cubelet in the scenario space."""

    aspect_from: str
    aspect_to: str
    phase_from: str
    phase_to: str
    level_from: str
    level_to: str


class Meta(TypedDict):
    """Represent meta information extracted from a scenario markdown."""

    identifier: str
    title: str
    relations: List[RelatesTo]
    volumetric: List[Cubelet]


_META_OPEN_RE = re.compile("<\s*rasaeco-meta( [^>]*)?>")
_META_CLOSE_RE = re.compile("<\s*/\s*rasaeco-meta\s*>")


def extract_meta(text: str) -> Tuple[Optional[Meta], List[str]]:
    """Extract meta information from the given markdown."""
    mtch = re.search(_META_OPEN_RE, text)
    if mtch is None:
        return None, ["No opening <rasaeco-meta> could be found."]

    meta_start = mtch.end()

    mtch = re.search(_META_CLOSE_RE, text)
    if mtch is None:
        return None, ["No closing </rasaeco-meta> could be found."]

    meta_end = mtch.start()

    if meta_start > meta_end:
        return None, ["Opening <rasaeco-meta> comes after closing </rasaeco-meta>."]

    meta_lineno = 0
    for i in range(0, meta_start):
        if text[i] == "\n":
            meta_lineno += 1

    meta_text = text[meta_start:meta_end]

    data = None  # type: Optional[Any]
    try:
        data = json.loads(meta_text)
    except json.decoder.JSONDecodeError as error:
        lineno = error.lineno + meta_lineno
        return None, [
            f"Failed to parse the JSON in <rasaeco-meta> at line {lineno}: {error.msg}"
        ]

    try:
        typeguard.check_type(argname="meta", value=data, expected_type=Meta)
    except TypeError as error:
        return None, [f"Failed to parse JSON rasaeco-meta data: {error}"]

    return data, []
