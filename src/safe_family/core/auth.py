"""Authentication routes and session management for Safe Family application."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import wraps
from urllib.parse import urlencode

import jwt as jwt_inner
import requests
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
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
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from itsdangerous import BadData, URLSafeTimedSerializer

from config.settings import settings
from src.safe_family.core.extensions import db
from src.safe_family.core.models import AuthCode, TokenBlocklist, User
from src.safe_family.utils.constants import HTTP_CREATED, HTTP_OK, SCOPES

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)
OAUTH_STATE_TTL_SECONDS = 600


def require_api_key(view_func):
    """Require a valid API key for notesync endpoints."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        expected = settings.NOTESYNC_API_KEY
        if not expected or api_key != expected:
            return jsonify({"error": "unauthorized"}), 401
        return view_func(*args, **kwargs)

    return wrapped


def _hash_auth_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _naive_utc_now() -> datetime:
    return datetime.utcnow()


def create_auth_code(user_id: str) -> str:
    """Create and persist a short-lived auth code for the user."""
    raw_code = secrets.token_urlsafe(32)
    code_hash = _hash_auth_code(raw_code)
    expires_at = _naive_utc_now() + timedelta(
        seconds=settings.NOTESYNC_AUTH_CODE_TTL_SECONDS,
    )
    auth_code = AuthCode(
        code_hash=code_hash,
        user_id=user_id,
        expires_at=expires_at,
    )
    db.session.add(auth_code)
    db.session.commit()
    return raw_code


def consume_auth_code(raw_code: str) -> AuthCode | None:
    """Validate and mark an auth code as used."""
    code_hash = _hash_auth_code(raw_code)
    auth_code = AuthCode.query.filter_by(code_hash=code_hash).one_or_none()
    if auth_code is None:
        return None
    if auth_code.used_at is not None or auth_code.is_expired():
        return None
    auth_code.used_at = _naive_utc_now()
    db.session.commit()
    return auth_code


def build_notesync_callback_url(code: str) -> str:
    """Return the universal link used by the iOS app to capture auth codes."""
    base = settings.NOTESYNC_CALLBACK_URL
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}code={code}"


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
    ), HTTP_OK


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
    session.pop("state", None)
    flash("Logged out successfully", "info")
    return redirect("/auth/login-ui")


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        token = session.get("access_token")
        if not token:
            logger.warning(
                "login_required: missing token path=%s method=%s ua=%s",
                request.path,
                request.method,
                request.headers.get("User-Agent", "-"),
            )
            flash("Please log in first.", "warning")
            return redirect("/auth/login-ui")
        try:
            decode_token(token)
        except (jwt_inner.ExpiredSignatureError, jwt_inner.InvalidTokenError):
            logger.warning(
                "login_required: expired/invalid token path=%s method=%s ua=%s",
                request.path,
                request.method,
                request.headers.get("User-Agent", "-"),
            )
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


google_client_secrets = {
    "web": {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "project_id": settings.GOOGLE_CLIENT_PROJECT_ID,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uris": [
            f"https://zzuse.duckdns.org/{settings.GOOGLE_CALLBACK_ROUTE}",
            f"http://127.0.0.1:5000/{settings.GOOGLE_CALLBACK_ROUTE}",
        ],
        "javascript_origins": ["https://zzuse.duckdns.org", "http://127.0.0.1:5000"],
    },
}


def _oauth_create_client(name: str):
    if name == "google":
        if not (
            settings.GOOGLE_CLIENT_ID
            and settings.GOOGLE_CLIENT_SECRET
            and settings.GOOGLE_CLIENT_PROJECT_ID
        ):
            return None
        return {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
        }
    if name == "github":
        if not (settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET):
            return None
        return {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
        }
    return None


def _oauth_provider_available(name: str) -> bool:
    client = _oauth_create_client(name)
    return bool(
        client,
    )


