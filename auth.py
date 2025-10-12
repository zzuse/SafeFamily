from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    current_user,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from models import TokenBlocklist, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register_user():
    data = request.get_json()
    user = User.get_user_by_username(username=data.get("username"))

    if user is not None:
        return jsonify({"message": "Username already exists"}), 400
    new_user = User(
        username=data.get("username"),
        email=data.get("email"),
        role=data.get("role"),
    )
    new_user.set_password(data.get("password"))
    new_user.save()
    return jsonify({"message": "User registered successfully"}), 201


@auth_bp.post("/login")
def login_user():
    data = request.get_json()
    user = User.get_user_by_username(username=data.get("username"))

    if user is None or not user.check_password(data.get("password")):
        return jsonify({"message": "Invalid username or password"}), 401

    if user and (user.check_password(data.get("password"))):
        return jsonify(
            {
                "message": "Login successful",
                "tokens": {
                    "access_token": create_access_token(identity=user.id),
                    "refresh_token": create_refresh_token(identity=user.id),
                },
            }
        ), 200
    return jsonify({"error": "Invalid credentials"}), 401


@auth_bp.get("/whoami")
@jwt_required()
def whoami():
    claim = get_jwt()
    return jsonify(
        {
            "message": "You are authenticated",
            "claim": claim,
            "user": current_user.username,
            "email": current_user.email,
        }
    ), 200


@auth_bp.get("/refresh")
@jwt_required(refresh=True)
def refresh_access():
    current_identity = get_jwt_identity()
    new_access_token = create_access_token(identity=current_identity)
    return jsonify({"message": current_identity, "access_token": new_access_token}), 200


@auth_bp.get("/logout")
@jwt_required(verify_type=False)
def logout():
    jwt = get_jwt()
    jti = jwt["jti"]
    token_type = jwt["type"]
    token = TokenBlocklist(jti=jti)
    token.save()
    return jsonify({"msg": f"{token_type} token has been revoked"}), 200
