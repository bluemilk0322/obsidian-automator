#!/usr/bin/env python3
"""Fetch unread emails from Gmail accounts and output as JSON.

Usage:
    python gmail_fetcher.py                    # Fetch from all configured accounts
    python gmail_fetcher.py --auth personal    # Interactive OAuth (host only)

Output: /tmp/emails.json
"""

import os
import sys
import json
import base64
from datetime import datetime

from googleapiclient.discovery import build

# Allow running --auth directly from this file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from google_auth import get_credentials, interactive_auth


OUTPUT_PATH = "/tmp/emails.json"
LABELS_OUTPUT_PATH = "/tmp/gmail-labels.json"

# 授權失效（refresh token 過期／被撤銷）的帳號 → {account: 錯誤訊息}。
# 跟「今天真的沒有未讀信」分開記，entrypoint 與 daily note 才看得出差別；
# 2026-04-27 起 token 失效，daily note 連續半年顯示「（無）」都沒人發現，就是沒分開的後果。
AUTH_FAILED: dict[str, str] = {}
# 本程序結束碼：授權失效時用 3，entrypoint 據此印出重新授權的指令。
EXIT_AUTH_FAILED = 3

# Gmail system labels to exclude from "user labels" snapshot
SYSTEM_LABEL_NAMES = {
    "INBOX", "SPAM", "TRASH", "UNREAD", "STARRED",
    "IMPORTANT", "SENT", "DRAFT", "CHAT",
}

# Mode-dependent settings (resolved at runtime via FIRST_RUN env var)
DAILY_MAX_EMAILS = 50
DAILY_MAX_BODY = 500
DAILY_QUERY = "is:unread newer_than:1d"

FIRST_RUN_MAX_EMAILS = 500
FIRST_RUN_MAX_BODY = 200
FIRST_RUN_QUERY = "newer_than:14d"


def is_first_run() -> bool:
    """Return True if FIRST_RUN env var is set to '1'."""
    return os.environ.get("FIRST_RUN", "0") == "1"


def get_settings() -> tuple[int, int, str]:
    """Return (max_emails, max_body_chars, gmail_query) for current mode."""
    if is_first_run():
        return FIRST_RUN_MAX_EMAILS, FIRST_RUN_MAX_BODY, FIRST_RUN_QUERY
    return DAILY_MAX_EMAILS, DAILY_MAX_BODY, DAILY_QUERY


def get_email_body(payload: dict, max_chars: int) -> str:
    """Extract plain text body from Gmail message payload, truncated to max_chars."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        raw = payload["body"]["data"]
        return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")[:max_chars]

    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            raw = part["body"]["data"]
            return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")[:max_chars]
        # Check nested parts (multipart/alternative inside multipart/mixed)
        for sub in part.get("parts", []):
            if sub.get("mimeType") == "text/plain" and sub.get("body", {}).get("data"):
                raw = sub["body"]["data"]
                return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")[:max_chars]

    return ""


def get_header(headers: list, name: str) -> str:
    """Extract a specific header value from Gmail message headers."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def fetch_emails(account_name: str) -> list[dict]:
    """Fetch emails for one account using current mode's settings."""
    try:
        creds = get_credentials(account_name)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"WARNING: {e}", file=sys.stderr)
        AUTH_FAILED[account_name] = str(e)
        return []

    service = build("gmail", "v1", credentials=creds)
    max_emails, max_body, query = get_settings()

    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_emails,
        ).execute()
    except Exception as e:
        print(f"WARNING: Failed to list emails for {account_name}: {e}", file=sys.stderr)
        return []

    messages = results.get("messages", [])
    emails = []

    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="full",
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()

            headers = msg.get("payload", {}).get("headers", [])
            label_ids = msg.get("labelIds", [])

            # Determine Gmail category
            category = "primary"
            for lid in label_ids:
                if lid.startswith("CATEGORY_"):
                    category = lid.replace("CATEGORY_", "").lower()
                    break

            # In first-run mode keep the per-email JSON tiny — 338+ emails
            # otherwise blow Claude's context window. The snippet alone is
            # usually enough to classify; body/thread_id/to/labels are dropped.
            entry = {
                "id": msg["id"],
                "account": account_name,
                "from": get_header(headers, "From"),
                "subject": get_header(headers, "Subject"),
                "date": get_header(headers, "Date"),
                "snippet": msg.get("snippet", "")[: (150 if is_first_run() else 300)],
                "category": category,
                "is_unread": "UNREAD" in label_ids,
            }
            if not is_first_run():
                entry["thread_id"] = msg.get("threadId", "")
                entry["to"] = get_header(headers, "To")
                entry["body"] = get_email_body(msg.get("payload", {}), max_body)
                entry["labels"] = label_ids
            emails.append(entry)
        except Exception as e:
            print(f"WARNING: Failed to fetch message {msg_ref['id']}: {e}", file=sys.stderr)
            continue

    return emails


