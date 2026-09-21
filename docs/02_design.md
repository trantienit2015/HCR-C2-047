# 02 — Design Specification — HCR-C2-047

## Position in AgentCore Architecture

- **Agent Class**: `VitalAnomalyNotificationGraph` (`src/graph/graph.py`)
- **L1 Base type**: `AgentBaseGraph` (L1 direct) — no L2 inheritance.
- **Inheritance**: `AgentBaseGraph` (L1 direct).
- **Category**: Cat 2 — canonical pattern: outer `AgentBaseGraph` + `GraphNode` (`main` slot)
  + inner `BaseGraph` domain subgraph.
- **Pattern**: Orchestration pipeline.

## Graph topology

```
OUTER (VitalAnomalyNotificationGraph : AgentBaseGraph)
  initialize -> pre_process (VitalDataInputNode)
            -> main (VitalAnomalyGraphNode : GraphNode)
            -> post_process (ResponseValidateNode)
            -> finalize

INNER (VitalAnomalyWorkflowGraph : BaseGraph)
  START -> vital_context_load -> anomaly_detect -> anomaly_severity_classify
        -> family_notification_draft -> notification_dispatch -> END
```

## APPI Article 17 (要配慮個人情報) design

- Vital signs + resident identity are sensitive personal information. State is checkpointed to
  the DB, so the **per-resident baseline and contact profile are NEVER written to State**. They
  are resolved in-memory at use time from a `baseline_provider` supplied via the GraphNode
  `_parent_config()` (InvocationContext-derived data, not State).
- The resident is referenced by an opaque `resident_ref`, not a patient identifier.
- `ResponseValidateNode` strips residual identifiers (honorifics) from the final response;
  audit events carry only `resident_ref` + counts, never raw PHI.
- `required_trust_level: VERIFIED_EXTERNAL` — the caller must be an authenticated facility
  monitoring system; anonymous callers are refused by S-1.
  VERIFIED_EXTERNAL rather than INTERNAL: the platform runner
  stamps every caller VERIFIED_EXTERNAL and grants INTERNAL to nobody, so an INTERNAL
  requirement would be refused by S-1 before `execute()` on every invocation.

## Node responsibilities

| Slot | Node | Responsibility |
|---|---|---|
| outer pre_process | `VitalDataInputNode` | S-1 (VERIFIED_EXTERNAL); validate + range-check vitals; reject malformed; serialize `validated_input` (vitals + resident_ref only). |
| inner step 1 | `VitalContextLoadNode` | Confirm baseline availability from the InvocationContext provider; does NOT place baseline in State. |
| inner step 2 | `AnomalyDetectNode` | Deterministic threshold + statistical-deviation vs baseline (non-suppressible for critical absolute thresholds, e.g. SpO2 < 90). |
| inner step 3 | `AnomalySeverityClassifyNode` | CRITICAL / WARNING / NORMAL; NORMAL -> early-exit, no dispatch. |
| inner step 4 | `FamilyNotificationDraftNode` | Severity-appropriate notification draft (none on NORMAL). |
| inner step 5 | `NotificationDispatchNode` | Dispatch to the registered contact channel; anonymized audit event. |
| outer post_process | `ResponseValidateNode` | Anonymized summary + PHI stripping before output (APPI Article 17). |

## State schema (`src/schemas/state.py`)

`class State(AgentState)` adds flat JSON-serializable fields: `resident_ref` (opaque), `vitals`,
`anomalies`, `severity`, `early_exit`, `notification_draft`, `dispatched`, `dispatch_channel`,
`phi_stripped`. No baseline / contact / Pydantic / InvocationContext / credentials in State.

## Security (5-layer)

- **S-1**: agent default `required_trust_level: VERIFIED_EXTERNAL`; `VitalDataInputNode`,
  `VitalAnomalyGraphNode` and `ResponseValidateNode` also declare it. Inner subgraph nodes run
  at ANONYMOUS — they are unreachable except through the gated outer nodes.
- **S-2**: framework input gate; VitalDataInput range-checks + rejects malformed vitals.
- **S-3 / APPI**: `ResponseValidateNode` deterministic PHI strip; baseline/contact never in
  State. Secrets via entry-point `bound_secrets`/`secrets_factory`/`provision_secrets`; never
  `os.environ`; `requires.secrets` in `agent.yaml`.
- **S-4**: `emit_trace_event()` on detect / classify / dispatch / validate (anonymized payloads).
- **S-5**: framework credential scan; flat-TypedDict State.

## Config (`config/agent.yaml` `agent.config`)

`max_retry`, `timeout_seconds`, `critical_deviation_pct` (30), `warning_deviation_pct` (15).
