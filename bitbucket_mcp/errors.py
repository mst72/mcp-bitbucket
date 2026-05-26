"""Error handling for Bitbucket Cloud API interactions."""

import requests
from typing import Optional


class BitbucketError(Exception):
    """Base exception for Bitbucket operations."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        result = {"error": self.message}
        if self.status_code:
            result["status_code"] = self.status_code
        if self.details:
            result["details"] = self.details
        return result


class AuthenticationError(BitbucketError):
    pass


class PermissionError(BitbucketError):
    pass


class NotFoundError(BitbucketError):
    pass


class ConflictError(BitbucketError):
    pass


class BadRequestError(BitbucketError):
    pass


class RateLimitError(BitbucketError):
    pass


class ServerError(BitbucketError):
    pass


def handle_api_error(response: requests.Response) -> None:
    try:
        error_data = response.json()
        error_message = error_data.get("error", {}).get("message", response.text)
        details = str(error_data)
    except Exception:
        error_message = response.text or f"HTTP {response.status_code}"
        details = None

    status_code = response.status_code

    if status_code == 400:
        raise BadRequestError(f"Bad request: {error_message}", status_code=status_code, details=details)
    elif status_code == 401:
        raise AuthenticationError("Authentication failed. Check your email and app password.", status_code=status_code, details=details)
    elif status_code == 403:
        raise PermissionError("Permission denied.", status_code=status_code, details=details)
    elif status_code == 404:
        raise NotFoundError(f"Resource not found: {error_message}", status_code=status_code, details=details)
    elif status_code == 409:
        raise ConflictError(f"Conflict: {error_message}", status_code=status_code, details=details)
    elif status_code == 429:
        raise RateLimitError("Rate limit exceeded. Try again later.", status_code=status_code, details=details)
    elif status_code >= 500:
        raise ServerError(f"Server error: {error_message}", status_code=status_code, details=details)
    else:
        raise BitbucketError(f"Request failed: {error_message}", status_code=status_code, details=details)
