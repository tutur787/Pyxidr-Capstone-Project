"""
FABN Agent - Capability: Asset Contribution Analysis
Business question: "Which assets contribute the most to portfolio income / RBC?"

Input: bond-level optimizer output (CSV or list of dicts) with columns:
    CUSIP, Sector, Rating, h_opt_usd, book_yield_pct, spread_bps,
    duration_yrs, rbc_factor_pct

This module is pure computation (no LLM calls). It is intended to be wired up
as a tool/function the agent calls, with the LLM only used for the final
narrative synthesis step.

Validation note: total rbc_contrib computed here should reconcile to the
optimizer's summary `rbc_usd` field. If it doesn't, the bond-level file and
the summary are out of sync and the agent should flag that rather than answer.
"""

from dataclasses import dataclass, field
from typing import Iterable

# Threshold (in percentage points) for flagging a group's RBC or income share
# as disproportionate relative to its portfolio weight. Currently an eyeballed
# judgment call per business decision (2026-06-30) -- revisit if flags feel
# too noisy or too quiet in practice.
FLAG_THRESHOLD_PCT = 5.0

TOP_N_CUSIPS = 10


@dataclass
class BondRow:
    cusip: str
    sector: str
    rating: str
    h_opt_usd: float
    book_yield_pct: float
    spread_bps: float
    duration_yrs: float
    rbc_factor_pct: float

    @property
    def income_usd(self) -> float:
        return self.h_opt_usd * self.book_yield_pct / 100

    @property
    def rbc_contrib_usd(self) -> float:
        return self.h_opt_usd * self.rbc_factor_pct / 100


@dataclass
class GroupSummary:
    group: str
    count: int
    h_usd: float
    weight_pct: float
    income_usd: float
    income_share_pct: float
    rbc_usd: float
    rbc_share_pct: float

    @property
    def income_flag(self) -> bool:
        return abs(self.income_share_pct - self.weight_pct) >= FLAG_THRESHOLD_PCT

    @property
    def rbc_flag(self) -> bool:
        return abs(self.rbc_share_pct - self.weight_pct) >= FLAG_THRESHOLD_PCT


@dataclass
class ContributionAnalysisResult:
    optimization_date: str
    total_h_usd: float
    total_income_usd: float
    total_rbc_usd: float
    holding_count: int
    by_sector: list[GroupSummary]
    by_rating: list[GroupSummary]
    top_cusips_by_rbc: list[BondRow]
    top_cusips_by_income: list[BondRow]
    reconciliation_warning: str | None = None


def load_bond_rows(records: Iterable[dict]) -> list[BondRow]:
    """Convert raw dict rows (e.g. from csv.DictReader) into BondRow objects."""
    rows = []
    for r in records:
        rows.append(
            BondRow(
                cusip=r["CUSIP"],
                sector=r["Sector"],
                rating=r["Rating"],
                h_opt_usd=float(r["h_opt_usd"]),
                book_yield_pct=float(r["book_yield_pct"]),
                spread_bps=float(r["spread_bps"]),
                duration_yrs=float(r["duration_yrs"]),
                rbc_factor_pct=float(r["rbc_factor_pct"]),
            )
        )
    return rows


def _rollup(rows: list[BondRow], key: str, total_h: float, total_income: float, total_rbc: float) -> list[GroupSummary]:
    groups: dict[str, list[BondRow]] = {}
    for r in rows:
        groups.setdefault(getattr(r, key), []).append(r)

    summaries = []
    for group_name, group_rows in groups.items():
        h = sum(r.h_opt_usd for r in group_rows)
        income = sum(r.income_usd for r in group_rows)
        rbc = sum(r.rbc_contrib_usd for r in group_rows)
        summaries.append(
            GroupSummary(
                group=group_name,
                count=len(group_rows),
                h_usd=h,
                weight_pct=h / total_h * 100,
                income_usd=income,
                income_share_pct=income / total_income * 100,
                rbc_usd=rbc,
                rbc_share_pct=rbc / total_rbc * 100,
            )
        )
    summaries.sort(key=lambda g: -g.rbc_share_pct)
    return summaries


