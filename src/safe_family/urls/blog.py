"""Technical blog routes: Markdown posts with tags, rendered server-side."""

from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from config.settings import settings
from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import db, local_tz
from src.safe_family.core.models import BlogPost, BlogTag
from src.safe_family.utils.markdown_render import markdown_excerpt, render_markdown

blog_bp = Blueprint("blog", __name__)

TITLE_MAX_LENGTH = 200
TAG_MAX_LENGTH = 64
POSTS_PER_PAGE = 10


def _to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(local_tz)


def _attach_local_timestamps(post: BlogPost) -> None:
    post.created_local = _to_local(post.created_at)
    post.updated_local = _to_local(post.updated_at)


def _parse_tag_names(raw: str) -> list[str]:
    names = {name.strip().lower()[:TAG_MAX_LENGTH] for name in raw.split(",")}
    return sorted(name for name in names if name)


def _resolve_tags(user_id: str, names: list[str]) -> list[BlogTag]:
    tags = []
    for name in names:
        tag = BlogTag.query.filter_by(user_id=user_id, name=name).first()
        if tag is None:
            tag = BlogTag(user_id=user_id, name=name)
            db.session.add(tag)
        tags.append(tag)
    return tags


def _read_form() -> tuple[dict, str | None]:
    """Return (form values, error message) for the post editor form."""
    values = {
        "title": (request.form.get("title") or "").strip(),
        "markdown": (request.form.get("markdown") or "").replace("\r\n", "\n"),
        "tags": request.form.get("tags") or "",
        "is_public": request.form.get("is_public") == "on",
    }
    if not values["title"]:
        return values, "Title is required."
    if len(values["title"]) > TITLE_MAX_LENGTH:
        return values, f"Title must be at most {TITLE_MAX_LENGTH} characters."
    if not values["markdown"].strip():
        return values, "Content is required."
    size = len(values["markdown"].encode("utf-8"))
    if size > settings.BLOG_MAX_MARKDOWN_BYTES:
        limit_kb = settings.BLOG_MAX_MARKDOWN_BYTES // 1024
        return values, f"Post is too large ({size // 1024} KB); the limit is {limit_kb} KB."
    return values, None


def _get_own_post(post_id: str, user_id: str) -> BlogPost:
    post = BlogPost.query.filter_by(id=post_id, user_id=user_id).one_or_none()
    if post is None:
        abort(404)
    return post


def _render_editor(post: BlogPost | None, values: dict, status: int = 200) -> tuple[str, int]:
    return (
        render_template(
            "blog/blog_edit.html",
            post=post,
            values=values,
            max_bytes=settings.BLOG_MAX_MARKDOWN_BYTES,
        ),
        status,
    )


@blog_bp.get("/blog")
@login_required
def blog_list():
    """List the user's own posts plus everyone's public posts."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    page = request.args.get("page", 1, type=int)
    tag_filter = (request.args.get("tag") or "").strip().lower()

    query = BlogPost.query.filter(
        or_(BlogPost.user_id == user.id, BlogPost.is_public.is_(True)),
    )
    if tag_filter:
        query = query.filter(BlogPost.tags.any(BlogTag.name == tag_filter))
    pagination = (
        query.options(selectinload(BlogPost.tags))
        .order_by(BlogPost.created_at.desc())
        .paginate(page=page, per_page=POSTS_PER_PAGE, error_out=False)
    )

    posts = pagination.items
    for post in posts:
        _attach_local_timestamps(post)
        post.excerpt = markdown_excerpt(post.markdown)

    return render_template(
        "blog/blog_list.html",
        posts=posts,
        pagination=pagination,
        tag_filter=tag_filter,
        current_user_id=user.id,
    )


@blog_bp.get("/blog/new")
@login_required
def blog_new():
    """Render an empty post editor."""
    values = {"title": "", "markdown": "", "tags": "", "is_public": False}
    return _render_editor(None, values)


@blog_bp.post("/blog/new")
@login_required
def blog_create():
    """Create a post from the editor form."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    values, error = _read_form()
    if error:
        flash(error, "warning")
        return _render_editor(None, values, 400)

    now = datetime.now(UTC).replace(tzinfo=None)
    post = BlogPost(
        user_id=user.id,
        title=values["title"],
        markdown=values["markdown"],
        is_public=values["is_public"],
        created_at=now,
        updated_at=now,
    )
    post.tags = _resolve_tags(user.id, _parse_tag_names(values["tags"]))
    db.session.add(post)
    db.session.commit()
    flash("Post published." if post.is_public else "Draft saved.", "success")
    return redirect(url_for("blog.blog_view", post_id=post.id))


@blog_bp.get("/blog/<post_id>")
def blog_view(post_id: str):
    """Show a rendered post. Public posts are readable without logging in."""
    post = (
        BlogPost.query.options(selectinload(BlogPost.tags))
        .filter_by(id=post_id)
        .one_or_none()
    )
    if post is None:
        abort(404)
    user = get_current_username()
    is_owner = user is not None and user.id == post.user_id
    if not is_owner and not post.is_public:
        abort(404)

    _attach_local_timestamps(post)
    return render_template(
        "blog/blog_view.html",
        post=post,
        body_html=render_markdown(post.markdown),
        is_owner=is_owner,
    )


@blog_bp.get("/blog/<post_id>/edit")
@login_required
def blog_edit(post_id: str):
    """Render the editor pre-filled with the post's original Markdown."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    post = _get_own_post(post_id, user.id)
    values = {
        "title": post.title,
        "markdown": post.markdown,
        "tags": ", ".join(tag.name for tag in post.tags),
        "is_public": post.is_public,
    }
    return _render_editor(post, values)


@blog_bp.post("/blog/<post_id>/edit")
@login_required
def blog_update(post_id: str):
    """Save edits to an existing post."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    post = _get_own_post(post_id, user.id)
    values, error = _read_form()
    if error:
        flash(error, "warning")
        return _render_editor(post, values, 400)

    post.title = values["title"]
    post.markdown = values["markdown"]
    post.is_public = values["is_public"]
    post.tags = _resolve_tags(user.id, _parse_tag_names(values["tags"]))
    post.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.session.commit()
    flash("Post updated.", "success")
    return redirect(url_for("blog.blog_view", post_id=post.id))


@blog_bp.post("/blog/<post_id>/delete")
@login_required
def blog_delete(post_id: str):
    """Delete a post."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    post = _get_own_post(post_id, user.id)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "success")
    return redirect(url_for("blog.blog_list"))


@blog_bp.post("/blog/preview")
@login_required
def blog_preview():
    """Render Markdown for the editor's live preview pane."""
    source = request.form.get("markdown") or ""
    if len(source.encode("utf-8")) > settings.BLOG_MAX_MARKDOWN_BYTES:
        return jsonify({"error": "Post is too large to preview."}), 413
    return jsonify({"html": str(render_markdown(source))})
