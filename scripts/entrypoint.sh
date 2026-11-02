#!/usr/bin/env bash
# Obsidian Automator — Daily entrypoint
# Runs all fetchers, then Claude Code CLI, then Gmail labeler.

set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
# cron 不帶 TZ，/app/.env 要到下面才 source；先定 TZ，否則 05:00 跑的 DATE 會算成 UTC 的前一天
export TZ="${TZ:-Asia/Taipei}"
DATE=$(date +%Y-%m-%d)
LOG="/tmp/automator-${DATE}.log"
CREDENTIALS_DIR="${CREDENTIALS_DIR:-/credentials}"
INITIALIZED_MARKER="${CREDENTIALS_DIR}/.initialized"

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"
}

log "=== Obsidian Automator starting ==="

# Load environment variables
if [ -f /app/.env ]; then
    set -a
    source /app/.env
    set +a
fi

# Detect first-run vs daily mode
if [ -f "$INITIALIZED_MARKER" ]; then
    export FIRST_RUN=0
    EMAIL_RANGE_DAYS=1
    log "Mode: daily (marker exists at $INITIALIZED_MARKER)"
else
    export FIRST_RUN=1
    EMAIL_RANGE_DAYS=14
    log "Mode: FIRST-RUN (no marker at $INITIALIZED_MARKER, running 14-day catch-up)"
fi

# Publish run mode for Claude Code CLI to read
cat > /tmp/run-mode.json <<EOF
{
  "first_run": $( [ "$FIRST_RUN" = "1" ] && echo true || echo false ),
  "email_range_days": $EMAIL_RANGE_DAYS,
  "date": "$DATE"
}
EOF

# Track per-step success so we know whether to write .initialized at the end
PIPELINE_OK=1

# 重新授權 Google 的指令（fetcher 結束碼 3 ＝ refresh token 過期或被撤銷）
REAUTH_CMD='cd ~/Code/obsidian/obsidian-automator && docker compose run --rm -p 8765:8765 -e OAUTH_PORT=8765 -e OAUTH_BIND=0.0.0.0 -e OAUTH_OPEN_BROWSER=0 automator python3 /app/scripts/google_auth.py --auth personal'

# Step 1: Fetch emails
log "Step 1: Fetching emails..."
python3 "${SCRIPTS_DIR}/gmail_fetcher.py" 2>>"$LOG"
RC=$?
if [ "$RC" -eq 0 ]; then
    log "  ✓ Emails fetched"
elif [ "$RC" -eq 3 ]; then
    log "  ✗ Gmail 授權失效：refresh token 過期或被撤銷，信件、標籤、自動歸檔全部停擺"
    log "    重新授權（在桌機 WSL 跑）：$REAUTH_CMD"
    PIPELINE_OK=0
else
    log "  ✗ Email fetch failed (continuing without email data)"
    echo '{"fetched_at":"","total":0,"emails":[],"errors":["fetch failed"],"accounts":{},"auth_failed":{}}' > /tmp/emails.json
    PIPELINE_OK=0
fi

# Step 2: Fetch calendar (not critical for first-run marker — just a daily concern)
log "Step 2: Fetching calendar..."
python3 "${SCRIPTS_DIR}/calendar_fetcher.py" 2>>"$LOG"
RC=$?
if [ "$RC" -eq 0 ]; then
    log "  ✓ Calendar fetched"
elif [ "$RC" -eq 3 ]; then
    log "  ✗ 行事曆授權失效（跟 Gmail 同一把 token），重新授權後一起恢復"
else
    log "  ✗ Calendar fetch failed (continuing without calendar data)"
    echo '{"fetched_at":"","date":"","total":0,"events":[],"errors":["fetch failed"],"auth_failed":{}}' > /tmp/calendar.json
fi

# Step 3: Fetch weather (not critical for first-run marker — just a daily concern)
log "Step 3: Fetching weather..."
if bash "${SCRIPTS_DIR}/weather.sh" 2>>"$LOG"; then
    log "  ✓ Weather fetched"
else
    log "  ✗ Weather fetch failed (continuing without weather data)"
    echo '{"error":"fetch failed"}' > /tmp/weather.json
fi

# Step 4: Run Claude Code CLI
log "Step 4: Running Claude Code CLI..."
PROMPT=$(cat "${SCRIPTS_DIR}/prompts/daily.md")

run_claude() {
    # First-run needs many more turns: classifying up to 1000 emails plus
    # writing Daily + AI-Digest + email-labels.json easily exceeds the
    # daily-mode budget.
    if [ "${FIRST_RUN:-0}" = "1" ]; then
        MAX_TURNS=80
    else
        MAX_TURNS=20
    fi
    claude --print "$PROMPT" \
        --allowedTools "Read,Write,Edit,WebFetch,Bash" \
        --model claude-sonnet-4-6 \
        --max-turns "$MAX_TURNS" \
        2>>"$LOG"
}

if run_claude; then
    log "  ✓ Claude Code completed"
else
    log "  ✗ Claude Code failed, retrying in 60s..."
    sleep 60
    if run_claude; then
        log "  ✓ Claude Code completed (retry)"
    else
        log "  ✗ Claude Code failed on retry. Aborting."
        exit 1
    fi
fi

# Step 5: Apply Gmail labels
log "Step 5: Applying Gmail labels..."
if python3 "${SCRIPTS_DIR}/gmail_labeler.py" 2>>"$LOG"; then
    log "  ✓ Labels applied"
else
    log "  ✗ Label application failed (daily notes are still generated)"
    PIPELINE_OK=0
fi

# Step 6: Write first-run marker if this was a first-run and everything succeeded
if [ "$FIRST_RUN" = "1" ] && [ "$PIPELINE_OK" = "1" ]; then
    printf '{"initialized_at":"%s"}\n' "$(date -Iseconds)" > "$INITIALIZED_MARKER"
    log "  ✓ First-run complete; wrote marker to $INITIALIZED_MARKER"
elif [ "$FIRST_RUN" = "1" ]; then
    log "  ⚠ First-run had failures; marker NOT written (next run will retry first-run mode)"
fi

log "=== Obsidian Automator finished ==="
log "Generated files:"
log "  - /vault/AI-Digest/${DATE}.md"
log "  - /vault/Daily/${DATE}.md"
