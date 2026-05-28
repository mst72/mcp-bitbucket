"""Focused tests for Bitbucket Server/Data Center comment listing behavior."""

import responses

from bitbucket_mcp.client import BitbucketClient

BASE = "https://stash.example.com/rest/api/1.0"


def make_client() -> BitbucketClient:
    return BitbucketClient(
        base_url="https://stash.example.com",
        api_token="test-token",
        project="SPGAIIN",
    )


class TestListPrCommentsFallback:
    @responses.activate
    def test_falls_back_to_activities_when_comments_endpoint_requires_path(self):
        client = make_client()
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/comments",
            json={
                "errors": [
                    {
                        "context": None,
                        "message": "The path query parameter is required when retrieving comments.",
                        "exceptionName": None,
                    }
                ]
            },
            status=400,
        )
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/activities",
            json={
                "size": 2,
                "limit": 50,
                "isLastPage": True,
                "start": 0,
                "values": [
                    {
                        "action": "COMMENTED",
                        "commentAction": "ADDED",
                        "comment": {
                            "id": 14665,
                            "text": "Test comment: we are testing the Bitbucket MCP integration.",
                            "author": {"displayName": "Alexey Mikhalchenkov"},
                            "createdDate": 1748366372000,
                            "updatedDate": 1748366372000,
                            "comments": [],
                        },
                    },
                    {
                        "action": "COMMENTED",
                        "commentAction": "ADDED",
                        "commentAnchor": {
                            "path": "README.md",
                            "line": 12,
                            "lineType": "ADDED",
                        },
                        "comment": {
                            "id": 14666,
                            "text": "Please update this section too.",
                            "author": {"displayName": "Reviewer"},
                            "createdDate": 1748366373000,
                            "updatedDate": 1748366373000,
                            "comments": [
                                {
                                    "id": 14667,
                                    "text": "Done in the next commit.",
                                    "author": {"displayName": "Alexey Mikhalchenkov"},
                                    "createdDate": 1748366374000,
                                    "updatedDate": 1748366374000,
                                    "comments": [],
                                }
                            ],
                        },
                    },
                ],
            },
        )

        result = client.list_pr_comments("spg-ai-qa-flow", 9)

        assert [comment["id"] for comment in result["values"]] == [14665, 14666, 14667]
        assert result["values"][1]["anchor"]["path"] == "README.md"
        assert result["values"][1]["anchor"]["line"] == 12
        assert result["values"][2]["parent"]["id"] == 14666

    @responses.activate
    def test_deleted_parent_removes_reply_subtree(self):
        client = make_client()
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/comments",
            json={
                "errors": [
                    {
                        "context": None,
                        "message": "The path query parameter is required when retrieving comments.",
                        "exceptionName": None,
                    }
                ]
            },
            status=400,
        )
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/activities",
            json={
                "size": 2,
                "limit": 50,
                "isLastPage": True,
                "start": 0,
                "values": [
                    {
                        "action": "COMMENTED",
                        "commentAction": "ADDED",
                        "comment": {
                            "id": 100,
                            "text": "Parent comment",
                            "author": {"displayName": "Reviewer"},
                            "comments": [
                                {
                                    "id": 101,
                                    "text": "Reply one",
                                    "author": {"displayName": "Author"},
                                    "comments": [],
                                },
                                {
                                    "id": 102,
                                    "text": "Reply two",
                                    "author": {"displayName": "Author"},
                                    "comments": [],
                                },
                            ],
                        },
                    },
                    {
                        "action": "COMMENTED",
                        "commentAction": "DELETED",
                        "comment": {
                            "id": 100,
                            "text": "Parent comment",
                            "author": {"displayName": "Reviewer"},
                            "comments": [],
                        },
                    },
                ],
            },
        )

        result = client.list_pr_comments("spg-ai-qa-flow", 9)

        assert result["values"] == []
        assert result["size"] == 0

    @responses.activate
    def test_paginates_activities_until_comment_page_is_complete(self):
        client = make_client()
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/comments",
            json={
                "errors": [
                    {
                        "context": None,
                        "message": "The path query parameter is required when retrieving comments.",
                        "exceptionName": None,
                    }
                ]
            },
            status=400,
        )
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/activities",
            match=[responses.matchers.query_param_matcher({"start": "0", "limit": "50"})],
            json={
                "size": 50,
                "limit": 50,
                "isLastPage": False,
                "start": 0,
                "nextPageStart": 50,
                "values": [
                    {"action": "APPROVED"},
                    {
                        "action": "COMMENTED",
                        "commentAction": "ADDED",
                        "comment": {
                            "id": 201,
                            "text": "First comment",
                            "author": {"displayName": "Reviewer"},
                            "comments": [],
                        },
                    },
                ],
            },
        )
        responses.add(
            responses.GET,
            f"{BASE}/projects/SPGAIIN/repos/spg-ai-qa-flow/pull-requests/9/activities",
            match=[responses.matchers.query_param_matcher({"start": "50", "limit": "50"})],
            json={
                "size": 2,
                "limit": 50,
                "isLastPage": True,
                "start": 50,
                "values": [
                    {
                        "action": "COMMENTED",
                        "commentAction": "ADDED",
                        "comment": {
                            "id": 202,
                            "text": "Second comment",
                            "author": {"displayName": "Reviewer"},
                            "comments": [],
                        },
                    },
                    {
                        "action": "COMMENTED",
                        "commentAction": "ADDED",
                        "comment": {
                            "id": 203,
                            "text": "Third comment",
                            "author": {"displayName": "Reviewer"},
                            "comments": [],
                        },
                    },
                ],
            },
        )

        result = client.list_pr_comments("spg-ai-qa-flow", 9, start=1, limit=2)

        assert [comment["id"] for comment in result["values"]] == [202, 203]
        assert result["size"] == 3
        assert result["start"] == 1
        assert result["limit"] == 2
        assert result["isLastPage"] is True
