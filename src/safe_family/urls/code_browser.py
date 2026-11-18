"""Read-only browser for a folder of Markdown and Python files (admin only).

The folder comes from settings.CODE_BROWSER_ROOT and is read fresh on every
request: one directory listing or one file per page, nothing is cached, so
edits and new files show up on the next reload and pointing the setting at a
different folder needs no code change.
"""

from pathlib import Path, PurePosixPath

from flask import Blueprint, abort, redirect, render_template, request, send_file
from markupsafe import Markup
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from config.settings import settings
from src.safe_family.core.auth import admin_required
from src.safe_family.utils.markdown_render import render_markdown

code_bp = Blueprint("code_browser", __name__)

PAGE_SUFFIXES = {".md", ".py"}
# Served as-is so Markdown files can show the images next to them.
RAW_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
HIDDEN_DIRS = {"__pycache__", "node_modules"}
MAX_FILE_BYTES = 2 * 1024 * 1024

_PY_FORMATTER = HtmlFormatter(
    cssclass="codehilite",
    linenos="inline",
    lineanchors="L",
    anchorlinenos=True,
)


def _root() -> Path | None:
    root = Path(settings.CODE_BROWSER_ROOT).expanduser().resolve()
    return root if root.is_dir() else None


def _resolve(root: Path, subpath: str) -> Path:
    """Map a URL path to a file under root, or 404.

    Dot-names (".git", "..", ".env") are refused outright, and the resolved
    path must stay inside root, so symlinks cannot lead out of it either.
    """
    parts = PurePosixPath(subpath).parts
    if any(part.startswith(".") or part in HIDDEN_DIRS for part in parts):
        abort(404)
    target = (root / subpath).resolve()
    if not target.is_relative_to(root) or not target.exists():
        abort(404)
    return target


def _breadcrumbs(subpath: str) -> list[tuple[str, str]]:
    crumbs = []
    url = "/code/"
    for part in PurePosixPath(subpath).parts:
        url += part + "/"
        crumbs.append((part, url))
    return crumbs


def _list_dir(directory: Path) -> tuple[list[str], list[str]]:
    dirs, files = [], []
    for entry in directory.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.name not in HIDDEN_DIRS:
                dirs.append(entry.name)
        elif entry.suffix.lower() in PAGE_SUFFIXES:
            files.append(entry.name)
    return sorted(dirs, key=str.lower), sorted(files, key=str.lower)


def _read_text(path: Path) -> str | None:
    if path.stat().st_size > MAX_FILE_BYTES:
        return None
    return path.read_bytes().decode("utf-8", errors="replace")


def _render_file(path: Path) -> Markup | None:
    text = _read_text(path)
    if text is None:
        return None
    if path.suffix.lower() == ".md":
        return render_markdown(text)
    # Pygments escapes the source itself, so its output is safe HTML.
    return Markup(highlight(text, PythonLexer(), _PY_FORMATTER))  # noqa: S704


@code_bp.route("/code/", defaults={"subpath": ""})
@code_bp.route("/code/<path:subpath>")
@admin_required
def code_browse(subpath: str) -> object:
    """Show a folder listing, a rendered .md/.py file, or a raw image."""
    root = _root()
    if root is None:
        return render_template("code_browser/browse.html", missing_root=True), 503

    target = _resolve(root, subpath.rstrip("/"))
    crumbs = _breadcrumbs(subpath.rstrip("/"))

    if target.is_dir():
        # Directory URLs end in "/" so relative links in READMEs resolve.
        if not request.path.endswith("/"):
            return redirect(request.path + "/", code=301)
        dirs, files = _list_dir(target)
        readme = target / "README.md"
        readme_html = _render_file(readme) if readme.is_file() else None
        return render_template(
            "code_browser/browse.html",
            root_name=root.name,
            crumbs=crumbs,
            dirs=dirs,
            files=files,
            readme_html=readme_html,
        )

    if request.path.endswith("/"):
        abort(404)
    suffix = target.suffix.lower()
    if suffix in RAW_SUFFIXES:
        response = send_file(target, max_age=300)
        # An SVG opened directly could run script on our origin; sandbox it.
        response.headers["Content-Security-Policy"] = "sandbox"
        return response
    if suffix not in PAGE_SUFFIXES:
        abort(404)
    return render_template(
        "code_browser/browse.html",
        root_name=root.name,
        crumbs=crumbs,
        file_name=target.name,
        file_kind="python" if suffix == ".py" else "markdown",
        body_html=_render_file(target),
    )
