from __future__ import annotations

from contextlib import contextmanager
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .hashing import canonical_json_bytes, sha256_bytes, sha256_file
from .strict import finite_number, parse_aware, require_sha256, strict_bool


try:  # pragma: no cover - the Windows branch is exercised only on Windows.
    import fcntl as _fcntl
except ImportError:  # pragma: no cover
    _fcntl = None

try:  # pragma: no cover - the POSIX branch is exercised in CI.
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover
    _msvcrt = None


EVENT_TYPES = frozenset({"CREATE", "AMEND", "WITHDRAW", "EXPIRE", "IMPORTED"})
OUTCOME_FORBIDDEN = frozenset({"outcome", "realized_positive", "gross_return", "benchmark_return", "net_return", "net_excess_return", "target_hit", "exit_price", "exit_price_fils", "future_return", "max_favorable_excursion", "max_adverse_excursion"})
FORECAST_ALLOWED = frozenset(
    {
        "decision_id",
        "security_code",
        "product_id",
        "target_rule",
        "decision_at",
        "outcome_due_at",
        "horizon_sessions",
        "model_version",
        "entry_rule",
        "eligible",
        "selected",
        "abstained",
        "score",
        "probability",
        "rank",
        "expected_net_return",
        "lower_return",
        "upper_return",
        "decision_status",
        "reason_codes",
        "catalyst_news_ids",
        "thesis_episode_id",
        "direction",
        "invalidation_rule",
    }
)
FORECAST_REQUIRED = frozenset({"decision_id", "security_code", "product_id", "target_rule", "decision_at", "outcome_due_at", "horizon_sessions", "model_version", "entry_rule", "eligible", "selected", "abstained", "thesis_episode_id"})


def _lock_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(ledger_path.name + ".lock")


