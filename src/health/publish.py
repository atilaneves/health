"""Publish site/index.html to GitHub Pages, encrypted with a password (StatiCrypt), so it can be read
on a phone. The repo and the Pages site are public; only the encrypted page leaves this machine.

    uv run python -m health.publish set-password   # once: choose the page password (kept in the keyring)
    uv run python -m health.publish                # encrypt and push now (build.sh does this after building)

The page is AES-encrypted in the browser by StatiCrypt, keyed from the password and a fixed salt kept
next to the other local state. Keeping the salt fixed means "Remember me" on the phone survives
republishing. The gh-pages branch is force-pushed as a single commit, so no old copies pile up.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from getpass import getpass
from pathlib import Path

import keyring

from health.db import ROOT, SITE_DIR

STATICRYPT = "staticrypt@3.5.4"
KEYRING_SERVICE = "health-pages"
KEYRING_USER = "password"
SALT_FILE = Path(os.environ.get("HEALTH_PAGES_SALT", "~/.local/share/health/pages_salt")).expanduser()
BRANCH = "gh-pages"
SET_PASSWORD_CMD = "uv run python -m health.publish set-password"


class PublishError(RuntimeError):
    pass


def password() -> str | None:
    return keyring.get_password(KEYRING_SERVICE, KEYRING_USER)


def _salt() -> str:
    if not SALT_FILE.exists():
        SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
        SALT_FILE.write_text(secrets.token_hex(16))
    return SALT_FILE.read_text().strip()


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode:
        raise PublishError(f"{cmd[0]} {cmd[1]} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def publish() -> str:
    """Encrypt the built page and force-push it to the gh-pages branch. Returns the Pages URL."""
    pw = password()
    if not pw:
        raise PublishError(f"no page password set; run: {SET_PASSWORD_CMD}")
    page = SITE_DIR / "index.html"
    if not page.exists():
        raise PublishError(f"{page} doesn't exist; build it first")
    origin = _run(["git", "remote", "get-url", "origin"], ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # The password goes in through the environment, never on a command line.
        _run(["npx", "--yes", STATICRYPT, str(page), "-d", str(tmp / "out"), "-s", _salt(), "-c", "false",
              "--short", "--template-title", "Health", "--template-instructions", "Health charts"],
             tmp, env={**os.environ, "STATICRYPT_PASSWORD": pw})
        site = tmp / "site"
        site.mkdir()
        shutil.copy(tmp / "out" / "index.html", site / "index.html")
        (site / ".nojekyll").touch()
        _run(["git", "init", "-q", "-b", BRANCH], site)
        _run(["git", "add", "-A"], site)
        _run(["git", "commit", "-q", "-m", "Encrypted health page"], site)
        _run(["git", "push", "-q", "--force", origin, f"{BRANCH}:{BRANCH}"], site)
    owner, repo = origin.removesuffix(".git").split("/")[-2:]
    owner = owner.split(":")[-1]
    return f"https://{owner}.github.io/{repo}/"


def set_password() -> None:
    pw = getpass("Page password (long; it's all that protects the published page): ")
    if pw != getpass("Again: "):
        sys.exit("Passwords differ; nothing saved.")
    if len(pw) < 12:
        sys.exit("Use at least 12 characters; nothing saved.")
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, pw)
    print("Saved in the keyring.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m health.publish", description=__doc__.split("\n\n")[0])
    p.add_argument("command", nargs="?", choices=["set-password"])
    a = p.parse_args(argv)
    if a.command == "set-password":
        set_password()
        return 0
    try:
        print(f"published: {publish()}")
    except PublishError as e:
        sys.exit(str(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
