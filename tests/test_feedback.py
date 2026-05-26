"""Tests for bb_submit_feedback tool."""

import pytest

from bitbucket_mcp.server import bb_submit_feedback, _slugify, FEEDBACK_DIR


class TestSlugify:
    def test_simple_text(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters(self):
        assert _slugify("Fix `bb_get_pipeline` to handle 500 errors") == "fix-bb-get-pipeline-to-handle-500-errors"

    def test_truncates_long_text(self):
        result = _slugify("a" * 100, max_len=60)
        assert len(result) <= 60

    def test_strips_leading_trailing_hyphens(self):
        assert _slugify("---hello---") == "hello"

    def test_empty_string(self):
        assert _slugify("") == ""


class TestSubmitFeedback:
    def test_creates_feedback_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        result = bb_submit_feedback("Test idea", "Some description")

        assert result["success"] is True
        assert result["file"].endswith(".md")
        assert "test-idea" in result["file"]

        filepath = tmp_path / result["file"]
        content = filepath.read_text(encoding="utf-8")
        assert 'title: "Test idea"' in content
        assert "category: idea" in content
        assert "status: open" in content
        assert "# Test idea" in content
        assert "Some description" in content

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        feedback_dir = tmp_path / "nested" / "feedback"
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", feedback_dir)
        result = bb_submit_feedback("Test", "Description")

        assert result["success"] is True
        assert feedback_dir.exists()

    def test_custom_category(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        result = bb_submit_feedback("Bug report", "Something broke", category="bug")

        assert result["success"] is True
        filepath = tmp_path / result["file"]
        content = filepath.read_text(encoding="utf-8")
        assert "category: bug" in content

    def test_empty_title_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        result = bb_submit_feedback("", "Description")
        assert "error" in result

    def test_empty_description_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        result = bb_submit_feedback("Title", "")
        assert "error" in result

    def test_whitespace_only_title_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        result = bb_submit_feedback("   ", "Description")
        assert "error" in result

    def test_description_with_markdown(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        desc = "## Problem\n\n- Item 1\n- Item 2\n\n```python\nprint('hello')\n```"
        result = bb_submit_feedback("Markdown test", desc)

        assert result["success"] is True
        filepath = tmp_path / result["file"]
        content = filepath.read_text(encoding="utf-8")
        assert "```python" in content

    def test_return_dict_structure(self, tmp_path, monkeypatch):
        monkeypatch.setattr("bitbucket_mcp.server.FEEDBACK_DIR", tmp_path)
        result = bb_submit_feedback("Structure test", "Check keys")

        assert "success" in result
        assert "file" in result
        assert "path" in result
