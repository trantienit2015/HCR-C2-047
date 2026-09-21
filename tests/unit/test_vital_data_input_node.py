# HCR-C2-047 — Unit Tests: VitalDataInputNode (outer pre_process)

import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.vital_data_input_node import VitalDataInputNode


class TestVitalDataInputNode:
    def setup_method(self):
        self.node = VitalDataInputNode()

    def _state(self, ctx):
        return {"user_input": "", "input_context": ctx, "node_history": [], "error_log": [], "execution_time": {}}

    def test_success(self):
        result = self.node.execute(self._state(
            {"resident_ref": "R-1", "vitals": {"heart_rate": 88, "spo2": 97, "temperature": 36.8}}))
        assert result["status"] == AgentStatus.SUCCESS
        assert result["resident_ref"] == "R-1"
        payload = json.loads(result["validated_input"])
        assert payload["vitals"]["heart_rate"] == 88

    def test_missing_vitals_error(self):
        result = self.node.execute(self._state({"resident_ref": "R-1"}))
        assert result["status"] == AgentStatus.ERROR

    def test_invalid_metric_error(self):
        result = self.node.execute(self._state({"resident_ref": "R-1", "vitals": {"heart_rate": -5}}))
        assert result["status"] == AgentStatus.ERROR
        assert "invalid value" in result["error_log"][0].lower()
