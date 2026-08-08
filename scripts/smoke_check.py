from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kubo.catalog import Catalog  # noqa: E402
from kubo.pack import PackValidator  # noqa: E402
from kubo.pipeline import ResearchPipeline  # noqa: E402
from kubo.source_network import SourceNetworkCatalog, SourceNetworkRunValidator  # noqa: E402
from kubo.synthetic import build_synthetic_valid_pack  # noqa: E402
from kubo.synthetic_network import build_synthetic_network_run  # noqa: E402


def main() -> int:
    catalog = Catalog(ROOT / "config")
    network_catalog = SourceNetworkCatalog(ROOT / "config")
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        run_path = build_synthetic_network_run(temporary / "network_run")
        network = SourceNetworkRunValidator(run_path, network_catalog, "next_session_rank").validate()
        pipeline = ResearchPipeline(ROOT)
        research = pipeline.plan("next_session_rank", network_run_root=run_path)
        no_run = pipeline.plan("next_session_rank")

        pack_path = build_synthetic_valid_pack(temporary / "legacy_pack")
        pack = PackValidator(pack_path, catalog).validate()
        legacy_daily = pipeline.plan("next_session_rank", pack_root=pack_path, mode="validated_forecast")
        legacy_opening = pipeline.plan("opening_gap_or_limit", pack_root=pack_path, mode="validated_forecast")

    ranked_rows = research["ranked_candidates"]
    ranked_rows_by_decision_status: dict[str, int] = {}
    for row in ranked_rows:
        decision_status = str(row.get("decision_status", "UNKNOWN"))
        ranked_rows_by_decision_status[decision_status] = (
            ranked_rows_by_decision_status.get(decision_status, 0) + 1
        )

    passed = (
        network.status == "PASS"
        and research["status"] == "RESEARCH_READY"
        and bool(ranked_rows)
        and all(row["probability"] is None and row["recommendation"] is None for row in ranked_rows)
        and no_run["status"] == "SOURCE_NETWORK_REQUIRED"
        and pack.status == "PASS"
        and legacy_daily["status"] == "DATA_READY_MODEL_UNBOUND"
        and legacy_opening["status"] == "EXECUTION_BLOCKED"
    )
    result = {
        "status": "PASS" if passed else "FAIL",
        "catalog": catalog.report(),
        "source_network_catalog": network_catalog.report(),
        "synthetic_network_run": network.to_dict(),
        "primary_research_mode": research["status"],
        "ranked_rows": len(ranked_rows),
        "ranked_rows_by_decision_status": dict(sorted(ranked_rows_by_decision_status.items())),
        "no_network_run": no_run["status"],
        "legacy_validated_forecast_mode": {
            "synthetic_pack": pack.status,
            "daily_without_model": legacy_daily["status"],
            "opening_without_authorized_feed": legacy_opening["status"],
        },
        "note": "Synthetic contract tests only; the live access probe is separate and no market prediction was performed.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
