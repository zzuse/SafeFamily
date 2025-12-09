"""Authentication routes and session management for Safe Family application."""

from functools import wraps

import jwt as jwt_inner
from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from src.safe_family.core.models import TokenBlocklist, User
from src.safe_family.utils.constants import HTTP_CREATED, HTTP_OK

auth_bp = Blueprint("auth", __name__)


# API-based authentication routes
# Using jwt_required decorator for protecting routes
@auth_bp.post("/register")
def register_user():
    """Register a new user."""
    data = getattr(g, "_json_data", None) or request.get_json()
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
    return jsonify({"message": "User registered successfully"}), HTTP_CREATED


@auth_bp.post("/login")
def login_user():
    """Authenticate user and return JWT tokens."""
    data = getattr(g, "_json_data", None) or request.get_json()
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
            },
        ), HTTP_OK
    return jsonify({"error": "Invalid credentials"}), 401


@auth_bp.post("/change-password")
@jwt_required()
def change_password():
    """Change the password for the authenticated user."""
    data = request.get_json()
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if user is None:
        return jsonify({"message": "User not found"}), 404

    if user.change_password(old_password, new_password):
        return jsonify({"message": "Password changed successfully"}), HTTP_OK
    return jsonify({"message": "Old password is incorrect"}), 400


@auth_bp.get("/whoami")
@jwt_required()
def whoami():
    """Get information about the currently authenticated user."""
    claim = get_jwt()
    return jsonify(
        {
            "message": "You are authenticated",
            "claim": claim,
            "user": current_user.username,
            "email": current_user.email,
        },
    ), 200


@auth_bp.get("/refresh")
@jwt_required(refresh=True)
def refresh_access():
    """Refresh the access token using a valid refresh token."""
    current_identity = get_jwt_identity()
    new_access_token = create_access_token(identity=current_identity)
    return jsonify(
        {"message": current_identity, "access_token": new_access_token},
    ), HTTP_OK


@auth_bp.get("/logout")
@jwt_required(verify_type=False)
def logout():
    """Logout the user by revoking the current token."""
    token = get_jwt()
    jti = token["jti"]
    token_type = token["type"]
    token = TokenBlocklist(jti=jti)
    token.save()
    return jsonify({"msg": f"{token_type} token has been revoked"}), HTTP_OK


# -------------------------------------
# HTML-based session management routes
# Using login_required decorator for protecting routes
@auth_bp.route("/session-register", methods=["GET", "POST"])
def session_register():
    """Register a new user via HTML form."""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        role = request.form["role"]
        password = request.form["password"]
        confirmed_password = request.form["confirm_password"]
        if password != confirmed_password:
            flash("Passwords do not match", "danger")
            return render_template("register.html")

        json_data = {
            "username": username,
            "email": email,
            "role": role,
            "password": password,
        }

        # temporary trick: attach json_data to g
        g._json_data = json_data
        response = register_user()
        # remove the temp data
        del g._json_data

        data, status_code = response
        if status_code != HTTP_CREATED:
            flash("Invalid username or password", "danger")
            return render_template("register.html")
        flash("Registration successful! Please log in.", "success")
        return redirect("/auth/login-ui")
    return render_template("/auth/register.html")


@auth_bp.post("/session-login")
def session_login():
    """Login user via HTML form and create session."""
    username = request.form.get("username")
    password = request.form.get("password")

    json_data = {"username": username, "password": password}

    # --- Call your existing login_user() directly ---
    # We need to simulate Flask's request context expecting JSON
    # So instead of request.get_json(), we'll modify login_user() slightly

    # temporary trick: attach json_data to g
    g._json_data = json_data

    # now call login_user() internally
    response = login_user()

    # remove the temp data
    del g._json_data

    data, status_code = response
    if status_code != HTTP_OK:
        flash("Invalid username or password", "danger")
        return redirect("/auth/login-ui")

    tokens = data.get_json().get("tokens", {})
    session["access_token"] = tokens.get("access_token")
    session["refresh_token"] = tokens.get("refresh_token")

    flash("Login successful!", "success")
    return redirect("/")


@auth_bp.get("/login-ui")
def show_login_form():
    """Render the login HTML form."""
    return render_template("auth/login.html")


@auth_bp.get("/logout-ui")
def session_logout():
    """Logout user and clear session."""
    session.pop("access_token", None)
    session.pop("refresh_token", None)
    flash("Logged out successfully", "info")
    return redirect("/auth/login-ui")


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        token = session.get("access_token")
        if not token:
            flash("Please log in first.", "warning")
            return redirect("/auth/login-ui")
        try:
            decode_token(token)
        except (jwt_inner.ExpiredSignatureError, jwt_inner.InvalidTokenError):
            flash("Session expired. Please log in again.", "danger")
            session.pop("access_token", None)
            return redirect("/auth/login-ui")
        return view_func(*args, **kwargs)

    return wrapped


def get_current_username():
    """Retrieve the current logged-in user based on session token."""
    token = session.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        user = User.query.get(user_id)
        if payload.get("is_admin") != "admin":
            user.role = "user"
        else:
            user.role = "admin"
    except (jwt_inner.ExpiredSignatureError, jwt_inner.InvalidTokenError):
        return None
    return user if user else None


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        token = session.get("access_token")
        if not token:
            flash("Please log in first.", "warning")
            return redirect("/auth/login-ui")
        try:
            payload = decode_token(token)
            if payload.get("is_admin") != "admin":
                flash("Admin Only.", "warning")
                return redirect("/auth/login-ui")
        except (jwt_inner.ExpiredSignatureError, jwt_inner.InvalidTokenError):
            flash("Session expired. Please log in again.", "danger")
            session.pop("access_token", None)
            return redirect("/auth/login-ui")
        return view_func(*args, **kwargs)

    return wrapped
