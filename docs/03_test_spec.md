# 03 — Test Specification — HCR-C2-047

## Coverage map

| Test file | Scope |
|---|---|
| `tests/unit/test_vital_data_input_node.py` | success, missing vitals, invalid metric |
| `tests/unit/test_anomaly_nodes.py` | deviation detect, absolute-critical SpO2, severity (critical/normal/warning) + vital_service |
| `tests/unit/test_notification_nodes.py` | draft (critical/normal), dispatch (with/without draft), response validate (PHI strip) |
| `tests/integration/test_graph.py` | full Cat 2 compile+invoke: critical dispatch, normal no-dispatch, node_history backbone, invalid input no crash |
| `tests/proof_of_boundary/test_import_isolation.py` | PB-4: no Level-0 imports under src/ |
| `tests/proof_of_boundary/test_state_safety.py` | PB-2/PB-5: no credential fields / Pydantic / InvocationContext in State |

## TC / PB mapping

| TC/PB | Covered by |
|---|---|
| TC-01 State contract | test_state_safety (baseline/contact NOT in State per APPI) |
| TC-02 reject path | VitalDataInput missing/invalid vitals |
| TC-03 no credential in src | gate-credential-scan (CI) |
| TC-04 ctx via configurable | integration `ctx=` + `input_context=` (baseline via provider/config) |
| TC-05 audit logging | emit_trace_event in detect/classify/dispatch/validate (anonymized) |
| TC-06/07 gates non-bypassable | FunctionNode @final inherited |
| TC-08 required_trust_level | agent.yaml VERIFIED_EXTERNAL + VitalDataInput class var |
| PB-1..6 | audit events / state safety (APPI) / dispatch external service / import isolation / invoke order |

## Run

```bash
PYTHONUTF8=1 python -m pytest tests/ -v
```
