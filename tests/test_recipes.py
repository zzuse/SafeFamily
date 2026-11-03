"""Tests for the static recipe pages and the hand-edited recipe data."""

import re
from pathlib import Path

import pytest

from src.safe_family.urls.recipes_data import RECIPES

STATIC_RECIPES = Path(__file__).resolve().parents[1] / "src" / "safe_family" / "static" / "recipes"
REQUIRED_TEXT = ("slug", "title", "summary")
OPTIONAL_TEXT = ("image", "servings", "time", "notes")


def _article(html):
    """The recipe article only, without the shared page layout."""
    return html.split('<article class="card recipe-detail">', 1)[1].split("</article>", 1)[0]


def _login(client, monkeypatch):
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"


def test_recipes_data_has_an_example():
    assert RECIPES, "keep at least one recipe so the page has an example to copy"


@pytest.mark.parametrize("recipe", RECIPES, ids=lambda r: r.get("slug", "?"))
def test_recipe_entry_is_well_formed(recipe):
    allowed = set(REQUIRED_TEXT) | set(OPTIONAL_TEXT) | {"tags", "ingredients", "steps"}
    assert set(recipe) <= allowed, f"unknown keys: {set(recipe) - allowed}"
    for key in REQUIRED_TEXT:
        assert isinstance(recipe.get(key), str), f"{key} must be text"
        assert recipe[key].strip(), f"{key} is empty"
    for key in OPTIONAL_TEXT:
        assert isinstance(recipe.get(key, ""), str), f"{key} must be text"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", recipe["slug"]), "slug: lowercase letters, digits, dashes"
    for key in ("ingredients", "steps"):
        items = recipe.get(key)
        assert isinstance(items, list), f"{key} must be a list of lines"
        assert items, f"{key} is empty"
        assert all(isinstance(i, str) and i.strip() for i in items), f"{key} has an empty or non-text line"
    tags = recipe.get("tags", [])
    assert isinstance(tags, list), "tags must be a list"
    assert all(isinstance(t, str) for t in tags), "tags must be text"
    if recipe.get("image"):
        assert (STATIC_RECIPES / recipe["image"]).is_file(), f"picture not found: static/recipes/{recipe['image']}"


def test_recipe_slugs_are_unique():
    slugs = [r["slug"] for r in RECIPES]
    assert len(slugs) == len(set(slugs)), "two recipes share a slug"


def test_recipes_require_login(client):
    resp = client.get("/recipes")
    assert resp.status_code == 302
    assert resp.location.endswith("/auth/login-ui")


def test_recipes_list_renders_cards(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/recipes")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    for recipe in RECIPES:
        assert recipe["title"] in html
        assert f'/recipes/{recipe["slug"]}' in html


def test_recipe_detail_shows_ingredients_steps_and_picture(client, monkeypatch):
    _login(client, monkeypatch)
    recipe = RECIPES[0]
    resp = client.get(f"/recipes/{recipe['slug']}")
    assert resp.status_code == 200
    article = _article(resp.get_data(as_text=True))
    assert recipe["title"] in article
    assert article.count('type="checkbox"') == len(recipe["ingredients"])
    steps = article.split('<ol class="recipe-steps">', 1)[1].split("</ol>", 1)[0]
    assert steps.count("<li>") == len(recipe["steps"])
    if recipe.get("image"):
        assert f"/static/recipes/{recipe['image']}" in article


def test_recipe_detail_unknown_slug_is_404(client, monkeypatch):
    _login(client, monkeypatch)
    assert client.get("/recipes/no-such-recipe").status_code == 404


def test_recipe_without_picture_or_optional_fields(client, monkeypatch):
    _login(client, monkeypatch)
    bare = {
        "slug": "bare",
        "title": "Bare Recipe",
        "summary": "No picture.",
        "ingredients": ["water"],
        "steps": ["boil"],
    }
    monkeypatch.setattr("src.safe_family.urls.miscellaneous.RECIPES", [bare])
    listing = client.get("/recipes").get_data(as_text=True)
    assert "recipe-card-img--empty" in listing
    detail = client.get("/recipes/bare")
    assert detail.status_code == 200
    assert "<img" not in _article(detail.get_data(as_text=True))


def test_recipes_empty_list(client, monkeypatch):
    _login(client, monkeypatch)
    monkeypatch.setattr("src.safe_family.urls.miscellaneous.RECIPES", [])
    assert "No recipes yet" in client.get("/recipes").get_data(as_text=True)
