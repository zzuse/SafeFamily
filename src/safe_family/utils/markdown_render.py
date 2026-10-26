"""Markdown to safe HTML rendering for blog posts."""

import html

import markdown
import nh3
from markupsafe import Markup

_EXTENSIONS = [
    "fenced_code",
    "tables",
    "sane_lists",
    "toc",
    "codehilite",
]
_EXTENSION_CONFIGS = {
    # Pygments emits short token classes (.k, .s, .c ...) styled in styles.css.
    "codehilite": {"guess_lang": False, "css_class": "codehilite"},
    "tables": {"use_align_attribute": True},
    "toc": {"permalink": False},
}

_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "dd", "del", "div", "dl",
    "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "kbd",
    "li", "ol", "p", "pre", "s", "span", "strong", "sub", "sup", "table",
    "tbody", "td", "th", "thead", "tr", "ul",
}  # fmt: skip
_ALLOWED_ATTRIBUTES = {
    "*": {"class", "id"},
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"align"},
    "th": {"align"},
}


def render_markdown(source: str) -> Markup:
    """Render Markdown to sanitized HTML that is safe to embed in a page.

    Raw HTML inside the Markdown is allowed but passed through an allow-list,
    so scripts, event handlers and javascript: URLs are stripped.
    """
    html = markdown.markdown(
        source or "",
        extensions=_EXTENSIONS,
        extension_configs=_EXTENSION_CONFIGS,
        output_format="html",
    )
    clean = nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )
    return Markup(clean)  # noqa: S704 - sanitized by nh3 above


def markdown_excerpt(source: str, limit: int = 200) -> str:
    """Return a plain-text excerpt of a Markdown document for list views."""
    text = nh3.clean(
        markdown.markdown(source or "", extensions=["fenced_code"]),
        tags=set(),
    )
    text = " ".join(html.unescape(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"
