# Issue #24 integration map

The 90-day work is an orchestration extension, not a second data system.

| Issue #24 capability | Existing authority to extend | New boundary |
| --- | --- | --- |
| Priority/preemption | `kubo.recovery` lease and heartbeat | Priority, generation/fencing, checkpoint CAS |
| Sharded collection | `kubo.source_orchestrator` | `market × source × date/page` work descriptors |
| Immediate failover | `kubo.source_resilience` and orchestrator | No new retry engine |
| Rights/admission | `kubo.source_quality`, trusted registry | Seven explicit admission labels |
| Provenance | `kubo.provenance`, `kubo.research_network` | Bundle and transformation manifests |
| Temporal/training gate | `kubo.source_evidence_lifecycle` | Dataset-release eligibility report |
| Public canary | `kubo.source_access_executor` | One-off admitted routes only |
| Live schedule | `kubo.automation_schedule`, Kuwait pipeline | Priority-aware dispatch, same market calendar |
| Recovery schedule | recovery controller | Event-driven retry + missed-event watchdog retained |

The coordinator may create package manifests and checkpoints, but it must call
these canonical validators. It cannot infer rights from public reachability,
promote a quality score into authority, treat a source access receipt as market
evidence, or unlock strict forecast.

The only accepted initial bundle status is
`INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT`. Saudi output is isolated
research-only staging; Saudi training and promotion remain blocked behind the
Kuwait locked Blind Test.
