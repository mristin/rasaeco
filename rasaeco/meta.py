"""Extract meta information from a scenario markdown."""
import dataclasses
import json
import re
from typing import List, Tuple, Optional, Any, TypedDict

import icontract
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


class Range:
    """Represent a range of text encompassing the meta tag."""

    @icontract.require(
        lambda block_start, text_start, text_end, block_end: block_start
        < text_start
        < text_end
        < block_end
    )
    def __init__(
        self, block_start: int, text_start: int, text_end: int, block_end: int
    ) -> None:
        """Initialize with the given values."""
        self.block_start = block_start
        self.text_start = text_start
        self.text_end = text_end
        self.block_end = block_end


def find_meta(text: str) -> Tuple[Optional[Range], List[str]]:
    """
    Find the meta block in the file.

    Return (range, errors if any).
    """
    mtch = re.search(_META_OPEN_RE, text)
    if mtch is None:
        return None, ["No opening <rasaeco-meta> could be found."]

    block_start = mtch.start()
    text_start = mtch.end()

    mtch = re.search(_META_CLOSE_RE, text)
    if mtch is None:
        return None, ["No closing </rasaeco-meta> could be found."]

    text_end = mtch.start()
    block_end = mtch.end()

    if block_start > block_end:
        return None, ["Opening <rasaeco-meta> comes after closing </rasaeco-meta>."]

    return (
        Range(
            block_start=block_start,
            text_start=text_start,
            text_end=text_end,
            block_end=block_end,
        ),
        [],
    )


def extract_meta(text: str) -> Tuple[Optional[Meta], List[str]]:
    """Extract meta information from the given markdown."""
    meta_range, errors = find_meta(text=text)
    if errors:
        return None, errors

    assert meta_range is not None

    meta_lineno = 0
    for i in range(0, meta_range.block_start):
        if text[i] == "\n":
            meta_lineno += 1

    meta_text = text[meta_range.text_start : meta_range.text_end]

    data = None  # type: Optional[Any]
    try:
        data = json.loads(meta_text)
    except json.decoder.JSONDecodeError as error:
        lineno = error.lineno + meta_lineno

        lines = [
            f"Failed to parse the JSON in <rasaeco-meta> at line {lineno}: {error.msg}"
        ]

        for i, line in enumerate(meta_text.splitlines()):
            if i == lineno - 1:
                lines.append(f"ERROR {i + 1:3d}: {line}")
            else:
                lines.append(f"      {i + 1:3d}: {line}")

        return None, ["\n".join(lines)]

    try:
        typeguard.check_type(argname="meta", value=data, expected_type=Meta)
    except TypeError as error:
        return None, [f"Failed to parse JSON rasaeco-meta data: {error}"]

    return data, []