def _oauth_state_serializer() -> URLSafeTimedSerializer:
    secret = current_app.secret_key or settings.APP_SECRET_KEY or settings.JWT_SECRET_KEY
    if not secret:
        raise RuntimeError("Missing secret key for OAuth state signing.")
    return URLSafeTimedSerializer(secret, salt="notesync-oauth-state")


def _normalize_oauth_client(value: str | None) -> str:
    return "ios" if value == "ios" else "web"


def _build_oauth_state(client: str) -> str:
    normalized = _normalize_oauth_client(client)
    nonce = secrets.token_urlsafe(16)
    state = _oauth_state_serializer().dumps(
        {"client": normalized, "nonce": nonce},
    )
    session["oauth_state_nonce"] = nonce
    return state


def _read_oauth_state(state: str | None) -> dict | None:
    if not state:
        return None
    try:
        payload = _oauth_state_serializer().loads(
            state,
            max_age=OAUTH_STATE_TTL_SECONDS,
        )
    except BadData:
        return None
    expected_nonce = session.pop("oauth_state_nonce", None)
    if expected_nonce and payload.get("nonce") != expected_nonce:
        return None
    return payload


def _resolve_oauth_client(state_payload: dict | None) -> str:
    session_client = session.pop("oauth_client", None)
    if session_client:
        return _normalize_oauth_client(session_client)
    if state_payload:
        return _normalize_oauth_client(state_payload.get("client"))
    return "web"


@auth_bp.get("/login/github")
def login_github():
    client = (request.args.get("client") or "").strip().lower()
    if client == "ios":
        session["oauth_client"] = "ios"
    if not _oauth_provider_available("github"):
        flash("GitHub login is not configured.", "danger")
        return redirect("/auth/login-ui")
    redirect_uri = url_for("auth.github_callback", _external=True)
    state = _build_oauth_state(client)
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    authorization_url = "https://github.com/login/oauth/authorize?" + urlencode(params)
    return redirect(authorization_url)


@auth_bp.get("/login/google")
def login_google():
    client = (request.args.get("client") or "").strip().lower()
    if client == "ios":
        session["oauth_client"] = "ios"
    if not _oauth_provider_available("google"):
        flash("Google login is not configured.", "danger")
        return redirect("/auth/login-ui")
    flow = Flow.from_client_config(
        google_client_secrets,
        scopes=SCOPES,
        redirect_uri=url_for("auth.google_callback", _external=True),
    )
    state = _build_oauth_state(client)
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
    )
    return redirect(authorization_url)


@auth_bp.get("/oauth_start")
def oauth_start():
    """Redirect to the provider-specific OAuth login route."""
    provider = (request.args.get("provider") or "").strip().lower()
    client = (request.args.get("client") or "").strip().lower()
    client = "ios" if client == "ios" else ""
    if client == "ios":
        session["oauth_client"] = "ios"
    if not provider:
        return render_template(
            "auth/oauth_start.html",
            client=client,
        )
    if provider == "google":
        if client:
            return redirect(url_for("auth.login_google", client=client))
        return redirect(url_for("auth.login_google"))
    if provider == "github":
        if client:
            return redirect(url_for("auth.login_github", client=client))
        return redirect(url_for("auth.login_github"))
    return (
        render_template(
            "auth/oauth_start.html",
            client=client,
            error="Invalid provider. Choose Google or GitHub.",
        ),
        400,
    )


