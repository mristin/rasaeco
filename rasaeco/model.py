"""Represent an ontology of scenarios."""
import dataclasses
import pathlib
from typing import Optional, List, MutableMapping, Mapping, cast, Dict, Set

import icontract

ASPECTS = [
    "as-planned",
    "as-observed",
    "divergence",
    "scheduling",
    "cost",
    "safety",
    "analytics",
]
ASPECT_SET = set(ASPECTS)


def verify_aspect_range(first: str, last: str) -> Optional[str]:
    """
    Verify that the aspect range is correct.

    Return error if any.
    """
    if first not in ASPECT_SET:
        return f"Unexpected start of an aspect range: {first!r}; possible aspects are: {ASPECTS}"

    if last not in ASPECT_SET:
        return f"Unexpected end of an aspect range: {last!r}; possible aspects are: {ASPECTS}"

    i = ASPECTS.index(first)
    j = ASPECTS.index(last)
    if i > j:
        return f"Invalid aspect range: {first!r} comes after {last!r}."

    return None


class AspectRange:
    """Represent a range over aspect in the scenario space."""

    @icontract.require(lambda first, last: verify_aspect_range(first, last) is None)
    def __init__(self, first: str, last: str) -> None:
        """Initialize with the given values."""
        self.first = first
        self.last = last


PHASES = ["planning", "construction", "operation", "renovation", "demolition"]
PHASE_SET = set(PHASES)


def verify_phase_range(first: str, last: str) -> Optional[str]:
    """
    Verify that the phase range is correct.

    Return error if any.
    """
    if first not in PHASE_SET:
        return f"Unexpected start of a phase range: {first!r}; possible phases are: {PHASES}"

    if last not in PHASE_SET:
        return (
            f"Unexpected end of a phase range: {last!r}; possible phases are: {PHASES}"
        )

    i = PHASES.index(first)
    j = PHASES.index(last)
    if i > j:
        return f"Invalid phase range: {first!r} comes after {last!r}."

    return None


class PhaseRange:
    """Represent a range over phase in the scenario space."""

    @icontract.require(lambda first, last: verify_phase_range(first, last) is None)
    def __init__(self, first: str, last: str) -> None:
        """Initialize with the given values."""
        self.first = first
        self.last = last


LEVELS = ["device", "machine", "zone", "site", "office", "company", "network"]
LEVEL_SET = set(LEVELS)


def verify_level_range(first: str, last: str) -> Optional[str]:
    """
    Verify that the level range is correct.

    Return error if any.
    """
    if first not in LEVEL_SET:
        return f"Unexpected start of a level range: {first!r}; possible levels are: {LEVELS}"

    if last not in LEVEL_SET:
        return (
            f"Unexpected end of a level range: {last!r}; possible levels are: {LEVELS}"
        )

    i = LEVELS.index(first)
    j = LEVELS.index(last)
    if i > j:
        return f"Invalid level range: {first!r} comes after {last!r}."

    return None


class LevelRange:
    """Represent a range over level in the scenario space."""

    @icontract.require(lambda first, last: verify_level_range(first, last) is None)
    def __init__(self, first: str, last: str) -> None:
        """Initialize with the given values."""
        self.first = first
        self.last = last


class Cubelet:
    """Represent a cubelet in the scenario space."""

    def __init__(
        self,
        aspect_range: AspectRange,
        phase_range: PhaseRange,
        level_range: LevelRange,
    ) -> None:
        """Initialize with the given values."""
        self.aspect_range = aspect_range
        self.phase_range = phase_range
        self.level_range = level_range


class Relation:
    """Represent a directed relation between two scenarios."""

    def __init__(self, source: str, target: str, nature: str) -> None:
        """Initialize with the given values."""
        self.source = source
        self.target = target
        self.nature = nature


@dataclasses.dataclass
class Definitions:
    """Represent definitions in a scenario such as model set and definition set."""

    model_set: Set[str]
    def_set: Set[str]
    test_set: Set[str]
    acceptance_set: Set[str]


class Scenario:
    """Represent a working model of a scenario."""

    @icontract.require(lambda relative_path: not relative_path.is_absolute())
    def __init__(
        self,
        identifier: str,
        title: str,
        contact: str,
        volumetric: List[Cubelet],
        definitions: Definitions,
        relative_path: pathlib.Path,
    ) -> None:
        """Initialize with the given values."""
        self.identifier = identifier
        self.title = title
        self.contact = contact
        self.volumetric = volumetric
        self.definitions = definitions
        self.relative_path = relative_path


class Ontology:
    """Represent the whole ontology of the scenarios."""

    @icontract.require(
        lambda scenarios, relations: (
            scenario_id_set := {s.identifier for s in scenarios},
            all(r.source in scenario_id_set for r in relations)
            and all(r.target in scenario_id_set for r in relations),
        )
    )
    def __init__(self, scenarios: List[Scenario], relations: List[Relation]) -> None:
        """Initialize with the given values."""
        self.scenarios = scenarios
        self.scenario_map = {
            s.identifier: s for s in scenarios
        }  # type: Dict[str, Scenario]

        relations_from = dict()  # type: MutableMapping[Scenario, List[Relation]]
        relations_to = dict()  # type: MutableMapping[Scenario, List[Relation]]
        for relation in relations:
            source = self.scenario_map[relation.source]
            target = self.scenario_map[relation.target]

            if source not in relations_from:
                relations_from[source] = []
            relations_from[source].append(relation)

            if target not in relations_to:
                relations_to[target] = []
            relations_to[target].append(relation)

        self.relations = relations
        self.relations_from = cast(Mapping[Scenario, List[Relation]], relations_from)
        self.relations_to = cast(Mapping[Scenario, List[Relation]], relations_to)
