"""Presentation grouping for QA findings; preserve evidence and individual locations."""

from collections import defaultdict


def group_findings(items: list[dict[str, str]]) -> list[dict]:
    groups = []
    positions = {}
    for item in items:
        # Only consolidate repeated compatibility warnings of the same kind.
        key = ("compatibility", item["title"]) if item["category"] == "compatibility" else None
        if key is None or key not in positions:
            group = {"item": item, "members": [item]}
            groups.append(group)
            if key is not None:
                positions[key] = len(groups) - 1
        else:
            groups[positions[key]]["members"].append(item)
    return groups
