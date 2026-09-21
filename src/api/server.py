"""AgentCore Platform v1.0 — HCR-C2-047 HTTP entry point.

Adapter only — no business logic. Per APPI Article 17, the resident baseline + contact profile
are passed via input_context (InvocationContext-derived) and never persisted in State.
"""

from typing import Any
import os
import secrets
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from shared.secrets import factory as secrets_factory
from src.graph.graph import Graph

app = FastAPI(title="HCR-C2-047 Elderly Care Vital Anomaly & Family Notification Agent")

agent = Graph()
agent.compile()
agent.provision_secrets(secrets_factory(namespace="hcr", agent_name="hcr-c2-047"))


class InvokeRequest(BaseModel):
    resident_ref: str
    vitals: dict[str, Any]
    session_id: str = ""


@app.post("/invoke")
async def invoke(req: InvokeRequest, request: Request) -> Any:
    trust = getattr(request.state, "trust_level", TrustLevel.ANONYMOUS)
    # Standalone/STG caller auth: when
    # INVOKE_AUTH_TOKEN is set on the server environment, callers that no upstream
    # middleware vouched for (still ANONYMOUS) must present it as a Bearer token
    # and run at VERIFIED_EXTERNAL. Middleware-established trust is never demoted.
    # This adapter is the entry-point auth boundary (standalone equivalent of
    # platform AuthMiddleware) — a deployment-level caller credential, not an
    # agent secret, so ctx.secrets does not apply (no InvocationContext exists
    # before auth); this is a documented entry-point exception.
    expected = os.environ.get("INVOKE_AUTH_TOKEN")
    if expected and trust is TrustLevel.ANONYMOUS:
        supplied = request.headers.get("authorization", "")
        # Compare bytes: compare_digest raises TypeError on non-ASCII str input
        # (headers decode as latin-1), which would 500 instead of the generic 401.
        if not secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
            # Generic body on purpose — do not leak whether the token was absent,
            # malformed, or wrong.
            raise HTTPException(status_code=401, detail="Token is invalid or expired.")
        trust = TrustLevel.VERIFIED_EXTERNAL
    with bound_secrets(agent._secrets_provider):
        ctx = InvocationContext(
            session_id=req.session_id or str(uuid4()),
            caller_trust_level=trust,
            caller_id=getattr(request.state, "caller_id", ""),
        )
        # vitals + opaque resident_ref via input_context (APPI: baseline resolved server-side,
        # never stored in State).
        return agent.invoke(
            "",
            ctx=ctx,
            input_context={"resident_ref": req.resident_ref, "vitals": req.vitals},
        )


@app.get("/health")
def health() -> Any:
    return {"status": "ok", "agent": "hcr-c2-047"}
