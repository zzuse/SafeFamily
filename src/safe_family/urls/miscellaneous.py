"""Miscellaneous URL routes for the Safe Family application."""

from flask import Blueprint, redirect, render_template

from src.safe_family.core.auth import login_required

root_bp = Blueprint("index", __name__)


@root_bp.route("/")
def index():
    """Redirect to the suspicious URLs view.

    This route redirects users to the main page for viewing suspicious URLs.
    """
    return redirect("/todo")


@root_bp.route("/store_sum")
@login_required
def store_sum():
    """Redirect to the store_sum page.

    This route redirects users to the store_sum page.
    """
    return render_template("miscellaneous/store_sum.html")


@root_bp.route("/ninja")
@login_required
def ninja_nightmare():
    """Redirect to the store_sum page.

    This route redirects users to the store_sum page.
    """
    return render_template("miscellaneous/ninja_nightmare.html")
