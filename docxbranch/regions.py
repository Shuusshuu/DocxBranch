"""Build disjoint review regions from baseline-relative paragraph changes."""

from dataclasses import dataclass

from docxbranch.diff import Change, Comparison, changes_overlap


@dataclass(frozen=True)
class ReviewRegion:
    """Represent one connected component of potentially overlapping edits."""

    start: int
    end: int
    changes_a: tuple[Change, ...]
    changes_b: tuple[Change, ...]

    @property
    def is_conflict(self) -> bool:
        """Return whether both employees edit this connected region."""
        return bool(self.changes_a and self.changes_b)


def build_regions(comparison: Comparison) -> tuple[ReviewRegion, ...]:
    """Group cross-employee overlapping edits into review regions.

    Connected components are used so transitive overlaps cannot lead
    to multiple, contradictory decisions for the same affected area.
    Independent edits remain separate, including adjacent non-overlaps.
    """
    changes = [("A", change) for change in comparison.changes_a]
    changes.extend(("B", change) for change in comparison.changes_b)
    parent = list(range(len(changes)))

    def find(index: int) -> int:
        """Find the representative of a change component."""
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for left in range(len(changes)):
        for right in range(left + 1, len(changes)):
            if (changes[left][0] != changes[right][0]
                    and changes_overlap(changes[left][1], changes[right][1])):
                parent[find(right)] = find(left)

    components: dict[int, list[tuple[str, Change]]] = {}
    for index, item in enumerate(changes):
        components.setdefault(find(index), []).append(item)

    regions = []
    for component in components.values():
        regions.append(ReviewRegion(
            start=min(change.start for _, change in component),
            end=max(change.end for _, change in component),
            changes_a=tuple(change for source, change in component if source == "A"),
            changes_b=tuple(change for source, change in component if source == "B"),
        ))
    return tuple(sorted(regions, key=lambda region: (
        region.start, region.end,
        0 if region.is_conflict else 1,
        0 if region.changes_a else 1,
    )))
