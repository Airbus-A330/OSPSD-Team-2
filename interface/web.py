"""Python-rendered web client. Sessions hold disposable presentation state only."""

import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from app.workflows import ProjectKickoffRequest
from interface.clients import (
    AccountClient,
    AccountView,
    AgentClient,
    AgentView,
    Decision,
    ExecutionView,
    HTTPWorkflowClient,
    STEP_LABELS,
    WorkflowClient,
    uncertain_result,
)

ROOT = Path(__file__).parent
FIELDS = (
    ("title", "Event title", "Project kickoff"),
    ("start", "Start time with UTC offset", "2030-01-15T10:00:00-05:00"),
    ("end", "End time with UTC offset", "2030-01-15T10:30:00-05:00"),
    ("document_path", "Document path", "/projects/your-project/kickoff.md"),
    ("issue_title", "Follow-up issue title", "Follow up on kickoff decisions"),
)


@dataclass
class BrowserSession:
    """Short-lived UI draft/results, never authoritative approval or identity."""

    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    touched: float = field(default_factory=time.monotonic)
    values: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    draft: ProjectKickoffRequest | None = None
    review_id: str = ""
    result: ExecutionView | None = None
    executing: bool = False
    notice: str = ""
    agent: AgentClient | None = None
    agent_view: AgentView | None = None
    agent_pending: bool = False
    account: AccountClient | None = None
    account_view: AccountView | None = None


