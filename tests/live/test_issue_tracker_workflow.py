"""Opt-in Team 4 creation and independent Trello read-back verification."""

import json
import os
from uuid import uuid4
from urllib.request import Request, urlopen

import pytest
from team_4_issue_tracker_trello import TrelloIssueProvider

from app.workflow_composition import open_issue_creator

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_ISSUE_TRACKER") != "1",
    reason="Opt-in live Trello verification writes a disposable card",
)


def test_live_issue_creation_and_direct_trello_read() -> None:
    """Confirm the created card directly in Trello and remove known creations."""
    if os.getenv("ISSUE_TRACKER_IMPLEMENTATION") != "team4-trello":
        pytest.fail("Set ISSUE_TRACKER_IMPLEMENTATION=team4-trello", pytrace=False)
    title = "OSPSD Team 2 verification " + uuid4().hex
    created_id: str | None = None
    try:
        with open_issue_creator() as creator:
            issue = creator.create_issue(title)
        created_id = issue.id
        assert issue.title == title
        key = os.environ["TRELLO_API_KEY"]
        token = os.environ["TRELLO_TOKEN"]
        request = Request(
            f"https://api.trello.com/1/cards/{created_id}?fields=id,name,idList",
            headers={
                "Authorization": f'OAuth oauth_consumer_key="{key}", oauth_token="{token}"'
            },
        )
        with urlopen(request, timeout=15) as response:
            card = json.load(response)
        assert card["id"] == created_id
        assert card["name"] == title
        assert card["idList"] == os.environ["TRELLO_LIST_ID"]
    finally:
        if created_id is not None:
            provider = TrelloIssueProvider()
            try:
                provider.delete_issue(created_id)
            finally:
                provider.close()
        else:
            print("Unconfirmed creation; inspect the Trello list before retry:", title)
