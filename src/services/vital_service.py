"""Deterministic vital-sign anomaly + severity helpers for HCR-C2-047.

Pure functions — no agenticstar imports, no side effects. The anomaly detection is a
deterministic threshold + statistical-deviation engine (non-suppressible for critical
thresholds), NOT an LLM self-check. PHI stripping is deterministic.
"""

from __future__ import annotations

from typing import Any
import re

# Absolute safety thresholds — breaching any of these is CRITICAL regardless of baseline
# deviation (non-suppressible for critical vital thresholds).
_CRITICAL_ABSOLUTE = {
    "spo2": ("min", 90),  # SpO2 < 90% is critical
    "heart_rate_min": ("min", 40),  # bradycardia
    "heart_rate_max": ("max", 130),  # tachycardia
    "bp_systolic_max": ("max", 180),
    "bp_systolic_min": ("min", 80),
    "temperature_max": ("max", 39.0),
}

_METRICS = ("heart_rate", "bp_systolic", "spo2", "temperature", "respiration")

# Strip anything resembling a personal identifier from output text.
_NAME_RE = re.compile(r"(様|さん|氏)\b")


def detect_anomalies(vitals: dict[str, Any], baseline: dict[str, Any]) -> list[Any]:
    """Return per-metric anomalies = deviation from baseline beyond 0, plus absolute breaches.

    Each anomaly: {"metric", "value", "deviation_pct", "absolute_critical": bool}.
    """
    anomalies: list[Any] = []
    for metric in _METRICS:
        value = vitals.get(metric)
        if value is None:
            continue
        base = (baseline or {}).get(metric)
        deviation_pct = 0.0
        if base:
            try:
                deviation_pct = round(abs(value - base) / base * 100, 1)
            except (TypeError, ZeroDivisionError):
                deviation_pct = 0.0
        absolute_critical = _breaches_absolute(metric, value)
        if deviation_pct > 0 or absolute_critical:
            anomalies.append(
                {
                    "metric": metric,
                    "value": value,
                    "deviation_pct": deviation_pct,
                    "absolute_critical": absolute_critical,
                }
            )
    return anomalies


def _breaches_absolute(metric: str, value: Any) -> bool:
    for key, (direction, limit) in _CRITICAL_ABSOLUTE.items():
        if not key.startswith(metric):
            continue
        if direction == "min" and value < limit:
            return True
        if direction == "max" and value > limit:
            return True
    return False


def classify_severity(anomalies: list[Any], critical_pct: float, warning_pct: float) -> str:
    """CRITICAL if any absolute breach or deviation >= critical_pct; WARNING if >= warning_pct; else NORMAL."""
    if not anomalies:
        return "NORMAL"
    max_dev = max((a.get("deviation_pct", 0.0) for a in anomalies), default=0.0)
    if any(a.get("absolute_critical") for a in anomalies) or max_dev >= critical_pct:
        return "CRITICAL"
    if max_dev >= warning_pct:
        return "WARNING"
    return "NORMAL"


def strip_phi(text: str) -> str:
    """Remove resident-name honorifics / identifiers from a response string (APPI Article 17)."""
    return _NAME_RE.sub("", text or "")
