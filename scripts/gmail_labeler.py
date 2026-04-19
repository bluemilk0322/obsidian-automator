#!/usr/bin/env python3
"""Apply Gmail labels based on Claude's email classification output.

Usage:
    python gmail_labeler.py

Input: /tmp/email-labels.json (written by Claude Code CLI)
"""

import os
import sys
import json
from pathlib import Path

from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from google_auth import get_credentials

INPUT_PATH = "/tmp/email-labels.json"

# Labels to auto-create if they don't exist
AUTO_LABELS = ["auto/重要", "auto/參考", "auto/通知"]


def ensure_labels_exist(service, labels: list[str]) -> dict[str, str]:
    """Create labels if they don't exist. Returns {label_name: label_id}."""
    existing = service.users().labels().list(userId="me").execute()
    existing_map = {l["name"]: l["id"] for l in existing.get("labels", [])}

    label_ids = {}
    for label_name in labels:
        if label_name in existing_map:
            label_ids[label_name] = existing_map[label_name]
        else:
            try:
                created = service.users().labels().create(
                    userId="me",
                    body={
                        "name": label_name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                ).execute()
                label_ids[label_name] = created["id"]
                print(f"Created label: {label_name}", file=sys.stderr)
            except Exception as e:
                print(f"WARNING: Failed to create label {label_name}: {e}", file=sys.stderr)

    return label_ids


def apply_labels(account_name: str, actions: list[dict]) -> None:
    """Apply label actions for one account."""
    try:
        creds = get_credentials(account_name)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"WARNING: {e}", file=sys.stderr)
        return

    service = build("gmail", "v1", credentials=creds)

    # Ensure all auto labels exist
    label_ids = ensure_labels_exist(service, AUTO_LABELS)

    for action in actions:
        msg_id = action["message_id"]
        add_label_names = action.get("add_labels", [])
        should_archive = action.get("archive", False)

        add_ids = []
        for name in add_label_names:
            if name in label_ids:
                add_ids.append(label_ids[name])

        remove_ids = []
        if should_archive:
            remove_ids.append("INBOX")

        if not add_ids and not remove_ids:
            continue

        try:
            body = {}
            if add_ids:
                body["addLabelIds"] = add_ids
            if remove_ids:
                body["removeLabelIds"] = remove_ids

            service.users().messages().modify(
                userId="me",
                id=msg_id,
                body=body,
            ).execute()
            print(f"Labeled {msg_id}: +{add_label_names} archive={should_archive}", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Failed to label {msg_id}: {e}", file=sys.stderr)


def main():
    if not Path(INPUT_PATH).exists():
        print(f"No label file found at {INPUT_PATH}, skipping.", file=sys.stderr)
        return

    try:
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"ERROR: Failed to read {INPUT_PATH}: {e}", file=sys.stderr)
        return

    actions = data.get("actions", [])
    if not actions:
        print("No label actions to apply.", file=sys.stderr)
        return

    # Group actions by account
    by_account: dict[str, list[dict]] = {}
    for action in actions:
        account = action.get("account", "personal")
        by_account.setdefault(account, []).append(action)

    for account_name, account_actions in by_account.items():
        print(f"Applying {len(account_actions)} labels for {account_name}...", file=sys.stderr)
        apply_labels(account_name, account_actions)

    print(f"Done. Applied labels for {len(actions)} emails.", file=sys.stderr)


if __name__ == "__main__":
    main()
