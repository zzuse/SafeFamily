"""Miscellaneous URL routes for the Safe Family application."""

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request

from config.settings import settings
from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import db
from src.safe_family.core.models import CountdownConfig

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


@root_bp.route("/calc_guide")
@login_required
def calc_guide():
    """Render the calculator guide page.

    This route renders a landing page linking to the available calculators.
    """
    return render_template("miscellaneous/calc_guide.html")


@root_bp.route("/yaw_calc")
@login_required
def yaw_calc():
    """Render the yaw calculator.

    This route renders a page where users can compute yaw from quaternion
    z/w pairs or from raw radian readings.
    """
    return render_template("miscellaneous/yaw_calculator.html")


@root_bp.route("/countdown")
@login_required
def countdown():
    """Render the countdown page.

    This route shows the days remaining until the event saved by the current
    user, falling back to COUNTDOWN_DATE / COUNTDOWN_DESCRIPTION from .env
    when the user has not saved one yet.
    """
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    config = CountdownConfig.query.filter_by(user_id=user.id).first()
    return render_template(
        "miscellaneous/countdown.html",
        countdown_date=config.target_date if config else settings.COUNTDOWN_DATE,
        countdown_description=(
            config.description if config else settings.COUNTDOWN_DESCRIPTION
        ),
    )


@root_bp.route("/countdown", methods=["POST"])
@login_required
def countdown_save():
    """Save the current user's countdown target date and description."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    target_date = (request.form.get("target_date") or "").strip()
    description = (request.form.get("description") or "").strip()
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        flash("Invalid date: use the YYYY-MM-DD format.", "danger")
        return redirect("/countdown")

    config = CountdownConfig.query.filter_by(user_id=user.id).first()
    if config is None:
        config = CountdownConfig(user_id=user.id)
        db.session.add(config)
    config.target_date = target_date
    config.description = description
    db.session.commit()
    flash("Countdown saved.", "success")
    return redirect("/countdown")


@root_bp.route("/store_sum_static")
@login_required
def store_sum_static():
    """Render the static store_sum page.

    This route renders the original static accounting page.
    """
    return render_template("miscellaneous/store_sum.html")
