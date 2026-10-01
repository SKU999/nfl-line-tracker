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
- **Per-Game Freshness Pills:** A dedicated `Last Recorded` column flags the exact time each game's odds were captured, distinguishing fresh lines from markets showing previous values.
- **Movement Summary:** When a spread or total moves ≥ 0.5 pt from the tracker baseline, the board automatically shows what moved and by how much. Annotate a specific reason with `log_reason.py` — the note then appears in the Movement Context column alongside the auto-summary.

---

## ⚙️ Data Source

Lines are pulled from a free, publicly accessible odds screen. This is an unofficial endpoint — suitable for personal research and prototyping. A production deployment should use a licensed odds feed (e.g. Sportradar, Pinnacle API).

---

## ⚙️ Data Architecture & Storage

1. **Active Slate File (`data/nfl_lines.jsonl`):**
   - Rolling view of the current NFL week, filtered by Tuesday-to-Tuesday windows.
2. **Immutable Perpetual Archive (`data/archive/nfl_lines_perpetual_raw.jsonl`):**
   - Append-only ledger of every raw market snapshot; never truncated. For historical backtesting.
3. **Every-Pull Continuity:**
   - Every scheduled scrape is appended, including unchanged markets.
   - Each valid completed pull renders as a chart dot so collection cadence and feed continuity are directly visible.

---

## ⏰ Scrape Schedule

The user's Mac runs the scraper and chart generator. GitHub Actions deploys the checked-in `charts/` directory to Pages after each local update; it does not scrape the odds provider because GitHub-hosted IP ranges are blocked.

The dashboard uses clickable desktop rows and responsive mobile game cards. Selecting a matchup expands its full-width movement chart directly below the game; slate filters narrow the board without leaving the page.

| Window | Times (CT) |
| :--- | :--- |
| Base cadence | 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00 |
| Sunday early (hourly) | 06:00 AM – 10:00 AM |
| Sunday pre-kickoff steam | 11:00 AM, 11:30 AM, 11:55 AM |
| Sunday late steam | 3:00 PM, 3:20 PM |
| SNF steam | 6:00 PM, 7:10 PM |
| MNF steam | 7:10 PM (Monday) |

The base cadence covers duplicate Sunday and Monday hours, so the supplemental cron entries contain only the additional kickoff-steam times. `workflow_dispatch` redeploys the current checked-in charts but does not perform an odds scrape.

---

## 🛠️ Local Usage & CLI Commands

### 1. Run Scraper
```bash
python3 scrape_nfl_lines.py
```

### 2. Generate Charts & HTML Board
```bash
python3 plot_nfl_lines.py
```

### 3. Log Movement Reasons
Add a sourced note for a specific game (it will appear in the Movement Context column):
```bash
python3 log_reason.py "ARI @ NYG" "Giants ruled out LT Andrew Thomas — source: ESPN"
python3 log_reason.py --list
```

### 4. Manage Local Crontab
```bash
python3 setup_cron.py install   # Add local cron entries
python3 setup_cron.py status    # View active entries
python3 setup_cron.py remove    # Remove entries
```

---

## 📜 License
MIT License. Open source for NFL analytics and line-tracking research.
