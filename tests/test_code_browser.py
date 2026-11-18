"""Tests for the read-only code browser at /code/."""

import pytest


@pytest.fixture
def tree(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "pkg" / "__pycache__").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("secret")
    (root / "README.md").write_text("# Project\n\nSee [mod](pkg/mod.py).\n")
    (root / "pkg" / "mod.py").write_text("def hello():\n    return '<b>'\n")
    (root / "pkg" / "notes.md").write_text("## Notes\n\n<script>alert(1)</script>\n")
    (root / "pkg" / "data.bin").write_bytes(b"\x00\x01")
    (root / "pkg" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "pkg" / "__pycache__" / "mod.pyc").write_bytes(b"x")
    (tmp_path / "outside.md").write_text("outside")
    (root / "escape.md").symlink_to(tmp_path / "outside.md")
    monkeypatch.setattr("config.settings.settings.CODE_BROWSER_ROOT", str(root))
    return root


@pytest.fixture
def admin(monkeypatch, client):
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "admin", "is_admin": "admin"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
    return client


def test_requires_login(client, tree):
    resp = client.get("/code/")
    assert resp.status_code == 302
    assert "/auth/login-ui" in resp.headers["Location"]


def test_non_admin_is_refused(monkeypatch, client, tree):
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "kid", "is_admin": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
    assert client.get("/code/").status_code == 302


def test_root_listing_shows_dirs_md_and_readme(admin, tree):
    body = admin.get("/code/").get_data(as_text=True)
    assert 'href="pkg/"' in body
    assert "README.md" in body
    assert "<h1" in body
    assert "Project" in body
    assert ".git" not in body


def test_subdir_listing_filters_files(admin, tree):
    body = admin.get("/code/pkg/").get_data(as_text=True)
    assert "mod.py" in body
    assert "notes.md" in body
    assert "data.bin" not in body
    assert "__pycache__" not in body


def test_dir_without_slash_redirects(admin, tree):
    resp = admin.get("/code/pkg")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/code/pkg/")


def test_python_file_is_highlighted_and_escaped(admin, tree):
    body = admin.get("/code/pkg/mod.py").get_data(as_text=True)
    assert 'class="codehilite"' in body
    assert 'id="L-1"' in body
    assert "&lt;b&gt;" in body
    assert "<b>'" not in body


def test_markdown_file_is_sanitized(admin, tree):
    body = admin.get("/code/pkg/notes.md").get_data(as_text=True)
    assert "Notes" in body
    assert "<script>alert(1)" not in body


def test_image_served_raw_and_sandboxed(admin, tree):
    resp = admin.get("/code/pkg/pic.png")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.headers["Content-Security-Policy"] == "sandbox"


@pytest.mark.parametrize(
    "path",
    [
        "/code/.git/config",
        "/code/pkg/__pycache__/mod.pyc",
        "/code/pkg/data.bin",
        "/code/missing.md",
        "/code/escape.md",
        "/code/pkg/mod.py/",
    ],
)
def test_refused_paths_404(admin, tree, path):
    assert admin.get(path).status_code == 404


def test_large_file_is_not_rendered(admin, tree, monkeypatch):
    monkeypatch.setattr("src.safe_family.urls.code_browser.MAX_FILE_BYTES", 5)
    body = admin.get("/code/pkg/mod.py").get_data(as_text=True)
    assert "larger than 2 MB" in body


def test_missing_root_explains_setting(admin, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "config.settings.settings.CODE_BROWSER_ROOT", str(tmp_path / "nope"),
    )
    resp = admin.get("/code/")
    assert resp.status_code == 503
    assert "CODE_BROWSER_ROOT" in resp.get_data(as_text=True)


def test_root_change_takes_effect_without_restart(admin, tree, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    (other / "fresh.md").write_text("# Fresh")
    monkeypatch.setattr("config.settings.settings.CODE_BROWSER_ROOT", str(other))
    assert "fresh.md" in admin.get("/code/").get_data(as_text=True)
