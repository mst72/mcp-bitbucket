"""Tests for bitbucket_mcp.errors module."""

import pytest
from unittest.mock import MagicMock
import requests

from bitbucket_mcp.errors import (
    BitbucketError,
    AuthenticationError,
    PermissionError as BbPermissionError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    handle_api_error,
)


class TestBitbucketError:
    def test_to_dict_basic(self):
        err = BitbucketError("something broke")
        assert err.to_dict() == {"error": "something broke"}

    def test_to_dict_with_status_and_details(self):
        err = BitbucketError("fail", status_code=500, details="server error")
        result = err.to_dict()
        assert result["error"] == "fail"
        assert result["status_code"] == 500
        assert result["details"] == "server error"


class TestHandleApiError:
    def _mock_response(self, status_code, json_body=None, text=""):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = status_code
        resp.text = text
        if json_body is not None:
            resp.json.return_value = json_body
        else:
            resp.json.side_effect = ValueError("No JSON")
        return resp

    def test_401_raises_authentication_error(self):
        resp = self._mock_response(401, {"error": {"message": "Unauthorized"}})
        with pytest.raises(AuthenticationError):
            handle_api_error(resp)

    def test_403_raises_permission_error(self):
        resp = self._mock_response(403, {"error": {"message": "Forbidden"}})
        with pytest.raises(BbPermissionError):
            handle_api_error(resp)

    def test_404_raises_not_found_error(self):
        resp = self._mock_response(404, {"error": {"message": "Not found"}})
        with pytest.raises(NotFoundError):
            handle_api_error(resp)

    def test_409_raises_conflict_error(self):
        resp = self._mock_response(409, {"error": {"message": "Merge conflict"}})
        with pytest.raises(ConflictError):
            handle_api_error(resp)

    def test_429_raises_rate_limit_error(self):
        resp = self._mock_response(429, {"error": {"message": "Rate limited"}})
        with pytest.raises(RateLimitError):
            handle_api_error(resp)

    def test_server_error_uses_server_error_envelope_message(self):
        resp = self._mock_response(
            400,
            {"errors": [{"message": "The path query parameter is required when retrieving comments."}]},
            text='{"errors":[{"message":"The path query parameter is required when retrieving comments."}]}',
        )
        with pytest.raises(BitbucketError, match="The path query parameter is required when retrieving comments."):
            handle_api_error(resp)

    def test_non_json_response(self):
        resp = self._mock_response(500, json_body=None, text="Internal Server Error")
        with pytest.raises(BitbucketError, match="Internal Server Error"):
            handle_api_error(resp)
