#!/usr/bin/env bash
# Docker container entrypoint.
# Persists docker-compose env_file vars to /app/.env so cron-spawned shells
# can source them (cron does not inherit the container's initial env).

set -euo pipefail

ENV_OUT=/app/.env

# Snapshot only the vars the application cares about.
# PATH + HOME are critical: cron strips env, so without these the cron-spawned
# shell can't find /opt/venv/bin (Python deps) or /usr/local/bin (claude CLI),
# and claude can't locate ~/.claude/ for OAuth auth.
{
    for var in PERSONAL_GMAIL WORKSPACE_GMAIL TZ VAULT_PATH CREDENTIALS_DIR PATH HOME; do
        if [ -n "${!var:-}" ]; then
            printf '%s=%s\n' "$var" "${!var}"
        fi
    done
} > "$ENV_OUT"

chmod 0600 "$ENV_OUT"

exec cron -f
