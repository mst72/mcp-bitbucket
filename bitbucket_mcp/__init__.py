"""
MCP Server for Bitbucket Cloud REST API integration.
"""

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.server import main

__version__ = "0.1.0"
__all__ = ["BitbucketClient", "main"]
