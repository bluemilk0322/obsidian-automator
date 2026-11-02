#!/usr/bin/env python3
"""Fetch today's calendar events from Google Calendar and output as JSON.

Usage:
    python calendar_fetcher.py

Output: /tmp/calendar.json
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from google_auth import get_credentials

OUTPUT_PATH = "/tmp/calendar.json"
TIMEZONE = "Asia/Taipei"

# 授權失效的帳號 → 錯誤訊息（與 gmail_fetcher 同一套約定，結束碼 3）
AUTH_FAILED: dict[str, str] = {}
EXIT_AUTH_FAILED = 3


def fetch_events(account_name: str) -> list[dict]:
    """Fetch today's events for one account from all visible calendars."""
    try:
        creds = get_credentials(account_name)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"WARNING: {e}", file=sys.stderr)
        AUTH_FAILED[account_name] = str(e)
        return []

    service = build("calendar", "v3", credentials=creds)

    # Get start/end of today in UTC
    # Use timezone offset +8 for Asia/Taipei
    tz_offset = timezone(timedelta(hours=8))
    now = datetime.now(tz_offset)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    time_min = start_of_day.isoformat()
    time_max = end_of_day.isoformat()

    events = []

    try:
        # List all calendars the user can see
        calendar_list = service.calendarList().list().execute()
        calendars = calendar_list.get("items", [])

        for cal in calendars:
            cal_id = cal["id"]
            cal_summary = cal.get("summary", cal_id)

            try:
                events_result = service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                for event in events_result.get("items", []):
                    start = event.get("start", {})
                    end = event.get("end", {})

                    # Extract Google Meet link if present
                    meet_link = ""
                    conference = event.get("conferenceData", {})
                    for ep in conference.get("entryPoints", []):
                        if ep.get("entryPointType") == "video":
                            meet_link = ep.get("uri", "")
                            break

                    events.append({
                        "account": account_name,
                        "calendar": cal_summary,
                        "title": event.get("summary", "(無標題)"),
                        "start": start.get("dateTime", start.get("date", "")),
                        "end": end.get("dateTime", end.get("date", "")),
                        "location": event.get("location", ""),
                        "meet_link": meet_link,
                        "description": (event.get("description", "") or "")[:200],
                        "all_day": "date" in start and "dateTime" not in start,
                    })
            except Exception as e:
                print(f"WARNING: Failed to fetch events from {cal_summary}: {e}", file=sys.stderr)
                continue

    except Exception as e:
        print(f"WARNING: Failed to list calendars for {account_name}: {e}", file=sys.stderr)

    return events


def main():
    personal = os.environ.get("PERSONAL_GMAIL", "")
    workspace = os.environ.get("WORKSPACE_GMAIL", "")

    all_events = []
    errors = []

    for account_name, email in [("personal", personal), ("workspace", workspace)]:
        if email:
            print(f"Fetching calendar for {account_name} ({email})...", file=sys.stderr)
            result = fetch_events(account_name)
            all_events.extend(result)
            if account_name in AUTH_FAILED:
                errors.append(f"Auth failed for {account_name} ({email}): {AUTH_FAILED[account_name]}")

    # Sort all events by start time
    all_events.sort(key=lambda e: e.get("start", ""))

    output = {
        "fetched_at": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total": len(all_events),
        "events": all_events,
        "errors": errors,
        "auth_failed": AUTH_FAILED,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(all_events)} events to {OUTPUT_PATH}", file=sys.stderr)

    if AUTH_FAILED:
        for account, msg in AUTH_FAILED.items():
            print(f"AUTH FAILURE [{account}]: {msg}", file=sys.stderr)
        sys.exit(EXIT_AUTH_FAILED)


if __name__ == "__main__":
    main()
