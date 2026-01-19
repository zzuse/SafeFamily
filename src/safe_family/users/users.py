"""User URL routes for Safe Family application."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from src.safe_family.core.models import User
from src.safe_family.core.schemas import UserOut

user_bp = Blueprint("users", __name__)


@user_bp.route("/all", methods=["GET"])
@jwt_required()
def get_all_users():
    """Get a paginated list of all users. Admins only."""
    claims = get_jwt()
    if claims.get("is_admin") != "admin":
        return jsonify({"msg": "Admins only!"}), 403
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=3, type=int)
    users = User.query.paginate(page=page, per_page=per_page)
    result = [UserOut.model_validate(user).model_dump() for user in users.items]
    return jsonify({"users": result}), 200
