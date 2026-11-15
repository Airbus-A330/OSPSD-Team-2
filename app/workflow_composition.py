"""Replaceable composition boundary for cross-vertical workflows."""

from app.workflows import ProjectKickoffWorkflow


def get_project_kickoff_workflow() -> ProjectKickoffWorkflow:
    """Return the configured workflow implementation.

    Real vertical packages and configuration selection are wired by the
    integration workstream. Tests replace this dependency with controlled
    implementations, keeping orchestration independent from provider SDKs.
    """
    raise RuntimeError("Project kickoff workflow is not configured")
