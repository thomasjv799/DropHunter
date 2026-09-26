"""Verify tokens with the configured Supabase authority, never JWT payload decoding."""

import os
from uuid import UUID

import requests


class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


def public_config():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    # Deliberately do not fall back to SUPABASE_KEY (may be a service-role key).
    if not url.startswith("https://") or not key.startswith("sb_publishable_"):
        raise AuthError("Google sign-in is not configured yet.", 503)
    return {"url": url, "key": key}


def verify_token(token):
    config = public_config()
    try:
        response = requests.get(
            config["url"] + "/auth/v1/user",
            headers={"apikey": config["key"], "Authorization": "Bearer " + token},
            timeout=(5, 10),
        )
        if response.status_code in (401, 403):
            raise AuthError("Your session expired. Please sign in again.")
        if response.status_code != 200:
            raise AuthError("Sign-in service is temporarily unavailable.", 503)
        user = response.json()
        UUID(user["id"])
        if not user.get("email_confirmed_at") or not any(
            identity.get("provider") == "google" for identity in user.get("identities", [])
        ):
            raise AuthError("A verified Google account is required.", 403)
        return user
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise AuthError("Sign-in service is temporarily unavailable.", 503) from exc
