"""Tests for bitbucket_mcp.client module."""

import pytest
import responses

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.errors import AuthenticationError, NotFoundError, ConflictError

BASE = "https://api.bitbucket.org/2.0"


@pytest.fixture
def client():
    return BitbucketClient(
        email="test@example.com",
        api_token="test-token",
        workspace="testws",
    )


class TestClientInit:
    def test_creates_session_with_basic_auth(self, client):
        assert client.session.auth is not None
        assert client.workspace == "testws"
        assert client.base_url == BASE


class TestListPullRequests:
    @responses.activate
    def test_list_open_prs(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests",
            json={
                "pagelen": 10,
                "size": 1,
                "values": [
                    {
                        "id": 1,
                        "title": "Test PR",
                        "state": "OPEN",
                        "author": {"display_name": "Alice"},
                        "source": {"branch": {"name": "feature/x"}},
                        "destination": {"branch": {"name": "main"}},
                        "created_on": "2025-01-01T00:00:00+00:00",
                        "updated_on": "2025-01-02T00:00:00+00:00",
                        "comment_count": 3,
                    }
                ],
            },
        )
        result = client.list_pull_requests("myrepo")
        assert len(result["values"]) == 1
        assert result["values"][0]["title"] == "Test PR"

    @responses.activate
    def test_list_prs_with_state_filter(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests",
            json={"pagelen": 10, "size": 0, "values": []},
        )
        client.list_pull_requests("myrepo", state="MERGED")
        assert "state=MERGED" in responses.calls[0].request.url


class TestGetPullRequest:
    @responses.activate
    def test_get_pr_by_id(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42",
            json={"id": 42, "title": "My PR", "state": "OPEN"},
        )
        result = client.get_pull_request("myrepo", 42)
        assert result["id"] == 42

    @responses.activate
    def test_get_pr_not_found(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/999",
            json={"error": {"message": "Not found"}},
            status=404,
        )
        with pytest.raises(NotFoundError):
            client.get_pull_request("myrepo", 999)


class TestCreatePullRequest:
    @responses.activate
    def test_create_pr(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests",
            json={"id": 100, "title": "New PR", "state": "OPEN"},
            status=201,
        )
        result = client.create_pull_request(
            "myrepo",
            title="New PR",
            source_branch="feature/new",
            destination_branch="main",
            description="Some changes",
        )
        assert result["id"] == 100
        body = responses.calls[0].request.body
        assert b"feature/new" in body


class TestMergePullRequest:
    @responses.activate
    def test_merge_pr(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/merge",
            json={"id": 42, "state": "MERGED"},
        )
        result = client.merge_pull_request("myrepo", 42)
        assert result["state"] == "MERGED"

    @responses.activate
    def test_merge_conflict(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/merge",
            json={"error": {"message": "Merge conflict"}},
            status=409,
        )
        with pytest.raises(ConflictError):
            client.merge_pull_request("myrepo", 42)


class TestDeclinePullRequest:
    @responses.activate
    def test_decline_pr(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/decline",
            json={"id": 42, "state": "DECLINED"},
        )
        result = client.decline_pull_request("myrepo", 42)
        assert result["state"] == "DECLINED"


class TestUpdatePullRequest:
    @responses.activate
    def test_update_title_and_description(self, client):
        responses.add(
            responses.PUT,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42",
            json={"id": 42, "title": "Updated", "description": "New desc"},
        )
        result = client.update_pull_request("myrepo", 42, title="Updated", description="New desc")
        assert result["title"] == "Updated"


class TestListPrComments:
    @responses.activate
    def test_list_comments(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/comments",
            json={
                "pagelen": 10,
                "size": 1,
                "values": [
                    {
                        "id": 1,
                        "content": {"raw": "Looks good!"},
                        "user": {"display_name": "Alice"},
                        "created_on": "2025-01-01T00:00:00+00:00",
                    }
                ],
            },
        )
        result = client.list_pr_comments("myrepo", 42)
        assert len(result["values"]) == 1


class TestAddPrComment:
    @responses.activate
    def test_add_general_comment(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/comments",
            json={"id": 10, "content": {"raw": "Nice work!"}},
            status=201,
        )
        result = client.add_pr_comment("myrepo", 42, "Nice work!")
        assert result["id"] == 10


class TestAddPrInlineComment:
    @responses.activate
    def test_add_inline_comment(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/comments",
            json={"id": 11, "content": {"raw": "Fix this"}, "inline": {"path": "src/main.py", "to": 10}},
            status=201,
        )
        result = client.add_pr_inline_comment("myrepo", 42, "Fix this", "src/main.py", to_line=10)
        assert result["inline"]["path"] == "src/main.py"


class TestApprovePullRequest:
    @responses.activate
    def test_approve(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/approve",
            json={"approved": True, "user": {"display_name": "Me"}},
        )
        result = client.approve_pull_request("myrepo", 42)
        assert result["approved"] is True


class TestGetPrDiff:
    @responses.activate
    def test_get_diff(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/diff",
            body="diff --git a/file.py b/file.py\n+new line\n",
            content_type="text/plain",
        )
        result = client.get_pr_diff("myrepo", 42)
        assert "diff --git" in result


class TestListPipelines:
    @responses.activate
    def test_list_pipelines(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pipelines/",
            json={
                "pagelen": 10,
                "size": 1,
                "values": [
                    {
                        "uuid": "{pipe-uuid}",
                        "build_number": 42,
                        "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
                        "target": {"ref_name": "main", "commit": {"hash": "abc123"}},
                        "created_on": "2025-01-01T00:00:00+00:00",
                    }
                ],
            },
        )
        result = client.list_pipelines("myrepo")
        assert len(result["values"]) == 1
        assert result["values"][0]["build_number"] == 42


class TestGetPipeline:
    @responses.activate
    def test_get_pipeline(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pipelines/%7Bpipe-uuid%7D",
            json={
                "uuid": "{pipe-uuid}",
                "build_number": 42,
                "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
            },
        )
        result = client.get_pipeline("myrepo", "{pipe-uuid}")
        assert result["build_number"] == 42


class TestGetPipelineStepLog:
    @responses.activate
    def test_get_step_log(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pipelines/%7Bpipe-uuid%7D/steps/%7Bstep-uuid%7D/log",
            body="Step 1: Installing dependencies...\nStep 2: Running tests...\nDone.",
            content_type="application/octet-stream",
        )
        result = client.get_pipeline_step_log("myrepo", "{pipe-uuid}", "{step-uuid}")
        assert "Installing dependencies" in result
