#!/usr/bin/env python3
"""
NFL Line Tracker — Chart Generator (v5)
Addresses all user feedback:
1. Vibrant electric Amber (#FFB300) and Teal (#00E5FF) so lines pop off dark panels.
   No dark-grey fading on unmoved charts.
2. Crystal-clear spread and implied total presentation:
   - Spread explicitly identifies the favorite: e.g. "PHI -7.0"
   - Implied totals match left-to-right matchup order: Away IT (e.g. "PHI 23.8") then Home IT (e.g. "TEN 16.8")
   - Prevents any ambiguity about who gets the points.
3. Accurate "Baseline vs Now" tracking with snapshot count clearly labeled.
4. Clean sorting: movement first when lines move; by slate order otherwise; Thursday pinned to bottom.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    CT_TZ = ZoneInfo("America/Chicago")
except Exception:
    CT_TZ = timezone(timedelta(hours=-5), "CT")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator

# Import manual reason logger
try:
    from log_reason import load_reasons
except ImportError:
    def load_reasons(): return {}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "nfl_lines.jsonl")
CHART_DIR = os.path.join(BASE_DIR, "charts")

# High-contrast luminous palette
BG_PAGE = "#0d0e15"
BG_CHART = "#151722"
AMBER_BRIGHT = "#FFB300"  # Vibrant amber / gold for Home
TEAL_BRIGHT = "#00E5FF"   # Vibrant electric cyan / teal for Away
TEXT_TITLE = "#EAEAEA"
TEXT_LABEL = "#B0B3C6"
GRID_MUTED = "#222536"


def load_data():
    games = defaultdict(list)
    if not os.path.exists(DATA_FILE):
        print(f"No data at {DATA_FILE}")
        sys.exit(1)
    with open(DATA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            games[s.get("game_id", "?")].append(s)
    for gid in games:
        games[gid].sort(key=lambda s: s.get("ts", ""))
    return games


def parse_ts_ct(ts_str):
    """Parse ISO timestamp and convert explicitly to America/Chicago."""
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
    except:
        dt = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CT_TZ)

parse_ts = parse_ts_ct


def game_day(start_str):
    if not start_str:
        return ""
    try:
        dt_ct = parse_ts_ct(start_str)
        return dt_ct.strftime("%a")
    except:
        return ""


def format_spread_fav(away, home, sp_home):
    """
    Format spread with the favored team explicitly named:
    sp_home < 0: Home favored (e.g. BUF -4.5)
    sp_home > 0: Away favored (e.g. PHI -7.0)
    sp_home == 0: PK
    """
    if sp_home is None:
        return "--"
    if sp_home < 0:
        return f"{home} {sp_home:+.1f}"
    elif sp_home > 0:
        return f"{away} {-sp_home:+.1f}"
    else:
        return "PK"


def plot_game(gid, snapshots, output_dir):
    if not snapshots:
        return None

    away = snapshots[0].get("away", "?")
    home = snapshots[0].get("home", "?")

    timestamps, home_impls, away_impls = [], [], []
    dk_totals, dk_spreads = [], []

    for s in snapshots:
        hi, ai = s.get("home_impl"), s.get("away_impl")
        if hi is None or ai is None:
            continue
        timestamps.append(parse_ts(s["ts"]))
        home_impls.append(hi)
        away_impls.append(ai)
        dk_totals.append(s.get("dk_total"))
        dk_spreads.append(s.get("dk_spread"))

    if not timestamps:
        return None

    fig, ax = plt.subplots(figsize=(11, 4.2), facecolor=BG_PAGE)
    ax.set_facecolor(BG_CHART)

    # Home implied total (AMBER) - Always bright, thick line
    ax.plot(timestamps, home_impls, "o-", color=AMBER_BRIGHT, linewidth=2.8,
            markersize=7, markerfacecolor=AMBER_BRIGHT, markeredgecolor=BG_CHART, markeredgewidth=1.5,
            label=f"{home} (Home)", zorder=5)

    # Away implied total (TEAL) - Always bright, thick line
    ax.plot(timestamps, away_impls, "s-", color=TEAL_BRIGHT, linewidth=2.8,
            markersize=7, markerfacecolor=TEAL_BRIGHT, markeredgecolor=BG_CHART, markeredgewidth=1.5,
            label=f"{away} (Away)", zorder=5)

    # Value annotations on the latest points
    ax.annotate(f"{home} {home_impls[-1]:.1f}",
                (timestamps[-1], home_impls[-1]),
                textcoords="offset points", xytext=(9, 7),
                fontsize=11, fontweight="bold", color=AMBER_BRIGHT, zorder=6)
    ax.annotate(f"{away} {away_impls[-1]:.1f}",
                (timestamps[-1], away_impls[-1]),
                textcoords="offset points", xytext=(9, -15),
                fontsize=11, fontweight="bold", color=TEAL_BRIGHT, zorder=6)

    # If multiple snapshots and movement occurred, annotate baseline
    if len(timestamps) > 1:
        if home_impls[0] != home_impls[-1]:
            ax.annotate(f"{home_impls[0]:.1f}",
                        (timestamps[0], home_impls[0]),
                        textcoords="offset points", xytext=(-9, 7),
                        fontsize=9, color=AMBER_BRIGHT, alpha=0.6, ha="right")
        if away_impls[0] != away_impls[-1]:
            ax.annotate(f"{away_impls[0]:.1f}",
                        (timestamps[0], away_impls[0]),
                        textcoords="offset points", xytext=(-9, -15),
                        fontsize=9, color=TEAL_BRIGHT, alpha=0.6, ha="right")

    # Title with explicit favorite spread + total
    fav_sp = format_spread_fav(away, home, dk_spreads[-1])
    tot = dk_totals[-1]
    tot_str = f"O/U {tot:.1f}" if tot is not None else ""
    ax.set_title(f"{away} @ {home}   |   {fav_sp}   |   {tot_str}",
                 fontsize=13, fontweight="bold", pad=12, loc="left", color=TEXT_TITLE)

    ax.set_ylabel("Implied Total", fontsize=10, color=TEXT_LABEL)
    leg = ax.legend(loc="upper right", fontsize=9, framealpha=0.6,
                    facecolor=BG_PAGE, edgecolor="#2d3045", labelcolor=TEXT_TITLE)

    # Soft midpoint guideline
    mid = (home_impls[-1] + away_impls[-1]) / 2
    ax.axhline(y=mid, color=GRID_MUTED, linestyle="--", linewidth=0.9, zorder=1)

    # Spines and ticks
    ax.tick_params(colors=TEXT_LABEL, labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#2d3045")
    ax.spines["bottom"].set_color("#2d3045")
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5]))

    # X-axis time handling
    if len(timestamps) == 1:
        t = timestamps[0]
        ax.set_xlim(t - timedelta(hours=12), t + timedelta(hours=12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d %-I%p"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    elif (timestamps[-1] - timestamps[0]) < timedelta(hours=6):
        mid_t = timestamps[0] + (timestamps[-1] - timestamps[0]) / 2
        ax.set_xlim(mid_t - timedelta(hours=3), mid_t + timedelta(hours=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d %-I%p"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    elif (timestamps[-1] - timestamps[0]) < timedelta(days=2):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-I%p"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-m/%-d"))
        ax.xaxis.set_major_locator(mdates.DayLocator())

    fig.autofmt_xdate(rotation=0, ha="center")
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    fname = f"{away}_{home}.png"
    fig.savefig(os.path.join(output_dir, fname), dpi=150,
                bbox_inches="tight", facecolor=BG_PAGE)
    plt.close(fig)
    return fname


def build_board_rows(games_data):
    rows = []
    for gid, snaps in games_data.items():
        first, last = snaps[0], snaps[-1]
        away, home = last.get("away", "?"), last.get("home", "?")
        day = game_day(last.get("start", ""))

        dk_sp0 = first.get("dk_spread")
        dk_sp1 = last.get("dk_spread")
        dk_t0 = first.get("dk_total")
        dk_t1 = last.get("dk_total")

        pin_sp = last.get("pin_spread")
        pin_tot = last.get("pin_total")

        # Movement deltas from baseline snapshot
        sp_d = (dk_sp1 - dk_sp0) if dk_sp1 is not None and dk_sp0 is not None else 0
        t_d = (dk_t1 - dk_t0) if dk_t1 is not None and dk_t0 is not None else 0

        # DraftKings vs Pinnacle divergence
        sp_div = abs(dk_sp1 - pin_sp) if dk_sp1 is not None and pin_sp is not None else 0
        t_div = abs(dk_t1 - pin_tot) if dk_t1 is not None and pin_tot is not None else 0

        # Formatted spreads
        sp_fav_now = format_spread_fav(away, home, dk_sp1)
        sp_fav_open = format_spread_fav(away, home, dk_sp0)

        rows.append({
            "away": away, "home": home, "day": day, "gid": gid,
            "n_snaps": len(snaps),
            "start": last.get("start", ""),
            "sp_fav_open": sp_fav_open,
            "sp_fav_now": sp_fav_now,
            "sp_d": sp_d,
            "t0": dk_t0, "t1": dk_t1, "t_d": t_d,
            "pin_sp": pin_sp, "pin_tot": pin_tot,
            "sp_div": sp_div, "t_div": t_div,
            "ai": last.get("away_impl"),
            "hi": last.get("home_impl"),
            "max_move": max(abs(sp_d), abs(t_d)),
            "is_thu": day == "Thu",
        })

    # Sort logic:
    # 1. Non-Thursday games first, Thursday pinned at bottom
    # 2. Games with movement (max_move > 0) float to top, sorted by movement desc
    # 3. If no movement yet, sorted by kickoff time
    rows.sort(key=lambda r: (
        1 if r["is_thu"] else 0,
        -r["max_move"],
        r["start"]
    ))
    return rows


def delta_cell(d):
    """Direction via text only: ▲ / ▼ / --, no color noise."""
    if abs(d) < 0.1:
        return "<td class='flat'>--</td>"
    arrow = "▲" if d > 0 else "▼"
    return f"<td class='delta'>{arrow} {abs(d):.1f}</td>"


def generate_html(chart_files, board_rows, output_dir, latest_ts=None):
    now_ct = datetime.now(CT_TZ)
    now_ct_str = now_ct.strftime("%a %b %d, %Y %-I:%M %p %Z")
    total_snaps = sum(r["n_snaps"] for r in board_rows)
    all_reasons = load_reasons()

    # Staleness check: compare latest snapshot timestamp to current time
    stale_hours = 0.0
    is_stale = False
    last_success_str = "Unknown"
    if latest_ts:
        try:
            last_ct = parse_ts_ct(latest_ts)
            diff = now_ct - last_ct
            stale_hours = max(0.0, diff.total_seconds() / 3600.0)
            last_success_str = last_ct.strftime("%a %b %d, %-I:%M %p %Z")
            if stale_hours >= 4.0:
                is_stale = True
        except:
            pass

    # Status Badge
    if is_stale:
        status_banner = f"""<div class='alert-banner stale'>
            <span class='alert-icon'>⚠️</span>
            <b>SCRAPER STALE WARNING:</b> Last successful snapshot was <b>{stale_hours:.1f} hours ago</b> ({last_success_str}).
            Expected run interval is 3 hours. Check <code>data/cron.log</code> for errors.
        </div>"""
    else:
        status_banner = f"""<div class='alert-banner healthy'>
            <span class='status-dot'></span>
            <b>Feed Healthy:</b> Last snapshot captured <b>{last_success_str}</b> ({stale_hours:.1f} hrs ago).
        </div>"""

    table_rows = []
    for r in board_rows:
        row_cls = "thu" if r["is_thu"] else ""
        tag = "<span class='tag'>THU</span> " if r["is_thu"] else ""
        
        # Pinnacle divergence flag: orange asterisk if 1+ pt divergence
        sp_flag = " <span class='div' title='Pinnacle divergence ≥ 1 pt'>*</span>" if r["sp_div"] >= 1 else ""
        t_flag = " <span class='div' title='Pinnacle divergence ≥ 1 pt'>*</span>" if r["t_div"] >= 1 else ""

        # Format values
        tot_open_str = f"{r['t0']:.1f}" if r['t0'] is not None else "--"
        tot_now_str = f"{r['t1']:.1f}" if r['t1'] is not None else "--"
        away_it_str = f"{r['away']} {r['ai']:.1f}" if r['ai'] is not None else "--"
        home_it_str = f"{r['home']} {r['hi']:.1f}" if r['hi'] is not None else "--"

        # Check for user-logged reason
        mu_key = f"{r['away']} @ {r['home']}"
        notes_list = all_reasons.get(mu_key, [])
        reason_text = notes_list[-1]["note"] if notes_list else ""
        reason_cell = f"<td class='reason' title='{reason_text}'>{reason_text}</td>" if reason_text else "<td class='reason-empty'>--</td>"

        table_rows.append(f"""<tr class='{row_cls}'>
            <td class='mu'>{tag}{r['away']} @ <b>{r['home']}</b></td>
            <td>{r['sp_fav_open']}</td>
            <td><b>{r['sp_fav_now']}</b>{sp_flag}</td>
            {delta_cell(r['sp_d'])}
            <td>{tot_open_str}</td>
            <td><b>{tot_now_str}</b>{t_flag}</td>
            {delta_cell(r['t_d'])}
            <td class='it-away'>{away_it_str}</td>
            <td class='it-home'>{home_it_str}</td>
            {reason_cell}
            <td class='snaps'>{r['n_snaps']}</td>
        </tr>""")

    chart_lookup = {f.replace(".png", ""): f for f in chart_files}
    cards = []
    for r in board_rows:
        key = f"{r['away']}_{r['home']}"
        if key in chart_lookup:
            cls = "card thu-card" if r["is_thu"] else "card"
            cards.append(f"<div class='{cls}'><img src='{chart_lookup[key]}' alt='{r['away']} @ {r['home']}'></div>")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NFL Lines — DraftKings Tracker</title>
<meta http-equiv='refresh' content='1800'>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: {BG_PAGE};
    color: #C5C8D8;
    padding: 24px;
    line-height: 1.4;
  }}
  h1 {{ font-size: 22px; color: #FFFFFF; font-weight: 700; margin-bottom: 4px; }}
  .sub {{ color: #72768E; font-size: 12px; margin-bottom: 22px; }}
  .legend-box {{
    display: inline-flex;
    gap: 16px;
    margin-left: 12px;
    font-size: 11px;
    font-weight: 600;
  }}
  .dot-teal {{ color: {TEAL_BRIGHT}; }}
  .dot-amber {{ color: {AMBER_BRIGHT}; }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 30px;
    font-size: 12.5px;
    background: #12131C;
    border-radius: 8px;
    overflow: hidden;
  }}
  th {{
    text-align: left;
    padding: 8px 12px;
    color: #6C7089;
    border-bottom: 1px solid #1F2233;
    font-weight: 600;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }}
  td {{
    padding: 7px 12px;
    border-bottom: 1px solid #171926;
    color: #8D92AA;
  }}
  td b {{ color: #E6E8F2; }}
  .mu {{ color: #E0E2EC; font-size: 13px; }}
  .mu b {{ color: #FFFFFF; }}
  .delta {{ color: #A0A5BC; font-weight: 600; }}
  .flat {{ color: #3E4259; }}
  .it-away {{ color: {TEAL_BRIGHT}; font-weight: 600; }}
  .it-home {{ color: {AMBER_BRIGHT}; font-weight: 600; }}
  .reason {{ color: #E0E2EC; font-size: 11.5px; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .reason-empty {{ color: #35384B; font-size: 11px; }}
  .snaps {{ color: #4E526B; font-size: 11px; text-align: center; }}
  .tag {{
    background: #25283B;
    color: #8287A5;
    font-size: 9px;
    font-weight: 700;
    padding: 2px 5px;
    border-radius: 3px;
    margin-right: 4px;
  }}
  .div {{ color: {AMBER_BRIGHT}; font-weight: bold; margin-left: 2px; }}
  tr.thu td {{ opacity: 0.4; }}

  /* Alert Banners */
  .alert-banner {{
    padding: 10px 16px;
    border-radius: 6px;
    margin-bottom: 20px;
    font-size: 12.5px;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .alert-banner.healthy {{
    background: rgba(34, 184, 160, 0.12);
    border: 1px solid rgba(34, 184, 160, 0.35);
    color: #4FE1C8;
  }}
  .alert-banner.stale {{
    background: rgba(255, 68, 68, 0.15);
    border: 1px solid rgba(255, 68, 68, 0.5);
    color: #FF7070;
    font-size: 13px;
    animation: pulse 2s infinite;
  }}
  .status-dot {{
    width: 8px;
    height: 8px;
    background: #00E5FF;
    border-radius: 50%;
    box-shadow: 0 0 8px #00E5FF;
    display: inline-block;
  }}
  .alert-icon {{ font-size: 16px; }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(560px, 1fr));
    gap: 14px;
  }}
  .card {{
    background: {BG_CHART};
    border: 1px solid #1E2130;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }}
  .card img {{
    width: 100%;
    display: block;
  }}
  .thu-card {{ opacity: 0.45; }}
</style>
</head>
<body>
<h1>NFL Line Movement — DraftKings</h1>
<p class='sub'>
  DraftKings pinned. Cross-checked with Pinnacle (* = 1+ pt divergence).<br>
  Dashboard refreshed {now_ct_str} &middot; {total_snaps} snapshots recorded
  <span class='legend-box'>
    <span class='dot-teal'>■ Away Implied Total</span>
    <span class='dot-amber'>● Home Implied Total</span>
  </span>
</p>

{status_banner}

<table>
<thead>
<tr>
  <th>Matchup</th>
  <th>Baseline Spread</th>
  <th>Current Spread</th>
  <th>Δ SP</th>
  <th>Baseline Total</th>
  <th>Current Total</th>
  <th>Δ Tot</th>
  <th>Away IT (Teal)</th>
  <th>Home IT (Amber)</th>
  <th>Movement Context / Reason</th>
  <th style="text-align: center;">Snaps</th>
</tr>
</thead>
<tbody>
{''.join(table_rows)}
</tbody>
</table>

<div class='grid'>
{''.join(cards)}
</div>
</body>
</html>"""

    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(html)


def main():
    games = load_data()
    print(f"Loaded {len(games)} games, {sum(len(v) for v in games.values())} snapshots")

    chart_files = []
    for gid, snaps in games.items():
        m = f"{snaps[0].get('away','?')} @ {snaps[0].get('home','?')}"
        fname = plot_game(gid, snaps, CHART_DIR)
        if fname:
            chart_files.append(fname)
            print(f"  {m}: {len(snaps)} pts -> {fname}")
        else:
            print(f"  {m}: skipped")

    board_rows = build_board_rows(games)
    
    # Extract latest snapshot timestamp across all games
    latest_ts = None
    for snaps in games.values():
        if snaps:
            ts = snaps[-1].get("ts")
            if ts and (latest_ts is None or ts > latest_ts):
                latest_ts = ts

    generate_html(chart_files, board_rows, CHART_DIR, latest_ts=latest_ts)
    print(f"\nGenerated {len(chart_files)} charts -> {CHART_DIR}/index.html")


if __name__ == "__main__":
    main()
