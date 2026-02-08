"""Historical dedup cleanup planner and executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tw_homedog.dedup import (
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_PRICE_TOLERANCE,
    DEFAULT_SIZE_TOLERANCE,
    build_entity_fingerprint,
    choose_canonical_listing,
    score_duplicate,
)
from tw_homedog.storage import Storage


@dataclass
class CleanupPlan:
    entity_fingerprint: str
    canonical_listing_id: str
    duplicate_listing_ids: list[str]
    score: float
    reason: str

    @property
    def total_records(self) -> int:
        return 1 + len(self.duplicate_listing_ids)


def _connected_components(
    listings: list[dict],
    *,
    threshold: float,
    price_tolerance: float,
    size_tolerance: float,
) -> list[list[dict]]:
    if len(listings) <= 1:
        return [listings]

    n = len(listings)
    adj: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            score = score_duplicate(
                listings[i],
                listings[j],
                price_tolerance=price_tolerance,
                size_tolerance=size_tolerance,
            )
            if score.score >= threshold:
                adj[i].add(j)
                adj[j].add(i)

    seen = [False] * n
    groups: list[list[dict]] = []
    for i in range(n):
        if seen[i]:
            continue
        stack = [i]
        component: list[dict] = []
        while stack:
            idx = stack.pop()
            if seen[idx]:
                continue
            seen[idx] = True
            component.append(listings[idx])
            stack.extend(adj[idx])
        groups.append(component)
    return groups


def plan_cleanup(
    storage: Storage,
    *,
    source: str = "591",
    threshold: float = DEFAULT_DEDUP_THRESHOLD,
    price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
    size_tolerance: float = DEFAULT_SIZE_TOLERANCE,
) -> list[CleanupPlan]:
    plans: list[CleanupPlan] = []
    bucketed: dict[str, list[dict]] = {}
    for listing in storage.get_all_listings(source=source):
        fingerprint = build_entity_fingerprint(listing)
        if not fingerprint:
            continue
        bucketed.setdefault(fingerprint, []).append(listing)

    for fingerprint, listings in bucketed.items():
        if len(listings) < 2:
            continue
        for component in _connected_components(
            listings,
            threshold=threshold,
            price_tolerance=price_tolerance,
            size_tolerance=size_tolerance,
        ):
            if len(component) <= 1:
                continue
            ids = [str(x["listing_id"]) for x in component]
            relation_counts = storage.get_relation_counts(source, ids)
            canonical = choose_canonical_listing(component, relation_counts)
            canonical_id = str(canonical["listing_id"])
            duplicates = [str(x["listing_id"]) for x in component if str(x["listing_id"]) != canonical_id]
            if not duplicates:
                continue

            top_score = 0.0
            top_reason = "cleanup"
            for item in component:
                lid = str(item["listing_id"])
                if lid == canonical_id:
                    continue
                scored = score_duplicate(
                    canonical,
                    item,
                    price_tolerance=price_tolerance,
                    size_tolerance=size_tolerance,
                )
                if scored.score >= top_score:
                    top_score = scored.score
                    top_reason = scored.reason

            plans.append(
                CleanupPlan(
                    entity_fingerprint=fingerprint,
                    canonical_listing_id=canonical_id,
                    duplicate_listing_ids=duplicates,
                    score=round(top_score, 4),
                    reason=top_reason,
                )
            )
    return plans


def run_cleanup(
    storage: Storage,
    *,
    source: str = "591",
    dry_run: bool = True,
    threshold: float = DEFAULT_DEDUP_THRESHOLD,
    price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
    size_tolerance: float = DEFAULT_SIZE_TOLERANCE,
    batch_size: int = 200,
) -> dict[str, Any]:
    """Execute or preview historical cleanup."""
    plans = plan_cleanup(
        storage,
        source=source,
        threshold=threshold,
        price_tolerance=price_tolerance,
        size_tolerance=size_tolerance,
    )
    plans = plans[: max(batch_size, 1)]

    report: dict[str, Any] = {
        "dry_run": dry_run,
        "source": source,
        "threshold": threshold,
        "price_tolerance": price_tolerance,
        "size_tolerance": size_tolerance,
        "batch_size": batch_size,
        "groups": len(plans),
        "projected_merge_records": sum(len(p.duplicate_listing_ids) for p in plans),
        "merged_groups": 0,
        "merged_records": 0,
        "cleanup_failed": 0,
        "plans": [
            {
                "entity_fingerprint": p.entity_fingerprint,
                "canonical_listing_id": p.canonical_listing_id,
                "duplicate_listing_ids": p.duplicate_listing_ids,
                "score": p.score,
                "reason": p.reason,
            }
            for p in plans
        ],
        "validation": {},
        "guidance": (
            "Use conservative batch sizes (<=200), keep each merge group in a single DB transaction, "
            "and rerun in dry-run mode before each threshold change."
        ),
    }

    if dry_run:
        return report

    for plan in plans:
        try:
            merged = storage.merge_duplicate_group(
                source=source,
                canonical_listing_id=plan.canonical_listing_id,
                duplicate_listing_ids=plan.duplicate_listing_ids,
                score=plan.score,
                reason=f"cleanup:{plan.reason}",
                entity_fingerprint=plan.entity_fingerprint,
            )
            report["merged_groups"] += 1 if merged > 0 else 0
            report["merged_records"] += merged
        except Exception:
            report["cleanup_failed"] += 1

    report["validation"] = storage.validate_relation_integrity()
    return report
