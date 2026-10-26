"""Tests for the technical blog routes and Markdown rendering."""

from datetime import datetime

from flask_jwt_extended import create_access_token

from src.safe_family.core.extensions import db
from src.safe_family.core.models import BlogPost, BlogTag, User
from src.safe_family.utils.markdown_render import markdown_excerpt, render_markdown


def _make_user(user_id, username):
    user = User(id=user_id, username=username, email=f"{username}@example.com", role="user")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()
    return user


def _login_session(app, client, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    with client.session_transaction() as sess:
        sess["access_token"] = token


def _make_post(user_id, title="Post", markdown="Body", *, is_public=False, tags=()):
    now = datetime(2026, 1, 2, 3, 4, 5)
    post = BlogPost(
        user_id=user_id,
        title=title,
        markdown=markdown,
        is_public=is_public,
        created_at=now,
        updated_at=now,
    )
    post.tags = [BlogTag(user_id=user_id, name=name) for name in tags]
    db.session.add(post)
    db.session.commit()
    return post.id


def test_render_markdown_sanitizes_and_highlights():
    html = render_markdown(
        "# Hi\n\n<script>alert(1)</script>[x](javascript:alert(1))"
        "<img src=x onerror=alert(1)>\n\n```python\ndef f():\n    pass\n```\n\n"
        "| a | b |\n|---|:-:|\n| 1 | 2 |\n",
    )

    assert '<h1 id="hi">Hi</h1>' in html
    assert "<script" not in html
    assert "javascript:" not in html
    assert "onerror" not in html
    assert 'class="codehilite"' in html
    assert '<span class="k">def</span>' in html
    assert '<td align="center">2</td>' in html


def test_render_markdown_handles_empty():
    assert str(render_markdown("")) == ""
    assert str(render_markdown(None)) == ""


def test_markdown_excerpt_plain_text_and_truncation():
    assert markdown_excerpt("**bold** & `a<b`") == "bold & a<b"
    excerpt = markdown_excerpt("word " * 100, limit=22)
    assert excerpt == "word word word word…"


def test_blog_list_requires_login(notesync_client):
    resp = notesync_client.get("/blog")

    assert resp.status_code == 302
    assert resp.location.endswith("/auth/login-ui")


def test_blog_list_shows_own_and_public_posts(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _make_user("u-other", "bob")
    _make_post("u-blog", title="My draft")
    _make_post("u-other", title="Bob public", is_public=True)
    _make_post("u-other", title="Bob secret")
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.get("/blog")

    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "My draft" in body
    assert "Bob public" in body
    assert "Bob secret" not in body
    assert ">Blog</a>" in body


def test_blog_list_filters_by_tag(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _make_post("u-blog", title="Rust post", tags=["rust"])
    _make_post("u-blog", title="Go post", tags=["go"])
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.get("/blog?tag=Rust")

    body = resp.get_data(as_text=True)
    assert "Rust post" in body
    assert "Go post" not in body
    assert "clear filter" in body


def test_blog_list_paginates(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    for i in range(12):
        _make_post("u-blog", title=f"Post {i}")
    _login_session(notesync_app, notesync_client, "u-blog")

    body = notesync_client.get("/blog?page=2").get_data(as_text=True)

    assert "Page 2 / 2" in body
    assert "Newer" in body


def test_blog_new_renders_editor(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.get("/blog/new")

    assert resp.status_code == 200
    assert "New post" in resp.get_data(as_text=True)


def test_blog_create_stores_markdown_and_tags(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.post(
        "/blog/new",
        data={
            "title": "  Hello  ",
            "markdown": "# Hi\r\n\r\nraw *md*",
            "tags": "Python, flask, python,",
            "is_public": "on",
        },
    )

    assert resp.status_code == 302
    post = BlogPost.query.one()
    assert resp.location.endswith(f"/blog/{post.id}")
    assert post.title == "Hello"
    assert post.markdown == "# Hi\n\nraw *md*"
    assert post.is_public is True
    assert post.created_at == post.updated_at
    assert [tag.name for tag in post.tags] == ["flask", "python"]


def test_blog_create_reuses_existing_tags(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _make_post("u-blog", tags=["python"])
    _login_session(notesync_app, notesync_client, "u-blog")

    notesync_client.post(
        "/blog/new",
        data={"title": "Second", "markdown": "x", "tags": "python"},
    )

    assert BlogTag.query.filter_by(user_id="u-blog", name="python").count() == 1


def test_blog_create_validation_errors(notesync_app, notesync_client, monkeypatch):
    _make_user("u-blog", "alice")
    _login_session(notesync_app, notesync_client, "u-blog")
    monkeypatch.setattr("config.settings.settings.BLOG_MAX_MARKDOWN_BYTES", 10)

    cases = [
        ({"title": "", "markdown": "x"}, "Title is required."),
        ({"title": "t" * 201, "markdown": "x"}, "at most 200"),
        ({"title": "t", "markdown": "   "}, "Content is required."),
        ({"title": "t", "markdown": "x" * 11}, "too large"),
    ]
    for data, message in cases:
        resp = notesync_client.post("/blog/new", data=data)
        assert resp.status_code == 400
        assert message in resp.get_data(as_text=True)
    assert BlogPost.query.count() == 0


def test_blog_view_renders_markdown_for_owner(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    post_id = _make_post("u-blog", title="Draft", markdown="## Section\n\n<script>x</script>")
    _login_session(notesync_app, notesync_client, "u-blog")

    body = notesync_client.get(f"/blog/{post_id}").get_data(as_text=True)

    assert '<h2 id="section">Section</h2>' in body
    assert "<script>x</script>" not in body
    assert "only you can see this" in body
    assert f"/blog/{post_id}/edit" in body


def test_blog_view_public_post_without_login(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    post_id = _make_post("u-blog", title="Open", is_public=True)

    resp = notesync_client.get(f"/blog/{post_id}")

    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Open" in body
    assert "/edit" not in body


def test_blog_view_hides_drafts_from_others(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _make_user("u-other", "bob")
    post_id = _make_post("u-blog", title="Secret")

    assert notesync_client.get(f"/blog/{post_id}").status_code == 404
    _login_session(notesync_app, notesync_client, "u-other")
    assert notesync_client.get(f"/blog/{post_id}").status_code == 404
    assert notesync_client.get("/blog/missing").status_code == 404


def test_blog_edit_prefills_original_markdown(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    post_id = _make_post("u-blog", markdown="**raw** <b>", tags=["a", "b"])
    _login_session(notesync_app, notesync_client, "u-blog")

    body = notesync_client.get(f"/blog/{post_id}/edit").get_data(as_text=True)

    assert "**raw** &lt;b&gt;" in body
    assert 'value="a, b"' in body


def test_blog_update_changes_content_and_timestamp(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    post_id = _make_post("u-blog", tags=["old"])
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.post(
        f"/blog/{post_id}/edit",
        data={"title": "New title", "markdown": "new body", "tags": "new"},
    )

    assert resp.status_code == 302
    post = db.session.get(BlogPost, post_id)
    assert post.title == "New title"
    assert post.markdown == "new body"
    assert post.is_public is False
    assert post.updated_at > post.created_at
    assert [tag.name for tag in post.tags] == ["new"]


def test_blog_update_validation_error(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    post_id = _make_post("u-blog", title="Keep")
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.post(f"/blog/{post_id}/edit", data={"title": "", "markdown": "x"})

    assert resp.status_code == 400
    assert db.session.get(BlogPost, post_id).title == "Keep"


def test_blog_edit_and_delete_forbidden_for_other_user(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    _make_user("u-other", "bob")
    post_id = _make_post("u-blog", is_public=True)
    _login_session(notesync_app, notesync_client, "u-other")

    assert notesync_client.get(f"/blog/{post_id}/edit").status_code == 404
    assert (
        notesync_client.post(
            f"/blog/{post_id}/edit",
            data={"title": "hacked", "markdown": "x"},
        ).status_code
        == 404
    )
    assert notesync_client.post(f"/blog/{post_id}/delete").status_code == 404
    assert db.session.get(BlogPost, post_id).title == "Post"


def test_blog_delete_removes_post(notesync_app, notesync_client):
    _make_user("u-blog", "alice")
    post_id = _make_post("u-blog", tags=["t"])
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.post(f"/blog/{post_id}/delete")

    assert resp.status_code == 302
    assert resp.location.endswith("/blog")
    assert BlogPost.query.count() == 0


def test_blog_preview_renders_and_limits_size(notesync_app, notesync_client, monkeypatch):
    _make_user("u-blog", "alice")
    _login_session(notesync_app, notesync_client, "u-blog")

    resp = notesync_client.post("/blog/preview", data={"markdown": "*hi*"})
    assert resp.get_json() == {"html": "<p><em>hi</em></p>"}

    monkeypatch.setattr("config.settings.settings.BLOG_MAX_MARKDOWN_BYTES", 3)
    resp = notesync_client.post("/blog/preview", data={"markdown": "*hi*"})
    assert resp.status_code == 413


def test_blog_routes_reject_unknown_session_user(notesync_app, notesync_client):
    _login_session(notesync_app, notesync_client, "ghost")

    for method, path in [
        ("get", "/blog"),
        ("post", "/blog/new"),
        ("get", "/blog/x/edit"),
        ("post", "/blog/x/edit"),
        ("post", "/blog/x/delete"),
    ]:
        resp = getattr(notesync_client, method)(path)
        assert resp.status_code == 302
        assert resp.location.endswith("/auth/login-ui")