@auth_bp.get("/github/callback")
def github_callback():
    if not _oauth_provider_available("github"):
        flash("GitHub login is not configured.", "danger")
        return redirect("/auth/login-ui")
    error = request.args.get("error")
    if error:
        flash("GitHub login failed.", "danger")
        return redirect("/auth/login-ui")
    state = request.args.get("state")
    state_payload = _read_oauth_state(state)
    if not state_payload:
        flash("GitHub login state mismatch.", "danger")
        return redirect("/auth/login-ui")
    code = request.args.get("code")
    if not code:
        flash("GitHub login missing code.", "danger")
        return redirect("/auth/login-ui")

    token_response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": url_for("auth.github_callback", _external=True),
            "state": state,
        },
        timeout=10,
    )
    if token_response.status_code != HTTP_OK:
        flash("GitHub token exchange failed.", "danger")
        return redirect("/auth/login-ui")
    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        flash("GitHub token exchange failed.", "danger")
        return redirect("/auth/login-ui")

    api_headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    user_response = requests.get(
        "https://api.github.com/user",
        headers=api_headers,
        timeout=10,
    )
    if user_response.status_code != HTTP_OK:
        flash("GitHub user lookup failed.", "danger")
        return redirect("/auth/login-ui")
    user_info = user_response.json()
    emails_response = requests.get(
        "https://api.github.com/user/emails",
        headers=api_headers,
        timeout=10,
    )
    emails = []
    if emails_response.status_code == HTTP_OK:
        emails = emails_response.json()

    email = user_info.get("email")
    if not email and emails:
        primary_verified = [
            entry for entry in emails if entry.get("primary") and entry.get("verified")
        ]
        verified = [entry for entry in emails if entry.get("verified")]
        selection = (
            primary_verified[0]
            if primary_verified
            else verified[0]
            if verified
            else emails[0]
        )
        email = selection.get("email")
    if not email:
        login_name = user_info.get("login", "github_user")
        email = f"{login_name}@users.noreply.github.com"

    github_id = str(user_info.get("id"))
    name = user_info.get("name") or user_info.get("login") or email.split("@")[0]
    user = User.query.filter_by(id=github_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    if not user:
        new_user = User(
            id=github_id,
            username=name,
            email=email,
        )
        new_user.set_password(secrets.token_urlsafe(48))
        new_user.save()
        user = new_user

    logger.info("Logging in GitHub user: %s", name)
    client = _resolve_oauth_client(state_payload)
    if client == "ios":
        auth_code = create_auth_code(user.id)
        return redirect(build_notesync_callback_url(auth_code))

    session["access_token"] = create_access_token(identity=user.id)
    session["refresh_token"] = create_refresh_token(identity=user.id)
    flash("Login successful!", "success")
    return redirect("/")


@auth_bp.get("/google/callback")
def google_callback():
    state = request.args.get("state")
    state_payload = _read_oauth_state(state)
    if not state_payload:
        flash("Google login state mismatch.", "danger")
        return redirect("/auth/login-ui")
    flow = Flow.from_client_config(
        google_client_secrets,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for("auth.google_callback", _external=True),
    )
    # Fetch token
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as exc:  # pragma: no cover - defensive handling
        logger.warning("Google token exchange failed: %s", exc)
        flash("Google token exchange failed.", "danger")
        return redirect("/auth/login-ui")
    # Get credentials and verify
    credentials = flow.credentials
    id_info = id_token.verify_oauth2_token(
        credentials.id_token,
        google_requests.Request(),
        google_client_secrets["web"]["client_id"],
    )
    google_id = id_info["sub"]
    email = id_info["email"]
    name = id_info.get("name", "")
    user = User.query.filter_by(id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    if not user:
        new_user = User(
            id=google_id,
            username=name,
            email=email,
        )
        new_user.set_password(secrets.token_urlsafe(48))
        new_user.save()
        user = new_user

    logger.info("Logging in Google user: %s, state: %s", name, state)
    client = _resolve_oauth_client(state_payload)
    if client == "ios":
        auth_code = create_auth_code(user.id)
        return redirect(build_notesync_callback_url(auth_code))

    session["access_token"] = create_access_token(identity=user.id)
    session["refresh_token"] = create_refresh_token(identity=user.id)
    flash("Login successful!", "success")
    return redirect("/")


@auth_bp.get("/callback")
def notesync_callback():
    """Fallback page for notesync universal link callback."""
    code = request.args.get("code", "")
    if not code:
        return "Missing auth code. Return to the app and try again.", 400
    return (
        "Auth code received. You can return to the app to finish login. "
        f"If needed, copy this code: {code}",
        200,
    )