def analyze_contributions(
    records: Iterable[dict],
    optimization_date: str,
    optimizer_summary_rbc_usd: float | None = None,
    reconciliation_tolerance_usd: float = 1.0,
) -> ContributionAnalysisResult:
    """
    Main entry point. Computes sector and rating rollups plus top CUSIP
    contributors, from raw bond-level optimizer output.

    If optimizer_summary_rbc_usd is provided, validates that bond-level RBC
    sums to the optimizer's reported summary RBC (within tolerance), and
    surfaces a warning if not -- this is a data-integrity check the agent
    should run before answering, not something to silently ignore.
    """
    rows = load_bond_rows(records)

    total_h = sum(r.h_opt_usd for r in rows)
    total_income = sum(r.income_usd for r in rows)
    total_rbc = sum(r.rbc_contrib_usd for r in rows)

    reconciliation_warning = None
    if optimizer_summary_rbc_usd is not None:
        diff = abs(total_rbc - optimizer_summary_rbc_usd)
        if diff > reconciliation_tolerance_usd:
            reconciliation_warning = (
                f"Bond-level RBC sum (${total_rbc:,.2f}) does not match optimizer "
                f"summary rbc_usd (${optimizer_summary_rbc_usd:,.2f}); "
                f"difference of ${diff:,.2f}. Data may be out of sync."
            )

    by_sector = _rollup(rows, "sector", total_h, total_income, total_rbc)
    by_rating = _rollup(rows, "rating", total_h, total_income, total_rbc)

    top_cusips_by_rbc = sorted(rows, key=lambda r: -r.rbc_contrib_usd)[:TOP_N_CUSIPS]
    top_cusips_by_income = sorted(rows, key=lambda r: -r.income_usd)[:TOP_N_CUSIPS]

    return ContributionAnalysisResult(
        optimization_date=optimization_date,
        total_h_usd=total_h,
        total_income_usd=total_income,
        total_rbc_usd=total_rbc,
        holding_count=len(rows),
        by_sector=by_sector,
        by_rating=by_rating,
        top_cusips_by_rbc=top_cusips_by_rbc,
        top_cusips_by_income=top_cusips_by_income,
        reconciliation_warning=reconciliation_warning,
    )


def to_agent_context(result: ContributionAnalysisResult) -> dict:
    """
    Serializes the result into a plain dict suitable for passing to the LLM
    as context for narrative synthesis (the only step that should involve
    an LLM call). Keeping this separate from the dataclasses above makes it
    easy to swap in a different prompt/synthesis layer later.
    """
    return {
        "optimization_date": result.optimization_date,
        "total_allocated_usd": round(result.total_h_usd, 2),
        "total_income_usd": round(result.total_income_usd, 2),
        "total_rbc_usd": round(result.total_rbc_usd, 2),
        "holding_count": result.holding_count,
        "reconciliation_warning": result.reconciliation_warning,
        "by_sector": [
            {
                "sector": g.group,
                "count": g.count,
                "weight_pct": round(g.weight_pct, 1),
                "income_share_pct": round(g.income_share_pct, 1),
                "rbc_share_pct": round(g.rbc_share_pct, 1),
                "flagged": g.rbc_flag or g.income_flag,
            }
            for g in result.by_sector
        ],
        "by_rating": [
            {
                "rating": g.group,
                "count": g.count,
                "weight_pct": round(g.weight_pct, 1),
                "income_share_pct": round(g.income_share_pct, 1),
                "rbc_share_pct": round(g.rbc_share_pct, 1),
                "flagged": g.rbc_flag or g.income_flag,
            }
            for g in result.by_rating
        ],
        "top_cusips_by_rbc": [
            {
                "cusip": r.cusip,
                "sector": r.sector,
                "rating": r.rating,
                "h_opt_usd": round(r.h_opt_usd, 2),
                "rbc_contrib_usd": round(r.rbc_contrib_usd, 2),
                "income_usd": round(r.income_usd, 2),
            }
            for r in result.top_cusips_by_rbc
        ],
        "top_cusips_by_income": [
            {
                "cusip": r.cusip,
                "sector": r.sector,
                "rating": r.rating,
                "h_opt_usd": round(r.h_opt_usd, 2),
                "income_usd": round(r.income_usd, 2),
                "rbc_contrib_usd": round(r.rbc_contrib_usd, 2),
            }
            for r in result.top_cusips_by_income
        ],
    }


if __name__ == "__main__":
    # Smoke test using a small inline sample. Replace with real CSV loading
    # (csv.DictReader against the optimizer's bond-level output file) when
    # wiring this into the actual agent.
    import csv
    import io
    import json

    sample_path = "sample_bond_data.csv"
    with open(sample_path) as f:
        records = list(csv.DictReader(f))

    result = analyze_contributions(
        records,
        optimization_date="2025-06-20",
        optimizer_summary_rbc_usd=5281702.97,
    )

    print(json.dumps(to_agent_context(result), indent=2))
