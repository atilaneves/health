"""mytanita.eu login: password in the system keyring, session cookies cached on disk.

    uv run python -m health.tanita.auth login    # once: email + password, verified by logging in
    uv run python -m health.tanita.auth status

The site is server-rendered (checked 2026-10-14): GET /en/user/login carries a hidden `token`;
POST /en/user/processlogin takes mail, password, token, login. There is no long-lived API token,
only a session cookie, so the password must be available whenever a saved session has expired.
The password only ever lives in the keyring; the session file holds the email and cookies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from getpass import getpass
from pathlib import Path

import keyring
import keyring.errors
import requests

from health.prompt import ask_email

BASE = "https://mytanita.eu"
LOGIN_PATH = "/en/user/login"
PROCESS_LOGIN_PATH = "/en/user/processlogin"
KEYRING_SERVICE = "health-tanita"
STATE_DIR = Path(os.environ.get("HEALTH_TANITA_STATE", "~/.local/share/health/tanita")).expanduser()
LOGIN_CMD = "uv run python -m health.tanita.auth login"
TIMEOUT_S = 30

_TOKEN_RE = re.compile(r'name="token"[^>]*\bvalue="([^"]+)"')


class TanitaAuthError(RuntimeError):
    """Can't get a logged-in session; the message says what the user must do."""


def session_file() -> Path:
    return STATE_DIR / "session.json"


def is_login_page(resp: requests.Response) -> bool:
    return PROCESS_LOGIN_PATH in resp.text and 'name="password"' in resp.text


def login_with(session: requests.Session, email: str, password: str) -> None:
    r = session.get(BASE + LOGIN_PATH, timeout=TIMEOUT_S)
    r.raise_for_status()
    m = _TOKEN_RE.search(r.text)
    if not m:
        raise TanitaAuthError(f"no login token on {BASE + LOGIN_PATH}; the site has changed")
    r = session.post(BASE + PROCESS_LOGIN_PATH, timeout=TIMEOUT_S,
                     data={"mail": email, "password": password, "token": m.group(1), "login": "Login"})
    r.raise_for_status()
    if is_login_page(r):
        raise TanitaAuthError("mytanita.eu rejected the login (wrong email/password?)")


def save_session(session: requests.Session, email: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.chmod(0o700)
    p = session_file()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"email": email, "cookies": requests.utils.dict_from_cookiejar(session.cookies)}))
    tmp.chmod(0o600)
    os.replace(tmp, p)


def _saved() -> dict | None:
    p = session_file()
    return json.loads(p.read_text()) if p.exists() else None


def get_session() -> requests.Session:
    """A session carrying the saved cookies. They may have expired: callers detect a login page
    and call relogin()."""
    saved = _saved()
    if not saved:
        raise TanitaAuthError(f"not logged in to Tanita. Run `{LOGIN_CMD}`.")
    s = requests.Session()
    s.cookies.update(saved["cookies"])
    return s


def _password(email: str) -> str | None:
    return keyring.get_password(KEYRING_SERVICE, email)


def relogin(session: requests.Session) -> None:
    """Log in again with the keyring password, then save the fresh cookies."""
    saved = _saved()
    if not saved:
        raise TanitaAuthError(f"not logged in to Tanita. Run `{LOGIN_CMD}`.")
    email = saved["email"]
    try:
        password = _password(email)
    except keyring.errors.KeyringError as e:
        raise TanitaAuthError(f"can't read the Tanita password from the keyring ({e}); is it unlocked?") from e
    if password is None:
        raise TanitaAuthError(f"no Tanita password in the keyring for {email}. Run `{LOGIN_CMD}`.")
    session.cookies.clear()
    login_with(session, email, password)
    save_session(session, email)


def login_interactive() -> None:
    """Prompt for email + password, verify by logging in, then store the password in the keyring."""
    email = ask_email("Tanita", (_saved() or {}).get("email"))
    password = getpass("Tanita password (stored in the system keyring): ")
    s = requests.Session()
    login_with(s, email, password)
    keyring.set_password(KEYRING_SERVICE, email, password)
    save_session(s, email)
    print("Logged in; password saved to the keyring, session cookies to", session_file())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="health.tanita.auth")
    p.add_argument("command", choices=["login", "status"])
    a = p.parse_args(argv)
    if a.command == "status":
        saved = _saved()
        email = saved["email"] if saved else None
        print(f"session file: {session_file() if saved else 'none'}")
        print(f"email: {email or '-'}")
        print(f"password in keyring: {bool(email and _password(email))}")
        return 0
    try:
        login_interactive()
    except TanitaAuthError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
