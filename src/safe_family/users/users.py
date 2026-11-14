"""User URL routes for Safe Family application."""

from flask import Blueprint, abort, flash, jsonify, redirect, request
from flask_jwt_extended import get_jwt, jwt_required

from src.safe_family.core.auth import admin_required, is_admin_claims
from src.safe_family.core.extensions import db
from src.safe_family.core.models import User
from src.safe_family.core.schemas import UserOut

user_bp = Blueprint("users", __name__)


@user_bp.route("/all", methods=["GET"])
@jwt_required()
def get_all_users():
    """Get a paginated list of all users. Admins only."""
    claims = get_jwt()
    if not is_admin_claims(claims):
        return jsonify({"msg": "Admins only!"}), 403
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=3, type=int)
    users = User.query.paginate(page=page, per_page=per_page)
    result = [UserOut.model_validate(user).model_dump() for user in users.items]
    return jsonify({"users": result}), 200


def accounts_for_admin() -> list[User]:
    """Return every account, waiting-for-approval first, for the MGMT page."""
    return User.query.order_by(User.is_approved.asc(), User.username.asc()).all()


@user_bp.post("/<user_id>/approve")
@admin_required
def approve_user(user_id: str):
    """Mark an account as family, or take that back with approved=0."""
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    user.is_approved = request.form.get("approved", "1") == "1"
    db.session.commit()
    state = "approved as family" if user.is_approved else "no longer approved"
    flash(f"{user.username} is {state}.", "success")
    return redirect("/suspicious")
