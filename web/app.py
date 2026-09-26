"""Same-origin dashboard API. Run with gunicorn 'web.app:create_app()'."""

import logging
import math
import os
import re
import time
from collections import OrderedDict, deque
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.exceptions import HTTPException

from utils.itad import search_game
from web.auth import AuthError, public_config, verify_token
from web.repository import Repository


class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return DefaultJSONProvider.default(value)


def target_value(body):
    value = body.get("target_price")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Enter a valid price.")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError("Enter a valid price.") from None
    if not math.isfinite(value) or not 0 <= value <= 1000000:
        raise ValueError("Price must be between ₹0 and ₹1,000,000.")
    return round(value, 2)


def create_app(repository=None, verifier=None):
    load_dotenv()
    app = Flask(__name__, static_folder=None)
    app.json = JSONProvider(app)
    app.config["MAX_CONTENT_LENGTH"] = 8192
    repo = repository or Repository()
    verify = verifier or verify_token
    static = Path(__file__).parent / "static"
    rate_lock, buckets = Lock(), OrderedDict()

    def body():
        value = request.get_json()
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object.")
        return value

    def game_id(value):
        try:
            return str(UUID(value))
        except ValueError:
            raise ValueError("Invalid game ID.") from None

    def signer():
        secret = os.environ.get("WEB_SECRET_KEY", "")
        if len(secret) < 32:
            raise AuthError("Game search is not configured yet.", 503)
        return URLSafeTimedSerializer(secret, salt="game-selection-v1")

    @app.before_request
    def authenticate():
        if not request.path.startswith("/api/") or request.path == "/api/config":
            return
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or not header[7:].strip():
            raise AuthError("Please sign in.")
        user = verify(header[7:])
        g.auth_user = user
        now = time.monotonic()
        with rate_lock:
            key = user["id"]
            bucket = buckets.pop(key, deque())
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            limited = len(bucket) >= 120
            if not limited:
                bucket.append(now)
            buckets[key] = bucket
            while len(buckets) > 2000:
                buckets.popitem(last=False)
        if limited:
            return jsonify(error="Too many requests. Try again in a minute."), 429
        account = repo.account(user["id"])
        if not account:
            raise AuthError("Your account is awaiting owner approval.", 403)
        g.user_id = account["discord_id"]

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Auth requests are made only to Supabase HTTPS endpoints; no third-party scripts.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self' https://*.supabase.co; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'"
        )
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, AuthError):
            return jsonify(error=str(exc)), exc.status
        if isinstance(exc, PermissionError):
            return jsonify(error=str(exc)), 403
        if isinstance(exc, ValueError):
            return jsonify(error=str(exc)), 400
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.name), exc.code
        logging.getLogger("drophunter.web").error("Request failed (%s)", type(exc).__name__)
        return jsonify(error="Service temporarily unavailable. Please retry."), 503

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.get("/api/config")
    def config():
        return jsonify(public_config())

    @app.get("/api/me")
    def me():
        return jsonify(email=g.auth_user.get("email"), auth_id=g.auth_user["id"])

    @app.get("/api/summary")
    def summary():
        return jsonify(repo.summary(g.user_id))

    @app.get("/api/games")
    def games():
        page, limit = int(request.args.get("page", 1)), int(request.args.get("limit", 10))
        sort, status = request.args.get("sort", "name"), request.args.get("status", "all")
        query = request.args.get("q", "").strip()
        if not 1 <= page <= 10000 or not 1 <= limit <= 50 or len(query) > 150:
            raise ValueError("Invalid pagination or search.")
        if sort not in ("name", "price", "gap") or status not in (
            "all",
            "deal",
            "watching",
            "unknown",
        ):
            raise ValueError("Invalid filter or sort.")
        return jsonify(repo.list_games(g.user_id, query, status, sort, page, limit))

    @app.get("/api/games/<value>/history")
    def history(value):
        ident = game_id(value)
        days = int(request.args.get("days", 30))
        if days not in (7, 30, 90):
            raise ValueError("Choose 7, 30, or 90 days.")
        game = repo.game(g.user_id, ident)
        if not game:
            return jsonify(error="Game not found."), 404
        return jsonify(game=game, points=repo.history(g.user_id, ident, days))

    @app.patch("/api/games/<value>")
    def update(value):
        data = body()
        if "target_price" not in data:
            raise ValueError("A target price is required; use null for historical-low alerts.")
        target = target_value(data)
        if not repo.update_game(g.user_id, game_id(value), target):
            return jsonify(error="Game not found."), 404
        return jsonify(ok=True)

    @app.delete("/api/games/<value>")
    def remove(value):
        if not repo.remove_game(g.user_id, game_id(value)):
            return jsonify(error="Game not found."), 404
        return jsonify(ok=True)

    @app.post("/api/search")
    def search():
        title = body().get("title", "")
        if not isinstance(title, str) or not 2 <= len(title.strip()) <= 150:
            raise ValueError("Enter a game title between 2 and 150 characters.")
        serializer = signer()
        match = search_game.__wrapped__(title.strip())  # One bounded lookup for web requests.
        if not match:
            return jsonify(error="No matching PC game found."), 404
        token = serializer.dumps(
            {"user": g.auth_user["id"], "id": match["id"], "title": match["title"]}
        )
        return jsonify(title=match["title"], selection=token)

    @app.post("/api/games")
    def add():
        data = body()
        target = target_value(data)
        try:
            match = signer().loads(data.get("selection", ""), max_age=600)
        except BadSignature:
            raise ValueError("Search for the game again; this selection has expired.") from None
        if match["user"] != g.auth_user["id"]:
            raise AuthError("This game selection belongs to a different account.", 403)
        return jsonify(repo.add_game(g.user_id, match["title"], match["id"], target)), 201

    @app.get("/api/watches")
    def watches():
        return jsonify(items=repo.watches(g.user_id))

    @app.get("/api/activity")
    def activity():
        return jsonify(items=repo.activity(g.user_id))

    @app.get("/api/settings")
    def settings():
        return jsonify(repo.settings(g.user_id))

    @app.patch("/api/settings")
    def save_settings():
        email = body().get("email")
        if email is not None:
            if not isinstance(email, str):
                raise ValueError("Enter a valid email address.")
            email = email.strip()
            if len(email) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
                raise ValueError("Enter a valid email address.")
        repo.set_email(g.user_id, email)
        return jsonify(ok=True)

    @app.get("/")
    def index():
        return send_from_directory(static, "index.html")

    @app.get("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(static / "assets", filename)

    return app
