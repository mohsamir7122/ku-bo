from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from kubo.hashing import canonical_json_bytes, sha256_bytes

from tests.test_research_ledger import (
    OUTCOME_OBSERVED_AT,
    OUTCOME_RECORDED_AT,
    make_ledger,
    outcome_payload,
    record,
    write_outcome_pack,
)


def append_valid_outcome(ledger, pack: Path) -> dict:
    return ledger.append_outcome(
        outcome_id="outcome-1",
        decision_id="decision-1",
        observed_at=OUTCOME_OBSERVED_AT,
        recorded_at=OUTCOME_RECORDED_AT,
        test_mode=True,
        payload=outcome_payload(),
        evidence_pack=pack,
        actor_or_model_id="outcome-worker",
    )


def rewrite_only_outcome(ledger, event: dict) -> None:
    event["event_hash"] = sha256_bytes(
        canonical_json_bytes({key: value for key, value in event.items() if key != "event_hash"})
    )
    ledger.outcome_path.write_text(
        json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class OutcomeLedgerIntegrationTests(unittest.TestCase):
    def test_arbitrary_payload_and_non_candidate_security_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            pack = write_outcome_pack(ledger)
            with self.assertRaisesRegex(ValueError, "outcome payload is missing fields"):
                ledger.append_outcome(
                    outcome_id="outcome-1",
                    decision_id="decision-1",
                    observed_at=OUTCOME_OBSERVED_AT,
                    recorded_at=OUTCOME_RECORDED_AT,
                    test_mode=True,
                    payload={"actual_return": 0.02},
                    evidence_pack=pack,
                    actor_or_model_id="outcome-worker",
                )

            wrong_pack = write_outcome_pack(
                ledger,
                outcome_id="outcome-2",
                security_code="102",
            )
            with self.assertRaisesRegex(ValueError, "exactly one candidate"):
                ledger.append_outcome(
                    outcome_id="outcome-2",
                    decision_id="decision-1",
                    observed_at=OUTCOME_OBSERVED_AT,
                    recorded_at=OUTCOME_RECORDED_AT,
                    test_mode=True,
                    payload=outcome_payload(security_code="102"),
                    evidence_pack=wrong_pack,
                    actor_or_model_id="outcome-worker",
                )

    def test_evidence_pack_must_be_inside_ledger_and_have_no_symlink_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            ledger = make_ledger(workspace / "ledger")
            record(ledger)
            outside = write_outcome_pack(
                ledger,
                packet_root=workspace / "outside-pack",
            )
            with self.assertRaisesRegex(ValueError, "inside the ledger root"):
                append_valid_outcome(ledger, outside)

            real_pack = write_outcome_pack(ledger)
            alias = ledger.ledger_root / "outcome_evidence" / "alias"
            try:
                alias.symlink_to(real_pack, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:  # pragma: no cover - platform dependent.
                self.skipTest(f"directory symlinks unavailable: {exc}")
            with self.assertRaisesRegex(ValueError, "symlink"):
                append_valid_outcome(ledger, alias)

    def test_relative_evidence_pack_is_resolved_from_ledger_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            write_outcome_pack(ledger)
            event = append_valid_outcome(
                ledger,
                Path("outcome_evidence/outcome-1"),
            )
            self.assertEqual(event["evidence_packet_path"], "outcome_evidence/outcome-1")

        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            with self.assertRaisesRegex(
                ValueError,
                "relative evidence_pack paths are resolved inside the ledger root",
            ):
                append_valid_outcome(ledger, Path("missing-outcome-pack"))

    def test_manifest_identity_is_bound_to_outcome_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            pack = write_outcome_pack(ledger)
            manifest_path = pack / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["decision_id"] = "decision-other"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest decision_id does not match"):
                append_valid_outcome(ledger, pack)

    def test_verify_revalidates_tampered_deleted_and_replaced_packets(self) -> None:
        for mutation in ("tampered", "deleted", "replaced"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                ledger = make_ledger(directory)
                record(ledger)
                pack = write_outcome_pack(ledger)
                append_valid_outcome(ledger, pack)
                self.assertEqual(ledger.verify()["status"], "PASS")

                if mutation == "tampered":
                    (pack / "raw" / "official-close.json").write_bytes(b"changed after append\n")
                elif mutation == "deleted":
                    shutil.rmtree(pack)
                else:
                    shutil.rmtree(pack)
                    write_outcome_pack(ledger, content=b'{"security_code":"101","close_fils":999}\n')

                result = ledger.verify()
                self.assertEqual(result["status"], "BLOCKED", result)
                self.assertTrue(
                    any("EVIDENCE_PACKET" in error for error in result["errors"]),
                    result,
                )

    def test_verify_rejects_changed_payload_security_and_packet_path(self) -> None:
        for mutation in ("payload", "security", "path"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                ledger = make_ledger(directory)
                record(ledger)
                pack = write_outcome_pack(ledger)
                append_valid_outcome(ledger, pack)
                event = ledger.outcomes()[0]
                if mutation == "payload":
                    event["payload"]["value"] = 0.5
                elif mutation == "security":
                    event["payload"]["security_code"] = "102"
                    event["payload_hash"] = sha256_bytes(canonical_json_bytes(event["payload"]))
                    rewrite_only_outcome(ledger, event)
                    result = ledger.verify()
                    self.assertEqual(result["status"], "BLOCKED", result)
                    self.assertTrue(
                        any("exactly one candidate" in error for error in result["errors"]),
                        result,
                    )
                    continue
                else:
                    event["evidence_packet_path"] = "outcome_evidence/missing"
                ledger.outcome_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
                self.assertEqual(ledger.verify()["status"], "BLOCKED")

    def test_seal_and_verify_seal_refuse_a_tampered_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = make_ledger(directory)
            record(ledger)
            pack = write_outcome_pack(ledger)
            append_valid_outcome(ledger, pack)
            seal_path = Path(directory) / "seal.json"
            ledger.seal(
                seal_path,
                sealed_at="2026-08-08T13:02:00+03:00",
                test_mode=True,
            )
            (pack / "raw" / "official-close.json").write_bytes(b"tampered\n")
            self.assertEqual(ledger.verify_seal(seal_path)["status"], "BLOCKED")
            with self.assertRaisesRegex(ValueError, "cannot seal an invalid research ledger"):
                ledger.seal(
                    Path(directory) / "replacement-seal.json",
                    sealed_at="2026-08-08T13:03:00+03:00",
                    test_mode=True,
                )

    def test_stream_paths_must_share_one_ledger_directory(self) -> None:
        from kubo.research_ledger import ResearchDecisionLedger

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "share one ledger directory"):
                ResearchDecisionLedger(
                    root / "decisions" / "decisions.jsonl",
                    root / "outcomes" / "outcomes.jsonl",
                    "ledger-1",
                )


if __name__ == "__main__":
    unittest.main()
