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
    """Render the dynamic store sum calculator.

    This route renders a page where users can calculate lotto and other item sums in real-time.
    """
    return render_template("miscellaneous/store_calculator.html")


@root_bp.route("/store_sum_static")
@login_required
def store_sum_static():
    """Render the static store_sum page.

    This route renders the original static accounting page.
    """
    return render_template("miscellaneous/store_sum.html")


@root_bp.route("/ninja")
@login_required
def ninja_nightmare():
    """Redirect to the store_sum page.

    This route redirects users to the store_sum page.
    """
    return render_template("miscellaneous/ninja_nightmare.html")
