"""Tests for auto_git utilities."""

from src.safe_family.auto_git import auto_git


def test_rule_auto_commit_writes_files(monkeypatch, tmp_path):
    class AutoCursor:
        def __init__(self):
            self.calls = 0

        def execute(self, sql, params=None):
            return None

        def fetchall(self):
            self.calls += 1
            if self.calls == 1:
                return [("example%com", "game")]
            return [("filter*",)]

    class AutoConn:
        def __init__(self):
            self.cursor_obj = AutoCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            return None

    conn = AutoConn()
    monkeypatch.setattr(auto_git, "get_db_connection", lambda: conn)
    monkeypatch.setattr(auto_git.settings, "ADGUARD_RULE_PATH", str(tmp_path) + "/")
    monkeypatch.setattr(auto_git.shutil, "which", lambda cmd: "/usr/bin/git")
    calls = []
    monkeypatch.setattr(
        auto_git.subprocess,
        "check_call",
        lambda args, cwd=None: calls.append((tuple(args), cwd)),
    )

    auto_git.rule_auto_commit()

    block_file = tmp_path / "block_game.txt"
    assert block_file.exists()
    content = block_file.read_text()
    assert "||examplecom^" in content
    filter_file = tmp_path / "filter.txt"
    assert filter_file.exists()
    assert calls
