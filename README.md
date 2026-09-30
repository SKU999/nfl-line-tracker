# 🏈 NFL Line Movement Tracker

> **Live Dashboard:** [https://sku999.github.io/nfl-line-tracker/](https://sku999.github.io/nfl-line-tracker/)

An automated, continuous NFL betting market tracker and visualization dashboard. Pinned to **DraftKings** lines with **Pinnacle sharp cross-checks**, tracking spread moves, total swings, and implied team total trajectories across every active game of the NFL week.

---

## 📊 Live Dashboard Features

- **High-Contrast Implied Total Charts:** Individual time-series trajectory plots for every matchup on the slate. Electric Cyan/Teal represents the Away team and Radiant Amber/Gold represents the Home team, complete with midpoint guideline and baseline-to-current deltas.
- **Contest Window Grouping:** Matches are grouped by kickoff window:
  - Thursday Night Football (TNF)
  - Sunday Main Slate — Early (12:00 PM CT / 1:00 PM ET)
  - Sunday Main Slate — Late (3:05 PM / 3:25 PM CT)
  - Sunday Night Football (SNF)
  - Monday Night Football (MNF)
- **Sharp Divergence Flags (`*`):** Any game where DraftKings diverges from Pinnacle by 1.0 or more points is automatically tagged with an orange indicator (`*`).
- **Dynamic Browser Feed Age:** Client-side JavaScript ticks every 5 seconds to compute the exact feed age in the browser. It displays minute-level precision (`Xm ago`) and automatically flags the feed status if snapshots stall.
- **Per-Game Freshness Pills:** A dedicated `Updated` column flags the exact time each game's odds were captured, distinguishing fresh lines from markets showing previous values.
- **Movement Context & Notes:** Curated market context and weather/injury updates annotated directly on the board (`data/movement_reasons.json`), with automatic fallback summaries for significant movements (&ge; 0.5 pt).

---

## ⚙️ Data Architecture & Storage

1. **Active Slate File (`data/nfl_lines.jsonl`):**
   - High-performance, rolling view of the active NFL week.
   - Automatically filtered by Tuesday-to-Tuesday NFL weekly windows.
2. **Immutable Perpetual Archive (`data/archive/nfl_lines_perpetual_raw.jsonl`):**
   - Append-only, never truncated ledger storing raw market responses, consensus metrics, and book odds for historical backtesting and statistical analysis.
3. **Proactive Snapshot Deduplication:**
   - The scraper inspects the last recorded snapshot for each game before writing.
   - If market numbers (`dk_spread`, `dk_total`, `pin_spread`, `pin_total`) have not moved and less than 75 minutes have elapsed, redundant duplicate writes are automatically suppressed.
   - When a market line moves, snapshots are recorded immediately regardless of elapsed time.

---

## ⏰ Scrape Schedule & Dual-Runner Cadence

The tracker uses a redundant dual-runner architecture combining GitHub Actions with a local Mac crontab to eliminate black holes:

- **Base Cadence:** Runs every 3 hours, 24 hours a day, 7 days a week:
  - `00:00`, `03:00`, `06:00`, `09:00`, `12:00`, `15:00`, `18:00`, `21:00` Central Time.
  - GitHub Actions runs at minute 12 of these hours (`12 2,5,8,11,14,17,20,23 * * *` UTC) to bypass top-of-hour runner congestion.
  - Local Mac cron runs at minute 00 of these hours.
- **Sunday Kickoff Steam Windows:**
  - `06:00 AM – 10:00 AM CT`: Hourly early-morning monitoring.
  - `11:00 AM, 11:30 AM, 11:55 AM CT`: Pre-kickoff rapid steam capture before 12:00 PM kickoff.
  - `03:00 PM, 03:20 PM CT`: Late afternoon steam capture before 3:25 PM window.
  - `06:00 PM, 07:10 PM CT`: Sunday Night Football steam capture before 7:20 PM kickoff.
- **Monday Night Football Steam Window:**
  - `07:10 PM CT`: Final steam capture before 7:15 PM MNF kickoff.

---

## 🛠️ Local Usage & CLI Commands

### 1. Run Scraper
Fetches current lines using TLS browser impersonation via `curl_cffi` to prevent bot challenge blocks:
```bash
python3 scrape_nfl_lines.py
```

### 2. Generate Charts & HTML Board
Renders matplotlib time-series charts and compiles the HTML dashboard:
```bash
python3 plot_nfl_lines.py
```

### 3. Log Movement Reasons
Annotate market context for a game:
```bash
# Add a reason for a line move:
python3 log_reason.py "ARI @ NYG" "Sharp action on ARI; Giants protection issues flip favorite"

# View all logged reasons:
python3 log_reason.py --list
```

### 4. Manage Local Crontab
Install or inspect the local schedule:
```bash
python3 setup_cron.py install   # Installs active cron entries
python3 setup_cron.py status    # View active tracker cron jobs
python3 setup_cron.py remove    # Cleanly remove tracker jobs
```

---

## 📜 License
MIT License. Open source for NFL analytics, line-tracking research, and sports betting market analysis.
