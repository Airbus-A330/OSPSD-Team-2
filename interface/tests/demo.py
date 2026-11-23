"""Explicit local-only demo: real API routes, synthetic provider/account/agent data.

Run the two uvicorn targets documented in docs/INTERFACE.md. Never deploy this
module or interpret its records as live provider/identity/approval evidence.
"""

import os

from interface.clients import HTTPWorkflowClient
from interface.tests.support import FakeAccount, FakeAgent, controlled_api
from interface.web import create_app

failure = os.getenv("INTERFACE_DEMO_FAILURE", "")
if failure not in {"", "storage", "issue_tracker", "calendar"}:
    raise ValueError("INTERFACE_DEMO_FAILURE must name a workflow step or be empty")
api, _ = controlled_api(failure, os.getenv("INTERFACE_DEMO_UNCERTAIN") == "1")
ui = create_app(
    HTTPWorkflowClient("http://127.0.0.1:8002"),
    agent_factory=FakeAgent,
    account_factory=FakeAccount,
    demo=True,
)
