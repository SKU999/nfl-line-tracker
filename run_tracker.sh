#!/bin/bash
# NFL Line Tracker — Automated Local Runner
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-/Library/Developer/CommandLineTools/usr/bin/python3}"
LOG_FILE="$SCRIPT_DIR/data/cron.log"
LOCK_DIR="/private/tmp/nfl-line-tracker.lock"
MPL_CACHE_DIR="/private/tmp/nfl-line-tracker-matplotlib"

# Avoid overlapping cron invocations. Recover automatically if a previous run
# was interrupted and left a stale lock behind.
if ! /bin/mkdir "$LOCK_DIR" 2>/dev/null; then
    if [[ -f "$LOCK_DIR/pid" ]] && /bin/kill -0 "$(/bin/cat "$LOCK_DIR/pid")" 2>/dev/null; then
        printf '[%s] Tracker already running; skipping overlapping invocation.\n' "$(/bin/date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
        exit 0
    fi
    /bin/rm -rf "$LOCK_DIR"
    /bin/mkdir "$LOCK_DIR"
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
trap '/bin/rm -rf "$LOCK_DIR"' EXIT INT TERM

# Keep Matplotlib from trying to write to ~/.matplotlib under cron.
/bin/mkdir -p "$MPL_CACHE_DIR"
export MPLCONFIGDIR="$MPL_CACHE_DIR"

/usr/bin/caffeinate -u -t 240 /bin/bash << EOF
cd "$SCRIPT_DIR"
("$PYTHON" scrape_nfl_lines.py || true) >> "$LOG_FILE" 2>&1
"$PYTHON" plot_nfl_lines.py >> "$LOG_FILE" 2>&1
git add data/ charts/ >> "$LOG_FILE" 2>&1
(git diff --cached --quiet || git commit -m "auto: local tracker sync") >> "$LOG_FILE" 2>&1
git pull --rebase -X ours origin main >> "$LOG_FILE" 2>&1
git push origin main >> "$LOG_FILE" 2>&1
EOF
