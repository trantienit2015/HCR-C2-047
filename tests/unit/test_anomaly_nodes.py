# HCR-C2-047 — Unit Tests: AnomalyDetect + SeverityClassify + vital_service

from framework.schemas.agent_status import AgentStatus
from src.nodes.anomaly_detect_node import AnomalyDetectNode
from src.nodes.anomaly_severity_classify_node import AnomalySeverityClassifyNode
from src.services.vital_service import detect_anomalies, classify_severity, strip_phi


def _provider(resident_ref):
    return {"baseline": {"heart_rate": 70, "spo2": 98, "temperature": 36.5},
            "contact": {"channel": "sms"}}


def _state(vitals, **extra):
    s = {"resident_ref": "R-1", "vitals": vitals, "node_history": [], "error_log": [], "execution_time": {}}
    s.update(extra)
    return s


class TestAnomalyDetectNode:
    def test_detects_deviation(self):
        node = AnomalyDetectNode(baseline_provider=_provider)
        result = node.execute(_state({"heart_rate": 110, "spo2": 97}))
        assert result["status"] == AgentStatus.SUCCESS
        hr = next(a for a in result["anomalies"] if a["metric"] == "heart_rate")
        assert hr["deviation_pct"] > 0

    def test_absolute_critical_spo2(self):
        node = AnomalyDetectNode(baseline_provider=_provider)
        result = node.execute(_state({"spo2": 85}))
        spo2 = next(a for a in result["anomalies"] if a["metric"] == "spo2")
        assert spo2["absolute_critical"] is True


class TestSeverityClassify:
    def test_critical_on_absolute(self):
        node = AnomalySeverityClassifyNode(critical_pct=30, warning_pct=15)
        result = node.execute(_state({}, anomalies=[{"metric": "spo2", "value": 85, "deviation_pct": 5, "absolute_critical": True}]))
        assert result["severity"] == "CRITICAL"
        assert result["early_exit"] is False

    def test_normal_early_exit(self):
        node = AnomalySeverityClassifyNode()
        result = node.execute(_state({}, anomalies=[]))
        assert result["severity"] == "NORMAL"
        assert result["early_exit"] is True

    def test_warning(self):
        node = AnomalySeverityClassifyNode(critical_pct=30, warning_pct=15)
        result = node.execute(_state({}, anomalies=[{"metric": "heart_rate", "value": 90, "deviation_pct": 20, "absolute_critical": False}]))
        assert result["severity"] == "WARNING"


class TestVitalService:
    def test_classify_thresholds(self):
        assert classify_severity([], 30, 15) == "NORMAL"
        assert classify_severity([{"deviation_pct": 35, "absolute_critical": False}], 30, 15) == "CRITICAL"
        assert classify_severity([{"deviation_pct": 20, "absolute_critical": False}], 30, 15) == "WARNING"

    def test_strip_phi(self):
        assert "様" not in strip_phi("田中様 の状態")

    def test_detect_anomalies_no_baseline(self):
        # absolute critical still fires without a baseline
        out = detect_anomalies({"spo2": 85}, {})
        assert any(a["absolute_critical"] for a in out)
