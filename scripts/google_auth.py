#!/usr/bin/env python3
"""Shared Google OAuth2 authentication helper.

Usage:
    from google_auth import get_credentials

    creds = get_credentials("personal", scopes=[...])
    service = build("gmail", "v1", credentials=creds)

First-time auth (run on host, not in Docker):
    python google_auth.py --auth personal
    python google_auth.py --auth workspace
"""

import os
import sys
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

CREDENTIALS_DIR = Path(os.environ.get("CREDENTIALS_DIR", "/credentials"))
CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_token_path(account_name: str) -> Path:
    """Return the token file path for a given account name."""
    return CREDENTIALS_DIR / f"token_{account_name}.json"


def get_credentials(account_name: str) -> Credentials:
    """Load or refresh OAuth2 credentials for the given account.

    Args:
        account_name: "personal" or "workspace"

    Returns:
        Valid Google OAuth2 Credentials object.

    Raises:
        FileNotFoundError: If token file doesn't exist (run --auth first).
        RuntimeError: If token refresh fails.
    """
    token_path = get_token_path(account_name)

    if not token_path.exists():
        raise FileNotFoundError(
            f"No token found for '{account_name}'. "
            f"Run: python google_auth.py --auth {account_name}"
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        except Exception as e:
            raise RuntimeError(
                f"Token refresh failed for '{account_name}': {e}. "
                f"Re-run: python google_auth.py --auth {account_name}"
            )

    return creds


def interactive_auth(account_name: str) -> None:
    """Run interactive OAuth2 consent flow (requires browser).

    Must be run on host machine, not inside Docker.
    """
    if not CLIENT_SECRETS_FILE.exists():
        print(f"ERROR: {CLIENT_SECRETS_FILE} not found.")
        print("Download it from Google Cloud Console → APIs & Services → Credentials")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS_FILE), SCOPES
    )
    creds = flow.run_local_server(port=0)

    token_path = get_token_path(account_name)
    token_path.write_text(creds.to_json())
    print(f"Token saved to {token_path}")
    print(f"Account '{account_name}' authenticated successfully.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--auth":
        account_name = sys.argv[2]
        if account_name not in ("personal", "workspace"):
            print("Usage: python google_auth.py --auth <personal|workspace>")
            sys.exit(1)
        interactive_auth(account_name)
    else:
        print("Usage: python google_auth.py --auth <personal|workspace>")
        sys.exit(1)
