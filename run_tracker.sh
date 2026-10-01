#!/bin/bash
# NFL Line Tracker — Automated Local Runner
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-/Library/Developer/CommandLineTools/usr/bin/python3}"
LOG_FILE="$SCRIPT_DIR/data/cron.log"

/usr/bin/caffeinate -u -t 240 /bin/bash << EOF
cd "$SCRIPT_DIR"
("$PYTHON" scrape_nfl_lines.py || true) >> "$LOG_FILE" 2>&1
"$PYTHON" plot_nfl_lines.py >> "$LOG_FILE" 2>&1
git add data/ charts/ >> "$LOG_FILE" 2>&1
(git diff --cached --quiet || git commit -m "auto: local cron sync [skip ci]") >> "$LOG_FILE" 2>&1
git pull --rebase -X ours origin main >> "$LOG_FILE" 2>&1
git push origin main >> "$LOG_FILE" 2>&1
EOF
