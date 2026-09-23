from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from typing import Mapping

from .sampling import (
    GEOGRAPHY_FLOORS,
    SECTOR_TARGETS,
    ValidationCandidate,
    ValidationSelection,
)


def standard_sector_targets() -> dict[str, int]:
    return {code: target for code, _, target, _ in SECTOR_TARGETS}


def standard_geography_targets() -> dict[str, int]:
    return {code: target for code, _, target, _ in GEOGRAPHY_FLOORS}


@dataclass(frozen=True)
class ValidationFreezeDiagnostics:
    target_n: int
    unique_candidates: int
    sector_available: dict[str, int]
    geography_available: dict[str, int]
    sector_deficits: dict[str, int]
    geography_deficits: dict[str, int]
    max_joint_flow: int
    flow_gap: int
    jointly_feasible: bool


class ValidationFreezeError(ValueError):
    def __init__(self, diagnostics: ValidationFreezeDiagnostics):
        self.diagnostics = diagnostics
        super().__init__(
            "validation sample is not jointly feasible: "
            f"target={diagnostics.target_n}, "
            f"unique_candidates={diagnostics.unique_candidates}, "
            f"max_joint_flow={diagnostics.max_joint_flow}, "
            f"flow_gap={diagnostics.flow_gap}"
        )


class _Edge:
    __slots__ = ("to", "rev", "capacity", "original_capacity")

    def __init__(self, to: int, rev: int, capacity: int):
        self.to = to
        self.rev = rev
        self.capacity = capacity
        self.original_capacity = capacity


class _Dinic:
    def __init__(self, n: int):
        self.graph: list[list[_Edge]] = [[] for _ in range(n)]

    def add_edge(self, source: int, target: int, capacity: int) -> _Edge:
        forward = _Edge(target, len(self.graph[target]), capacity)
        reverse = _Edge(source, len(self.graph[source]), 0)
        self.graph[source].append(forward)
        self.graph[target].append(reverse)
        return forward

    def max_flow(self, source: int, sink: int) -> int:
        total = 0
        n = len(self.graph)

        while True:
            level = [-1] * n
            level[source] = 0
            queue: deque[int] = deque([source])
            while queue:
                node = queue.popleft()
                for edge in self.graph[node]:
                    if edge.capacity > 0 and level[edge.to] < 0:
                        level[edge.to] = level[node] + 1
                        queue.append(edge.to)
            if level[sink] < 0:
                return total

            progress = [0] * n

            def dfs(node: int, flow: int) -> int:
                if node == sink:
                    return flow
                while progress[node] < len(self.graph[node]):
                    edge = self.graph[node][progress[node]]
                    if edge.capacity > 0 and level[node] + 1 == level[edge.to]:
                        pushed = dfs(edge.to, min(flow, edge.capacity))
                        if pushed:
                            edge.capacity -= pushed
                            self.graph[edge.to][edge.rev].capacity += pushed
                            return pushed
                    progress[node] += 1
                return 0

            while True:
                pushed = dfs(source, 10**18)
                if not pushed:
                    break
                total += pushed


@dataclass(frozen=True)
class ValidationFreezePlan:
    selections: tuple[ValidationSelection, ...]
    cell_allocation: dict[tuple[str, str], int]
    diagnostics: ValidationFreezeDiagnostics


def _deduplicate(candidates: list[ValidationCandidate]) -> list[ValidationCandidate]:
    return sorted(
        {candidate.public_id: candidate for candidate in candidates}.values(),
        key=lambda candidate: candidate.public_id,
    )


def _validate_targets(
    sector_targets: Mapping[str, int],
    geography_targets: Mapping[str, int],
) -> int:
    if any(value < 0 for value in sector_targets.values()):
        raise ValueError("sector targets must be non-negative")
    if any(value < 0 for value in geography_targets.values()):
        raise ValueError("geography targets must be non-negative")
    sector_total = sum(sector_targets.values())
    geography_total = sum(geography_targets.values())
    if sector_total != geography_total:
        raise ValueError(
            "sector and geography targets must sum to the same validation total: "
            f"{sector_total} != {geography_total}"
        )
    return sector_total