def fetch_labels(account_name: str) -> list[str]:
    """Fetch user-defined Gmail labels for one account.

    Returns the sorted list of label names visible to the user,
    excluding Gmail system labels (INBOX, SPAM, CATEGORY_*, etc.).
    """
    try:
        creds = get_credentials(account_name)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"WARNING: {e}", file=sys.stderr)
        AUTH_FAILED.setdefault(account_name, str(e))
        return []

    service = build("gmail", "v1", credentials=creds)

    try:
        result = service.users().labels().list(userId="me").execute()
    except Exception as e:
        print(f"WARNING: Failed to list labels for {account_name}: {e}", file=sys.stderr)
        return []

    names = []
    for label in result.get("labels", []):
        name = label.get("name", "")
        if not name or name in SYSTEM_LABEL_NAMES or name.startswith("CATEGORY_"):
            continue
        names.append(name)

    return sorted(names)


def main():
    # Handle --auth mode
    if len(sys.argv) == 3 and sys.argv[1] == "--auth":
        interactive_auth(sys.argv[2])
        return

    personal = os.environ.get("PERSONAL_GMAIL", "")
    workspace = os.environ.get("WORKSPACE_GMAIL", "")

    all_emails = []
    errors = []

    if personal:
        print(f"Fetching emails for personal ({personal})...", file=sys.stderr)
        result = fetch_emails("personal")
        all_emails.extend(result)
        if not result:
            errors.append(f"No emails fetched for personal ({personal})")

    if workspace:
        print(f"Fetching emails for workspace ({workspace})...", file=sys.stderr)
        result = fetch_emails("workspace")
        all_emails.extend(result)
        if not result:
            errors.append(f"No emails fetched for workspace ({workspace})")

    max_emails, max_body, query = get_settings()
    output = {
        "fetched_at": datetime.now().isoformat(),
        "mode": "first_run" if is_first_run() else "daily",
        "query": query,
        "max_per_account": max_emails,
        "total": len(all_emails),
        "emails": all_emails,
        "errors": errors,
        # 帳號代號 → 信箱，daily note 的授權失效警告要寫出是哪個信箱
        "accounts": {k: v for k, v in (("personal", personal), ("workspace", workspace)) if v},
        # 授權失效的帳號；空物件＝授權正常（零封信就是真的零封）
        "auth_failed": AUTH_FAILED,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(all_emails)} emails to {OUTPUT_PATH} (mode={output['mode']})", file=sys.stderr)

    # Snapshot user's existing Gmail labels per account so Claude can classify
    # using the user's own taxonomy (instead of a fixed auto/* set).
    accounts_labels: dict[str, list[str]] = {}
    if personal:
        accounts_labels["personal"] = fetch_labels("personal")
    if workspace:
        accounts_labels["workspace"] = fetch_labels("workspace")

    labels_output = {
        "fetched_at": datetime.now().isoformat(),
        "accounts": accounts_labels,
    }
    with open(LABELS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(labels_output, f, ensure_ascii=False, indent=2)

    total_labels = sum(len(v) for v in accounts_labels.values())
    print(f"Wrote {total_labels} labels to {LABELS_OUTPUT_PATH}", file=sys.stderr)

    # 兩個 JSON 都寫完才回報授權失效，讓後面的步驟仍有檔可讀
    if AUTH_FAILED:
        for account, msg in AUTH_FAILED.items():
            print(f"AUTH FAILURE [{account}]: {msg}", file=sys.stderr)
        sys.exit(EXIT_AUTH_FAILED)


if __name__ == "__main__":
    main()
