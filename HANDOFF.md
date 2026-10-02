# NFL Line Tracker — Technical Handoff Document

**Generated:** 2026-09-30 22:30 CT  
**Working Directory:** `/Users/sg/.gemini/antigravity/scratch/nfl-line-tracker`  
**GitHub Repository:** [github.com/SKU999/nfl-line-tracker](https://github.com/SKU999/nfl-line-tracker) (`main` branch)  
**Live Site / Dashboard:** [https://sku999.github.io/nfl-line-tracker/](https://sku999.github.io/nfl-line-tracker/)

---

## 1. Project Purpose & Scope

The **NFL Line Tracker** is an automated pipeline and web dashboard monitoring DraftKings lines (with Pinnacle cross-reference) for all 16 weekly NFL games.
It captures:
- DraftKings spread and total lines (pinned to DK main lines with balanced juice).
- Consensus spread and total.
- Pinnacle spread and total.
- Calculated Implied Team Totals for Home and Away teams.
- Weekly opening/baseline values for each game.
- Historical movement charts and a summary table rendered to GitHub Pages.
- Staleness detection (live counting in client browser; triggers after 4.0 hours Mon–Sat, or after 1.5 hours on Sunday).

---

## 2. Architecture & File Inventory

| Path | Purpose | Key Details |
|---|---|---|
| `scrape_nfl_lines.py` | Odds scraper | Uses `curl_cffi` impersonating `chrome124`. Scrapes `4codds.com/api/v2/board/football` and `/game/{gid}/market/{sp\|tot}`. Writes `data/nfl_lines.jsonl` and `data/scraper_status.json`. |
| `plot_nfl_lines.py` | Dashboard & chart builder | Processes `data/nfl_lines.jsonl` and `data/scraper_status.json`. Generates PNG charts in `charts/` and `charts/index.html`. Employs oldest-game timestamping for staleness. |
| `run_tracker.sh` | Local execution script | Runs scraper, plotter, and git commit/push under macOS `caffeinate -u -t 240`. |
| `setup_cron.py` | Local cron configurer | Generates and installs crontab invoking `run_tracker.sh`. |
| `.github/workflows/nfl_tracker.yml` | GitHub Pages workflow | Deploys the checked-in `charts/` directory after a local runner push. It does not scrape from GitHub-hosted runners. |
| `data/nfl_lines.jsonl` | Database | Rolling JSONL log of market snapshots per game. |
| `data/scraper_status.json` | Health status file | Contains the run timestamp, success flag, total/valid/closed game counts, error details, and invalid pregame matchup names. Written purely by code. |
| `charts/index.html` | Front-end dashboard | Responsive single-page board with slate filters, expandable per-game charts, mobile game cards, and a dynamic JS staleness banner. Every valid completed pull is shown as a chart dot. |

---

## 3. Critical Findings & Solved Pitfalls

### A. The Cron Execution Failure (BSD Cron 1,000-Char Limit)
- **Symptom:** Between 11:11 AM and 10:17 PM, scheduled cron jobs failed to update `charts/index.html`, making the live page report stale.
- **Root Cause:** macOS uses BSD `cron`. The previous crontab command was a 1,051-character one-liner with chained commands (`git diff`, `git pull`, `git push`). BSD cron has a strict line length limit of 1,000 characters. It silently truncated the command at byte 1,000, cutting off the closing quote `'` and causing `/bin/sh` to throw syntax errors (`unexpected EOF while looking for matching '''`). System mail in `/var/mail/sg` proved cron was attempting to fire, but was syntax-erroring.
- **Resolution:** All execution logic was moved into the executable script `run_tracker.sh` (90 characters in crontab). Verified and active.

### B. Remote Blocking of GitHub Actions (HTTP 403)
- **Symptom:** GitHub Actions runs fail with `HTTP 403 Forbidden` on `4codds.com`.
- **Finding:** The data provider blocks major cloud datacenter IP ranges (Azure/AWS GitHub runners) via Cloudflare/WAF. Residential IP (the user's Mac) succeeds 100% of the time.
- **Protection in Place:** GitHub Actions no longer scrapes or regenerates charts. The Mac runner owns data collection and pushes the generated dashboard; Actions only deploys the checked-in `charts/` directory. This prevents cloud failures from publishing an old board with a new render timestamp.

### C. DraftKings Alternate Line Picking vs Main Lines
- **Problem:** Books often offer alternate lines (e.g., 48.5 at -104 / -128) alongside standard main lines (47.5 at -110 / -110). Scrapers picking strictly the lowest-juice side or consensus match sometimes picked lopsided alternate lines.
- **Solution in `find_book_main_line`:**
  1. Filters lines within 1.0 point of consensus.
  2. Scores lines based on balanced two-sided market vig: $|over\_price - (-110)| + |under\_price - (-110)|$.
  3. Includes an **8-cent hysteresis rule**: If the current line is still present in the candidate set, the scraper will only move to a neighboring line if the new candidate is at least 8 cents more balanced. This prevents 0.5-point oscillation in implied team totals caused by minor price noise.

### D. Status File Integrity
- `data/scraper_status.json` is generated directly by `scrape_nfl_lines.py`. Hand-editing this file should never be permitted.

### E. Staleness Calculation
- The dashboard banner timestamp uses the **oldest open pregame market** across the active matchups ($\min(ts_i)$). A single fresh line cannot mask stale open games, while games whose kickoff has passed retain their final verified line without making the board appear degraded.
- The browser counts elapsed time locally and shifts to a red banner when elapsed time exceeds 4.0 hours (Mon–Sat) or 1.5 hours (Sunday).

---

## 4. Current State (As of Commit `b29c0ee`)

- **Git status:** Clean. Synced with `origin/main`.
- **Database:** All 16 games tracked with valid DK main lines.
- **Status file:** Healthy (`"success": true, "games_scraped": 16`).
- **Dashboard:** Rendered, deployed, and live at [https://sku999.github.io/nfl-line-tracker/](https://sku999.github.io/nfl-line-tracker/).
- **Local Runner:** Configured in `run_tracker.sh`.

---

## 5. Instructions for Incoming AI Agent or Developer

### A. How to Run Manually
```bash
cd /Users/sg/.gemini/antigravity/scratch/nfl-line-tracker
./run_tracker.sh
```
Check status:
```bash
tail -n 30 data/cron.log
cat data/scraper_status.json
```

### B. Sunday Morning Operation
Because GitHub Actions is IP-blocked by the data provider (HTTP 403), Sunday morning captures (6:00 AM – 11:55 AM CT) rely on the Mac runner:
- Ensure the Mac is awake during Sunday morning hours (e.g., via `caffeinate -s` or System Settings > Energy Saver > "Prevent automatic sleeping on power adapter").
- Optional improvement: Migrate from `cron` to a `launchd` plist (`~/Library/LaunchAgents/com.nfl.tracker.plist`), which Apple designs to catch up missed runs upon wake.

### C. Key Code Locations for Modification
- **Line selection / Hysteresis:** `scrape_nfl_lines.py` -> `find_book_main_line()` (lines ~150–225).
- **Staleness threshold:** `plot_nfl_lines.py` -> `get_stale_limit_hours()` and JS timer in `generate_html()` (lines ~450–520).
- **Cadence / Schedule:** `setup_cron.py` -> `CRON_LINES` list.
