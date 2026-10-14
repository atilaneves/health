"""Garmin token management.

    uv run python -m health.garmin.auth login    # one-time interactive login (+MFA)
    uv run python -m health.garmin.auth status   # is a token saved / when does the access token expire

Verified against garminconnect 0.3.17:
- Garmin.login(tokenstore) first tries to load <tokenstore>/garmin_tokens.json; only if that
  fails AND email/password were given does it do a credential login (then dumps tokens, 0600 in 0700 dir).
- The file holds di_token (access JWT, short-lived, auto-refreshed before each request and
  re-saved) and di_refresh_token (opaque; its lifetime is not documented or decodable).
- get_client() passes NO credentials, so the library can never fall back to a password login.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import sys
import time
from getpass import getpass
from pathlib import Path

from health.prompt import ask_email

TOKEN_DIR = Path(
    os.environ.get("HEALTH_GARMIN_TOKENS", "~/.local/share/health/garmin_tokens")
).expanduser()
TOKEN_FILE_NAME = "garmin_tokens.json"  # fixed by garminconnect.client.token_file_path

LOGIN_CMD = "uv run python -m health.garmin.auth login"


class GarminAuthError(RuntimeError):
    """No usable saved tokens; the user must run the interactive login."""


def token_file() -> Path:
    return TOKEN_DIR / TOKEN_FILE_NAME


def _jwt_exp(token: str) -> float | None:
    try:
        part = token.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return float(payload["exp"])
    except Exception:
        return None


def token_status() -> dict:
    """Describe the saved token without any network access."""
    path = token_file()
    if not path.exists():
        return {"present": False, "path": str(path)}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {"present": False, "path": str(path), "error": "unreadable token file"}
    exp = _jwt_exp(data.get("di_token") or "")
    return {
        "present": bool(data.get("di_token")),
        "has_refresh_token": bool(data.get("di_refresh_token")),
        "access_token_expires": exp,  # epoch seconds; refreshed automatically on use
        "access_token_expired": (exp is not None and exp < time.time()),
        "mode": oct(stat.S_IMODE(path.stat().st_mode)),
        "path": str(path),
    }


def get_client():
    """Return a logged-in garminconnect.Garmin using ONLY saved tokens.

    Raises GarminAuthError if tokens are missing, or rejected (refresh token expired/revoked).
    Never uses a password. May do network I/O (token refresh + profile fetch).
    """
    if not token_file().exists():
        raise GarminAuthError(
            f"No Garmin tokens at {token_file()}. Run `{LOGIN_CMD}` first."
        )
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )

    client = Garmin()  # no credentials on purpose
    try:
        client.login(str(TOKEN_DIR))
    except GarminConnectTooManyRequestsError:
        raise  # not an auth problem; caller should back off, not re-login
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as e:
        raise GarminAuthError(
            f"Saved Garmin tokens unusable ({e}). Run `{LOGIN_CMD}` again."
        ) from e
    return client


def login_interactive() -> None:
    from garminconnect import Garmin

    TOKEN_DIR.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_DIR.mkdir(mode=0o700, exist_ok=True)
    TOKEN_DIR.chmod(0o700)
    email = ask_email("Garmin")
    password = getpass("Garmin password (not stored): ")
    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    try:
        client.login(str(TOKEN_DIR))  # saves tokens on success
    finally:
        del password
    token_file().chmod(0o600)
    print(f"Logged in. Tokens saved to {token_file()}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="health.garmin.auth")
    p.add_argument("command", choices=["login", "status"])
    args = p.parse_args(argv)
    if args.command == "login":
        if token_file().exists():
            print(
                f"Tokens already exist at {token_file()}. Repeated fresh logins cause HTTP 429;\n"
                "delete the file first if you really want to log in again."
            )
            return 1
        login_interactive()
        return 0
    st = token_status()
    for k, v in st.items():
        if k == "access_token_expires" and v:
            v = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v)) + " (auto-refreshed on use)"
        print(f"{k}: {v}")
    return 0 if st.get("present") else 1


if __name__ == "__main__":
    sys.exit(main())
