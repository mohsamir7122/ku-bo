from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .event_factor_audit import audit_retrospective_csv, audit_retrospective_decisions
from .event_factor_common import (
    EventFactorPanelError,
    MATERIAL_RETURN_THRESHOLD_PCT,
    POST_EVENT_SESSIONS,
    PRE_EVENT_SESSIONS,
    PRODUCT_ID,
)
from .event_factor_packet import validate_event_factor_panel_packet
from .event_factor_study import (
    _event_metrics,
    evaluate_event_factor_panel,
    validate_event_factor_panel_result,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a sealed retrospective HUMANSOFT decision ledger. "
            "The output is aggregate-only and never a production accuracy claim."
        )
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audited-horizon-sessions", type=int, default=20)
    parser.add_argument("--decision-cadence-sessions", type=int, default=5)
    parser.add_argument(
        "--material-threshold-pct",
        type=float,
        default=MATERIAL_RETURN_THRESHOLD_PCT,
    )
    args = parser.parse_args(argv)
    audit_retrospective_csv(
        args.input,
        output_path=args.output,
        audited_horizon_sessions=args.audited_horizon_sessions,
        decision_cadence_sessions=args.decision_cadence_sessions,
        material_return_threshold_pct=args.material_threshold_pct,
    )
    return 0


__all__ = [
    "EventFactorPanelError",
    "MATERIAL_RETURN_THRESHOLD_PCT",
    "POST_EVENT_SESSIONS",
    "PRE_EVENT_SESSIONS",
    "PRODUCT_ID",
    "_event_metrics",
    "audit_retrospective_csv",
    "audit_retrospective_decisions",
    "evaluate_event_factor_panel",
    "validate_event_factor_panel_packet",
    "validate_event_factor_panel_result",
]


if __name__ == "__main__":
    raise SystemExit(main())