def create_app(
    workflow: WorkflowClient | None = None,
    *,
    agent_factory: Callable[[], AgentClient] | None = None,
    account_factory: Callable[[], AccountClient] | None = None,
    secure_cookie: bool = False,
    demo: bool = False,
) -> FastAPI:
    """Build an independent UI, with optional per-session agent/account adapters.

    Default mode is a loopback-only, single-test-account manual client. The
    hosting owner must integrate verified per-user adapters before public use.
    """
    api = (
        workflow
        if workflow is not None
        else HTTPWorkflowClient(
            os.getenv("INTERFACE_API_URL", "http://127.0.0.1:8000"),
            os.getenv("INTERFACE_API_TOKEN", ""),
        )
    )
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )
    application.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    sessions: dict[str, BrowserSession] = {}

    def session_for(
        request: Request, *, create: bool = False
    ) -> tuple[str, BrowserSession]:
        now = time.monotonic()
        for key, value in list(sessions.items()):
            if (
                now - value.touched > 1800
                and not value.executing
                and not value.agent_pending
            ):
                del sessions[key]
        key = request.cookies.get("interface_session", "")
        if key not in sessions:
            if not create:
                raise HTTPException(
                    409,
                    "This preview expired. Open the start page. Do not replay a run whose outcome was unconfirmed.",
                )
            if len(sessions) >= 128:
                raise HTTPException(503, "The interface is busy. Please try later.")
            key = secrets.token_urlsafe(32)
            sessions[key] = BrowserSession(
                agent=agent_factory() if agent_factory else None,
                account=account_factory() if account_factory else None,
            )
        sessions[key].touched = now
        return key, sessions[key]

    @application.middleware("http")
    async def security_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @application.exception_handler(HTTPException)
    async def request_error(request: Request, error: HTTPException) -> HTMLResponse:
        return HTMLResponse(
            templates.get_template("error.html").render(message=error.detail),
            status_code=error.status_code,
        )

    @application.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        key, session = session_for(request, create=True)
        response = HTMLResponse(
            templates.get_template("index.html").render(
                session=session,
                fields=FIELDS,
                step_labels=STEP_LABELS,
                demo=demo,
            )
        )
        response.set_cookie(
            "interface_session",
            key,
            httponly=True,
            samesite="strict",
            secure=secure_cookie,
            max_age=1800,
        )
        return response

    @application.post("/action")
    async def action(request: Request) -> RedirectResponse:
        _, session = session_for(request)
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Please use the interface form.")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 262144:
                raise HTTPException(
                    413,
                    "This interface accepts up to 256 KiB of form text. Shorten the document and review again.",
                )
        try:
            parsed = parse_qs(
                body.decode("utf-8"), keep_blank_values=True, max_num_fields=20
            )
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(
                400, "The form could not be read. Review your inputs."
            ) from None
        if any(len(values) != 1 for values in parsed.values()):
            raise HTTPException(400, "Duplicate form fields are not supported.")
        form = {name: values[0] for name, values in parsed.items()}
        if not secrets.compare_digest(
            form.get("csrf", "").encode(), session.csrf.encode()
        ):
            raise HTTPException(
                403,
                "This form is not valid for your browser session. Reopen the start page.",
            )
        kind = form.get("action", "")
        if session.executing or session.agent_pending:
            raise HTTPException(
                409,
                "A request is already in progress. Wait for its result; do not resend it.",
            )
        session.notice = ""

        if kind == "review":
            if session.result is not None:
                raise HTTPException(
                    409, "Keep the existing result before starting a different kickoff."
                )
            session.draft = None
            session.review_id = ""
            session.values = {
                name: form.get(name, "")
                for name in [*(f[0] for f in FIELDS), "document_content"]
            }
            try:
                session.draft = ProjectKickoffRequest.model_validate(
                    {
                        "event": {
                            key: session.values[key]
                            for key in ("title", "start", "end")
                        },
                        **{
                            key: session.values[key]
                            for key in (
                                "document_path",
                                "document_content",
                                "issue_title",
                            )
                        },
                    }
                )
                session.errors = []
                session.review_id = secrets.token_urlsafe(24)
            except ValidationError as error:
                session.errors = [
                    f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                    for item in error.errors(include_input=False, include_url=False)
                ]
        elif kind in {"execute", "reject"}:
            if (
                not session.draft
                or not session.review_id
                or not secrets.compare_digest(
                    form.get("review_id", "").encode(), session.review_id.encode()
                )
            ):
                raise HTTPException(
                    409,
                    "This preview was replaced or already used. Review the current values before proceeding.",
                )
            session.review_id = ""
            if kind == "reject":
                session.draft = None
                session.notice = "Changes rejected. Nothing was sent to the API. You can edit the form."
            else:
                session.executing = True
                # Retain uncertainty even if this UI request is interrupted.
                session.result = uncertain_result()
                try:
                    session.result = await api.kickoff(session.draft)
                finally:
                    session.executing = False
        elif kind == "new":
            session.values, session.errors = {}, []
            session.draft, session.result, session.review_id = None, None, ""
        elif kind in {
            "agent_submit",
            "agent_refresh",
            "approve",
            "reject_proposal",
            "change",
        }:
            if session.agent is None:
                raise HTTPException(
                    503,
                    "The agent service is not connected yet. Use the manual scenario.",
                )
            session.agent_pending = True
            try:
                if kind == "agent_submit":
                    message = form.get("message", "")
                    if not message.strip():
                        raise HTTPException(
                            422, "Describe what you would like help with."
                        )
                    session.agent_view = await session.agent.submit(message)
                elif kind == "agent_refresh":
                    if session.agent_view is None:
                        raise HTTPException(409, "There is no agent run to refresh.")
                    session.agent_view = await session.agent.refresh(
                        session.agent_view.run_id
                    )
                else:
                    view = session.agent_view
                    if (
                        not view
                        or view.state != "awaiting approval"
                        or view.proposal is None
                    ):
                        raise HTTPException(
                            409, "There is no current proposal awaiting a decision."
                        )
                    proposal = view.proposal
                    if (
                        form.get("proposal_id") != proposal.id
                        or form.get("revision") != proposal.revision
                    ):
                        raise HTTPException(
                            409,
                            "The proposal changed. Review the latest version before deciding.",
                        )
                    decision: Decision = (
                        "reject"
                        if kind == "reject_proposal"
                        else "change"
                        if kind == "change"
                        else "approve"
                    )
                    if decision == "change" and not view.can_request_change:
                        raise HTTPException(
                            409,
                            "This service does not support clarification for this proposal.",
                        )
                    # Disable local replay before awaiting a possibly uncertain response.
                    session.agent_view = AgentView(
                        view.run_id,
                        "executing",
                        "Waiting for the service to confirm your decision.",
                    )
                    session.agent_view = await session.agent.decide(
                        view.run_id,
                        proposal.id,
                        proposal.revision,
                        decision,
                        form.get("clarification", ""),
                    )
            except httpx.HTTPError:
                if session.agent_view:
                    session.agent_view = AgentView(
                        session.agent_view.run_id,
                        "uncertain",
                        "The agent response was lost. Refresh status; do not approve again.",
                    )
                session.notice = "The agent could not confirm the request. Refresh its status before taking another action."
            finally:
                session.agent_pending = False
        elif kind in {"account_status", "sign_in", "reconnect", "disconnect"}:
            if session.account is None:
                raise HTTPException(
                    503,
                    "Account sign-in and connection management are not integrated yet.",
                )
            try:
                if kind == "account_status":
                    session.account_view = await session.account.status()
                else:
                    if kind != "sign_in" and (
                        session.account_view is None
                        or not session.account_view.signed_in
                        or form.get("provider")
                        not in {
                            item.provider for item in session.account_view.connections
                        }
                    ):
                        raise HTTPException(
                            409,
                            "Refresh your account status before changing a connection.",
                        )
                    account_action: Literal["sign_in", "reconnect", "disconnect"] = (
                        "sign_in"
                        if kind == "sign_in"
                        else "reconnect"
                        if kind == "reconnect"
                        else "disconnect"
                    )
                    session.account_view = await session.account.act(
                        account_action, form.get("provider", "")
                    )
            except httpx.HTTPError:
                session.account_view = None
                session.notice = "Account status is unavailable. Refresh status before changing a connection."
        else:
            raise HTTPException(400, "Unknown interface action.")
        return RedirectResponse("/", status_code=303)

    return application


app = create_app()