def build_validation_freeze_plan(
    candidates: list[ValidationCandidate],
    *,
    sector_targets: Mapping[str, int] | None = None,
    geography_targets: Mapping[str, int] | None = None,
) -> ValidationFreezePlan:
    """Build an exact jointly constrained validation sample.

    The problem is represented as a bipartite max-flow network:
    source -> sector quotas -> observed sector×geography candidate cells ->
    geography quotas -> sink.

    A sample is frozen only when the maximum flow equals the full target. This
    prevents a sequential quota algorithm from meeting sector targets while silently
    breaking geography targets, or vice versa.
    """
    sector_targets = dict(sector_targets or standard_sector_targets())
    geography_targets = dict(geography_targets or standard_geography_targets())
    target_n = _validate_targets(sector_targets, geography_targets)

    unique = _deduplicate(candidates)
    sector_available = Counter(candidate.sector_family for candidate in unique)
    geography_available = Counter(candidate.geography_group for candidate in unique)

    sector_deficits = {
        code: max(0, target - sector_available.get(code, 0))
        for code, target in sector_targets.items()
        if sector_available.get(code, 0) < target
    }
    geography_deficits = {
        code: max(0, target - geography_available.get(code, 0))
        for code, target in geography_targets.items()
        if geography_available.get(code, 0) < target
    }

    sectors = list(sector_targets)
    geographies = list(geography_targets)
    source = 0
    sector_offset = 1
    geography_offset = sector_offset + len(sectors)
    sink = geography_offset + len(geographies)
    flow = _Dinic(sink + 1)

    sector_node = {code: sector_offset + i for i, code in enumerate(sectors)}
    geography_node = {code: geography_offset + i for i, code in enumerate(geographies)}

    for code, target in sector_targets.items():
        flow.add_edge(source, sector_node[code], target)
    for code, target in geography_targets.items():
        flow.add_edge(geography_node[code], sink, target)

    cells: dict[tuple[str, str], list[ValidationCandidate]] = {}
    for candidate in unique:
        if candidate.sector_family not in sector_targets:
            continue
        if candidate.geography_group not in geography_targets:
            continue
        cells.setdefault(
            (candidate.sector_family, candidate.geography_group),
            [],
        ).append(candidate)

    edge_refs: dict[tuple[str, str], _Edge] = {}
    for (sector, geography), members in sorted(cells.items()):
        edge_refs[(sector, geography)] = flow.add_edge(
            sector_node[sector],
            geography_node[geography],
            len(members),
        )

    max_joint_flow = flow.max_flow(source, sink)
    diagnostics = ValidationFreezeDiagnostics(
        target_n=target_n,
        unique_candidates=len(unique),
        sector_available=dict(sector_available),
        geography_available=dict(geography_available),
        sector_deficits=sector_deficits,
        geography_deficits=geography_deficits,
        max_joint_flow=max_joint_flow,
        flow_gap=max(0, target_n - max_joint_flow),
        jointly_feasible=max_joint_flow == target_n,
    )

    if not diagnostics.jointly_feasible:
        raise ValidationFreezeError(diagnostics)

    allocation: dict[tuple[str, str], int] = {}
    selections: list[ValidationSelection] = []
    for cell, edge in sorted(edge_refs.items()):
        used = edge.original_capacity - edge.capacity
        if used <= 0:
            continue
        allocation[cell] = used
        members = sorted(cells[cell], key=lambda candidate: candidate.public_id)
        for candidate in members[:used]:
            selections.append(ValidationSelection(candidate, "JOINT_QUOTA"))

    selections.sort(key=lambda item: item.candidate.public_id)
    if len(selections) != target_n:
        raise RuntimeError(
            f"internal freeze error: selected {len(selections)} records for target {target_n}"
        )

    return ValidationFreezePlan(tuple(selections), allocation, diagnostics)
