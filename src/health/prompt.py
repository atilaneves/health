"""Interactive prompts shared by the login commands."""

from __future__ import annotations

import os
import subprocess


def default_email() -> str | None:
    """$HEALTH_EMAIL, else `git config user.email`, else None."""
    if email := os.environ.get("HEALTH_EMAIL", "").strip():
        return email
    try:
        out = subprocess.run(["git", "config", "--get", "user.email"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def ask_email(service: str, default: str | None = None, input=input) -> str:
    """Prompt for an email; Enter accepts the default."""
    default = default or default_email()
    while True:
        answer = input(f"{service} email [{default}]: " if default else f"{service} email: ").strip()
        if answer or default:
            return answer or default