@contextmanager
def _exclusive_lock(ledger_path: Path) -> Iterator[None]:
    """Serialize ledger readers and writers across processes."""

    lock_path = _lock_path(ledger_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if _fcntl is not None:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
        elif _msvcrt is not None:  # pragma: no cover
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            _msvcrt.locking(handle.fileno(), _msvcrt.LK_LOCK, 1)
        else:  # pragma: no cover
            raise RuntimeError("no supported process-locking primitive")
        try:
            yield
        finally:
            if _fcntl is not None:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:  # pragma: no cover
                handle.seek(0)
                _msvcrt.locking(handle.fileno(), _msvcrt.LK_UNLCK, 1)


def _read_events_unlocked(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid ledger JSON at line {index + 1}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"ledger line {index + 1} is not an object")
        events.append(value)
    return events


def _append_event_unlocked(path: Path, event: dict[str, Any]) -> None:
    """Append exactly one record with one O_APPEND write, or restore its prefix."""

    data = canonical_json_bytes(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_BINARY"):  # pragma: no cover
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    original_size = path.stat().st_size if path.exists() else 0
    descriptor = os.open(path, flags, 0o600)
    try:
        written = os.write(descriptor, data)
        if written != len(data):
            raise OSError(f"short atomic append: wrote {written} of {len(data)} bytes")
        os.fsync(descriptor)
    except BaseException:
        # The process lock guarantees that bytes after original_size belong to
        # this failed append, so rolling them back cannot erase another event.
        try:
            os.ftruncate(descriptor, original_size)
            os.fsync(descriptor)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _forbidden_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized in OUTCOME_FORBIDDEN or normalized.startswith("realized_") or normalized.startswith("future_") or normalized.startswith("exit_price") or normalized.endswith("_target_hit"):
                return str(key)
            hit = _forbidden_key(nested)
            if hit:
                return hit
    elif isinstance(value, list):
        for nested in value:
            hit = _forbidden_key(nested)
            if hit:
                return hit
    return None


def validate_forecast_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    forbidden = _forbidden_key(payload)
    if forbidden:
        errors.append(f"FORBIDDEN_OUTCOME_FIELD:{forbidden}")
    unknown = sorted(set(payload) - FORECAST_ALLOWED)
    if unknown:
        errors.append("NON_ALLOWLISTED_FIELDS:" + ",".join(unknown))
    missing = sorted(field for field in FORECAST_REQUIRED if payload.get(field) in (None, ""))
    if missing:
        errors.append("MISSING_FIELDS:" + ",".join(missing))
    try:
        decision = parse_aware(payload.get("decision_at"), "decision_at")
        due = parse_aware(payload.get("outcome_due_at"), "outcome_due_at")
        if due <= decision:
            errors.append("OUTCOME_DUE_NOT_AFTER_DECISION")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        if int(payload.get("horizon_sessions", 0)) <= 0:
            errors.append("HORIZON_NOT_POSITIVE")
    except (TypeError, ValueError):
        errors.append("INVALID_HORIZON")
    try:
        eligible = strict_bool(payload.get("eligible"), "eligible")
        selected = strict_bool(payload.get("selected"), "selected")
        abstained = strict_bool(payload.get("abstained"), "abstained")
        if selected and (abstained or not eligible):
            errors.append("INVALID_SELECTION_FLAGS")
    except ValueError as exc:
        errors.append(str(exc))
    score = payload.get("score")
    probability = payload.get("probability")
    if score in (None, "") and probability in (None, ""):
        errors.append("SCORE_OR_PROBABILITY_REQUIRED")
    if score not in (None, ""):
        try:
            finite_number(score, "score")
        except ValueError as exc:
            errors.append(str(exc))
    if probability not in (None, ""):
        try:
            finite_number(probability, "probability", minimum=0, maximum=1)
        except ValueError as exc:
            errors.append(str(exc))
    if payload.get("rank") not in (None, ""):
        try:
            if int(payload["rank"]) <= 0:
                errors.append("RANK_NOT_POSITIVE")
        except (TypeError, ValueError):
            errors.append("INVALID_RANK")
    for field in ("reason_codes", "catalyst_news_ids"):
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field.upper()}_MUST_BE_LIST")
    return sorted(set(errors))


class ForecastLedger:
    def __init__(self, path: Path, ledger_id: str):
        if not ledger_id.strip():
            raise ValueError("ledger_id is required")
        self.path = Path(path)
        self.ledger_id = ledger_id

    def events(self) -> list[dict[str, Any]]:
        with _exclusive_lock(self.path):
            return _read_events_unlocked(self.path)

    def append(
        self,
        *,
        event_type: str,
        claim_id: str,
        issued_at: str,
        effective_at: str,
        source_hash: str,
        actor_or_model_id: str,
        policy_hash: str,
        code_hash: str,
        feature_snapshot_hash: str,
        universe_hash: str,
        trading_calendar_hash: str,
        payload: dict[str, Any],
        recorded_at: str | None = None,
        test_mode: bool = False,
    ) -> dict[str, Any]:
        event_type = event_type.upper()
        if event_type not in EVENT_TYPES:
            raise ValueError("unsupported event_type")
        if event_type in {"CREATE", "AMEND"}:
            payload_errors = validate_forecast_payload(payload)
            if payload_errors:
                raise ValueError(";".join(payload_errors))
        else:
            forbidden = _forbidden_key(payload)
            if forbidden:
                raise ValueError(f"forbidden outcome field: {forbidden}")
            if not str(payload.get("reason", "")).strip():
                raise ValueError("withdraw/expire/import metadata requires reason")
        issued = parse_aware(issued_at, "issued_at")
        effective = parse_aware(effective_at, "effective_at")
        if effective < issued:
            raise ValueError("effective_at cannot precede issued_at")
        if recorded_at is None:
            supplied_recorded = None
        else:
            if not test_mode:
                raise ValueError("caller-supplied recorded_at requires test_mode")
            supplied_recorded = parse_aware(recorded_at, "recorded_at")
        for field, value in {
            "source_hash": source_hash,
            "policy_hash": policy_hash,
            "code_hash": code_hash,
            "feature_snapshot_hash": feature_snapshot_hash,
            "universe_hash": universe_hash,
            "trading_calendar_hash": trading_calendar_hash,
        }.items():
            require_sha256(value, field)

        with _exclusive_lock(self.path):
            # Runtime time is sampled after acquiring the lock so queued
            # writers remain monotonic in their physical append order.
            recorded = supplied_recorded or datetime.now(timezone.utc)
            events = _read_events_unlocked(self.path)
            if any(event.get("ledger_id") != self.ledger_id for event in events):
                raise ValueError("existing ledger contains another ledger_id")
            if event_type in {"CREATE", "IMPORTED"} and any(
                event.get("claim_id") == claim_id
                and event.get("event_type") in {"CREATE", "IMPORTED"}
                for event in events
            ):
                raise ValueError("claim already has an origin event")
            prior_claim_events = [event for event in events if event.get("claim_id") == claim_id]
            if event_type in {"AMEND", "WITHDRAW", "EXPIRE"} and not prior_claim_events:
                raise ValueError("amendment/withdrawal/expiry requires a prior claim")
            if recorded < issued:
                raise ValueError("recorded_at cannot precede issued_at")
            if events and recorded < parse_aware(events[-1]["recorded_at"], "recorded_at"):
                raise ValueError("recorded_at must be monotonic")
            if event_type in {"AMEND", "WITHDRAW", "EXPIRE"} and effective < recorded:
                raise ValueError("later event cannot become effective before it is recorded")

            event: dict[str, Any] = {
                "ledger_id": self.ledger_id,
                "claim_id": claim_id,
                "revision": len(prior_claim_events) + 1,
                "event_type": event_type,
                "issued_at": issued.isoformat(),
                "recorded_at": recorded.isoformat(),
                "effective_at": effective.isoformat(),
                "source_hash": source_hash,
                "actor_or_model_id": actor_or_model_id,
                "policy_hash": policy_hash,
                "code_hash": code_hash,
                "feature_snapshot_hash": feature_snapshot_hash,
                "universe_hash": universe_hash,
                "trading_calendar_hash": trading_calendar_hash,
                "payload": payload,
                "event_seq": len(events) + 1,
                "previous_event_hash": events[-1]["event_hash"] if events else None,
                "supersedes_event_hash": (
                    prior_claim_events[-1]["event_hash"] if prior_claim_events else None
                ),
            }
            event["payload_hash"] = sha256_bytes(canonical_json_bytes(payload))
            event["event_hash"] = sha256_bytes(canonical_json_bytes(event))
            _append_event_unlocked(self.path, event)
            return event

    def verify(self) -> dict[str, Any]:
        try:
            events = self.events()
        except ValueError as exc:
            return {"status": "BLOCKED", "events": 0, "errors": [str(exc)]}
        errors: list[str] = []
        previous: str | None = None
        last_recorded = None
        claims: dict[str, list[dict[str, Any]]] = {}
        for expected_seq, event in enumerate(events, start=1):
            prefix = f"event_{expected_seq}"
            if event.get("ledger_id") != self.ledger_id:
                errors.append(prefix + ":LEDGER_ID")
            if event.get("event_seq") != expected_seq:
                errors.append(prefix + ":SEQUENCE")
            if event.get("previous_event_hash") != previous:
                errors.append(prefix + ":PREVIOUS_HASH")
            try:
                recorded = parse_aware(event.get("recorded_at"), "recorded_at")
                issued = parse_aware(event.get("issued_at"), "issued_at")
                effective = parse_aware(event.get("effective_at"), "effective_at")
                if recorded < issued or effective < issued or (last_recorded and recorded < last_recorded):
                    errors.append(prefix + ":TIME_ORDER")
                last_recorded = recorded
            except ValueError:
                errors.append(prefix + ":TIMESTAMP")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                errors.append(prefix + ":PAYLOAD_NOT_OBJECT")
                payload = {}
            expected_payload_hash = sha256_bytes(canonical_json_bytes(payload))
            if event.get("payload_hash") != expected_payload_hash:
                errors.append(prefix + ":PAYLOAD_HASH")
            candidate = dict(event)
            expected_event_hash = candidate.pop("event_hash", None)
            if expected_event_hash != sha256_bytes(canonical_json_bytes(candidate)):
                errors.append(prefix + ":EVENT_HASH")
            for field in ("source_hash", "policy_hash", "code_hash", "feature_snapshot_hash", "universe_hash", "trading_calendar_hash"):
                try:
                    require_sha256(event.get(field), field)
                except ValueError:
                    errors.append(prefix + f":{field.upper()}")
            event_type = str(event.get("event_type", ""))
            if event_type not in EVENT_TYPES:
                errors.append(prefix + ":EVENT_TYPE")
            if event_type in {"CREATE", "AMEND"}:
                errors.extend(prefix + ":" + item for item in validate_forecast_payload(payload))
            claim_id = str(event.get("claim_id", ""))
            claim_events = claims.setdefault(claim_id, [])
            if int(event.get("revision", 0)) != len(claim_events) + 1:
                errors.append(prefix + ":REVISION")
            if event_type in {"AMEND", "WITHDRAW", "EXPIRE"}:
                if not claim_events or event.get("supersedes_event_hash") != claim_events[-1].get("event_hash"):
                    errors.append(prefix + ":SUPERSEDES")
                try:
                    if parse_aware(event.get("effective_at"), "effective_at") < parse_aware(event.get("recorded_at"), "recorded_at"):
                        errors.append(prefix + ":BACKDATED_LATER_EVENT")
                except ValueError:
                    pass
            elif event_type in {"CREATE", "IMPORTED"} and claim_events:
                errors.append(prefix + ":DUPLICATE_ORIGIN")
            claim_events.append(event)
            previous = expected_event_hash
        return {"status": "PASS" if events and not errors else "BLOCKED", "events": len(events), "errors": sorted(set(errors)), "last_event_hash": previous}

    def seal(self, path: Path, *, sealed_at: str | None = None, test_mode: bool = False) -> dict[str, Any]:
        verification = self.verify()
        if verification["status"] != "PASS":
            raise ValueError(f"cannot seal invalid ledger: {verification}")
        events = self.events()
        if sealed_at is None:
            sealed = datetime.now(timezone.utc)
        else:
            if not test_mode:
                raise ValueError("caller-supplied sealed_at requires test_mode")
            sealed = parse_aware(sealed_at, "sealed_at")
        last_recorded = parse_aware(events[-1]["recorded_at"], "recorded_at")
        if sealed < last_recorded:
            raise ValueError("seal cannot predate last event")
        seal = {
            "schema_version": "2.0",
            "ledger_id": self.ledger_id,
            "event_count": len(events),
            "first_event_hash": events[0]["event_hash"],
            "last_event_hash": events[-1]["event_hash"],
            "content_sha256": sha256_file(self.path),
            "last_event_recorded_at": events[-1]["recorded_at"],
            "sealed_at": sealed.isoformat(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seal, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return seal

    def verify_seal(self, path: Path) -> dict[str, Any]:
        verification = self.verify()
        errors = list(verification["errors"])
        if not path.is_file():
            errors.append("MISSING_SEAL")
            return {"status": "BLOCKED", "errors": errors}
        try:
            seal = json.loads(path.read_text(encoding="utf-8"))
            events = self.events()
            expected = {
                "schema_version": "2.0",
                "ledger_id": self.ledger_id,
                "event_count": len(events),
                "first_event_hash": events[0]["event_hash"] if events else None,
                "last_event_hash": events[-1]["event_hash"] if events else None,
                "content_sha256": sha256_file(self.path),
                "last_event_recorded_at": events[-1]["recorded_at"] if events else None,
            }
            for key, value in expected.items():
                if seal.get(key) != value:
                    errors.append(f"SEAL_{key.upper()}")
            sealed = parse_aware(seal.get("sealed_at"), "sealed_at")
            if events and sealed < parse_aware(events[-1]["recorded_at"], "recorded_at"):
                errors.append("SEAL_TIME")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"INVALID_SEAL:{exc}")
        return {"status": "PASS" if verification["status"] == "PASS" and not errors else "BLOCKED", "errors": sorted(set(errors))}


__all__ = ["ForecastLedger", "validate_forecast_payload"]
