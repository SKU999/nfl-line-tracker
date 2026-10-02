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
from html import escape
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
STATUS_FILE = os.path.join(BASE_DIR, "data", "scraper_status.json")
CHART_DIR = os.path.join(BASE_DIR, "charts")


def load_scraper_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None

# High-contrast luminous palette
BG_PAGE = "#0d0e15"
BG_CHART = "#151722"
AMBER_BRIGHT = "#FFB300"  # Vibrant amber / gold for Home
TEAL_BRIGHT = "#00E5FF"   # Vibrant electric cyan / teal for Away
TEXT_TITLE = "#EAEAEA"
TEXT_LABEL = "#B0B3C6"
GRID_MUTED = "#222536"


def get_current_slate_window(ref_time=None):
    """
    Returns (start_dt, end_dt) for the active NFL week in Central Time.
    An NFL week starts Tuesday 00:00 CT and concludes Tuesday 06:00 CT.
    """
    if ref_time is None:
        ref_time = datetime.now(CT_TZ)
    days_since_tue = (ref_time.weekday() - 1) % 7
    week_start = (ref_time - timedelta(days=days_since_tue)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7, hours=6)
    return week_start, week_end


def load_data(active_only=True):
    games = defaultdict(list)
    if not os.path.exists(DATA_FILE):
        print(f"No data at {DATA_FILE}")
        sys.exit(1)

    week_start, week_end = get_current_slate_window()

    with open(DATA_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            away = s.get("away")
            home = s.get("home")
            if not away or not home:
                continue
            mu_key = f"{away}@{home}"
            games[mu_key].append(s)

    for mu in list(games.keys()):
        # Every stored pull is intentionally retained and rendered as a dot,
        # even when the market values are unchanged.
        games[mu].sort(key=lambda s: s.get("ts", ""))

    if active_only:
        filtered = {}
        for mu, snaps in games.items():
            start_str = next((s.get("start") for s in reversed(snaps) if s.get("start")), "")
            if start_str:
                try:
                    start_dt = parse_ts_ct(start_str)
                    if week_start <= start_dt <= week_end:
                        filtered[mu] = snaps
                except Exception:
                    filtered[mu] = snaps
            else:
                filtered[mu] = snaps
        if filtered:
            return filtered

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


def classify_slate_window(start_str):
    """
    Classify game into an NFL contest window using kickoff time (Central Time):
    - TNF: Thursday Night Football
    - SUN_EARLY: Sunday Main Slate — Early (~12:00 PM CT / 1:00 PM ET)
    - SUN_LATE: Sunday Main Slate — Late (~3:05 - 3:25 PM CT / 4:05 - 4:25 PM ET)
    - SNF: Sunday Night Football (~7:20 PM CT / 8:20 PM ET)
    - MNF: Monday Night Football (~7:15 PM CT / 8:15 PM ET)
    - OTHER_PRIMETIME: International / Saturday / Special Primetime

    Returns: (window_code, window_display_label, window_sort_order)
    """
    if not start_str:
        return ("OTHER_PRIMETIME", "OTHER / SPECIAL PRIMETIME", 99)
    try:
        dt_ct = parse_ts_ct(start_str)
        weekday = dt_ct.strftime("%a")
        hour = dt_ct.hour

        if weekday == "Thu":
            return ("TNF", "THURSDAY NIGHT FOOTBALL", 1)
        if weekday == "Sun":
            if hour < 11:
                return ("OTHER_PRIMETIME", "OTHER / SPECIAL PRIMETIME", 2)
            elif hour < 14:
                return ("SUN_EARLY", "SUNDAY MAIN SLATE — EARLY", 3)
            elif hour < 18:
                return ("SUN_LATE", "SUNDAY MAIN SLATE — LATE", 4)
            else:
                return ("SNF", "SUNDAY NIGHT FOOTBALL", 5)
        if weekday == "Mon":
            return ("MNF", "MONDAY NIGHT FOOTBALL", 6)
        return ("OTHER_PRIMETIME", "OTHER / SPECIAL PRIMETIME", 7)
    except:
        return ("OTHER_PRIMETIME", "OTHER / SPECIAL PRIMETIME", 99)


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
    ax.plot(timestamps, home_impls, "o-", color=AMBER_BRIGHT, linewidth=2.4,
            markersize=5.5, markerfacecolor=AMBER_BRIGHT, markeredgecolor=BG_CHART, markeredgewidth=1.0,
            label=f"{home} (Home)", zorder=5)

    # Away implied total (TEAL) - Always bright, thick line
    ax.plot(timestamps, away_impls, "o-", color=TEAL_BRIGHT, linewidth=2.4,
            markersize=5.5, markerfacecolor=TEAL_BRIGHT, markeredgecolor=BG_CHART, markeredgewidth=1.0,
            label=f"{away} (Away)", zorder=5)

    # Faint opening references make the baseline easy to compare without
    # competing with the timestamp dots.
    ax.axhline(home_impls[0], color=AMBER_BRIGHT, linestyle=":", linewidth=1.0, alpha=0.24, zorder=1)
    ax.axhline(away_impls[0], color=TEAL_BRIGHT, linestyle=":", linewidth=1.0, alpha=0.24, zorder=1)

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

    # Title with explicit favorite spread + total from latest valid entries
    valid_pairs = [(sp, tot) for sp, tot in zip(dk_spreads, dk_totals) if sp is not None and tot is not None]
    if valid_pairs:
        fav_sp = format_spread_fav(away, home, valid_pairs[-1][0])
        tot = valid_pairs[-1][1]
    else:
        fav_sp = format_spread_fav(away, home, dk_spreads[-1] if dk_spreads else None)
        tot = dk_totals[-1] if dk_totals else None
    tot_str = f"O/U {tot:.1f}" if tot is not None else ""
    ax.set_title(f"{away} @ {home}   |   {fav_sp}   |   {tot_str}   |   {len(timestamps)} pulls",
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

    # X-axis time handling with explicit Central Time timezone
    if len(timestamps) == 1:
        t = timestamps[0]
        ax.set_xlim(t - timedelta(hours=12), t + timedelta(hours=12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d %-I%p CT", tz=CT_TZ))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=CT_TZ))
    elif (timestamps[-1] - timestamps[0]) < timedelta(hours=6):
        mid_t = timestamps[0] + (timestamps[-1] - timestamps[0]) / 2
        ax.set_xlim(mid_t - timedelta(hours=3), mid_t + timedelta(hours=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m/%-d %-I%p CT", tz=CT_TZ))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=CT_TZ))
    elif (timestamps[-1] - timestamps[0]) < timedelta(days=2):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-I%p CT", tz=CT_TZ))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=CT_TZ))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %-m/%-d", tz=CT_TZ))
        ax.xaxis.set_major_locator(mdates.DayLocator(tz=CT_TZ))

    fig.autofmt_xdate(rotation=0, ha="center")
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    fname = f"{away}_{home}.png"
    fig.savefig(os.path.join(output_dir, fname), dpi=150,
                bbox_inches="tight", facecolor=BG_PAGE)
    plt.close(fig)
    return fname


def get_stale_limit_hours(ref_dt=None):
    """
    On Sunday (when cadence is hourly / rapid steam), staleness flags after 1.5 hours (90 mins).
    On other days (base 3-hour cadence), staleness flags after 4.0 hours.
    """
    dt = ref_dt or datetime.now(CT_TZ)
    return 1.5 if dt.weekday() == 6 else 4.0


def build_board_rows(games_data, latest_ts=None):
    rows = []
    latest_dt = parse_ts_ct(latest_ts) if latest_ts else datetime.now(CT_TZ)
    stale_limit = get_stale_limit_hours(latest_dt)

    for gid, snaps in games_data.items():
        if not snaps:
            continue

        valid_snaps = [s for s in snaps if s.get("dk_spread") is not None and s.get("dk_total") is not None]
        first = valid_snaps[0] if valid_snaps else snaps[0]
        last = valid_snaps[-1] if valid_snaps else snaps[-1]

        latest_meta = snaps[-1]
        away = latest_meta.get("away") or snaps[0].get("away", "?")
        home = latest_meta.get("home") or snaps[0].get("home", "?")
        start_time = latest_meta.get("start") or snaps[0].get("start", "")
        day = game_day(start_time)
        market_closed = False
        game_status_str = ""
        if start_time:
            try:
                start_dt = parse_ts_ct(start_time)
                market_closed = start_dt <= latest_dt
                if market_closed:
                    game_status_str = f"Started {start_dt.strftime('%a %-I:%M %p CT')}"
            except Exception:
                pass

        dk_sp0 = first.get("dk_spread")
        dk_sp1 = last.get("dk_spread")
        dk_t0 = first.get("dk_total")
        dk_t1 = last.get("dk_total")

        pin_sp = last.get("pin_spread")
        pin_tot = last.get("pin_total")

        # A missing DraftKings market in the latest scrape is a degradation
        # immediately, even while the last valid line is recent.
        latest_market_missing = not market_closed and (
            latest_meta.get("dk_spread") is None or
            latest_meta.get("dk_total") is None
        )
        last_valid_ts = last.get("ts")
        is_stale_game = False
        last_valid_str = "Unknown"
        if last_valid_ts:
            try:
                last_valid_dt = parse_ts_ct(last_valid_ts)
                age_hrs = (latest_dt - last_valid_dt).total_seconds() / 3600.0
                if not market_closed and age_hrs >= stale_limit:
                    is_stale_game = True
                if last_valid_dt.date() == latest_dt.date():
                    last_valid_str = last_valid_dt.strftime("%-I:%M %p CT")
                else:
                    last_valid_str = last_valid_dt.strftime("%a %-I:%M %p CT")
            except Exception:
                pass

        # Movement deltas from baseline snapshot
        sp_d = (dk_sp1 - dk_sp0) if dk_sp1 is not None and dk_sp0 is not None else 0
        t_d = (dk_t1 - dk_t0) if dk_t1 is not None and dk_t0 is not None else 0

        # DraftKings vs Pinnacle divergence
        sp_div = abs(dk_sp1 - pin_sp) if dk_sp1 is not None and pin_sp is not None else 0
        t_div = abs(dk_t1 - pin_tot) if dk_t1 is not None and pin_tot is not None else 0

        # Formatted spreads
        sp_fav_now = format_spread_fav(away, home, dk_sp1)
        sp_fav_open = format_spread_fav(away, home, dk_sp0)

        # Classify slate window
        slate_code, slate_label, slate_order = classify_slate_window(start_time)

        rows.append({
            "away": away, "home": home, "day": day, "gid": gid,
            "n_snaps": len(snaps),
            "n_chart_points": len(valid_snaps),
            "n_failed_attempts": len(snaps) - len(valid_snaps),
            "start": start_time,
            "slate_window": slate_code,
            "slate_label": slate_label,
            "slate_order": slate_order,
            "sp_fav_open": sp_fav_open,
            "sp_fav_now": sp_fav_now,
            "dk_sp0": dk_sp0, "dk_sp1": dk_sp1,
            "sp_d": sp_d,
            "t0": dk_t0, "t1": dk_t1, "t_d": t_d,
            "pin_sp": pin_sp, "pin_tot": pin_tot,
            "sp_div": sp_div, "t_div": t_div,
            "ai": last.get("away_impl"),
            "hi": last.get("home_impl"),
            "max_move": max(abs(sp_d), abs(t_d)),
            "is_thu": slate_code == "TNF",
            "is_stale_game": is_stale_game,
            "latest_market_missing": latest_market_missing,
            "market_closed": market_closed,
            "game_status_str": game_status_str,
            "last_valid_str": last_valid_str,
            "last_valid_ts": last_valid_ts,
        })

    # Sort logic:
    # 1. By slate window order: TNF -> SUN_EARLY -> SUN_LATE -> SNF -> MNF -> OTHER
    # 2. Within each slate window, preserve existing sorting:
    #    - Movement first (max_move descending)
    #    - Then by start time
    rows.sort(key=lambda r: (
        r["slate_order"],
        -r["max_move"],
        r["start"]
    ))
    return rows


def delta_cell(d, significant_at=1.0):
    """Movement magnitude with a neutral emphasis badge for meaningful changes."""
    if abs(d) < 0.1:
        return "<td class='flat'>--</td>"
    cls = "movement-badge significant" if abs(d) >= significant_at else "movement-badge"
    return f"<td class='delta'><span class='{cls}'>{abs(d):.1f}</span></td>"


def generate_html(chart_files, board_rows, output_dir, latest_ts=None):
    now_ct = datetime.now(CT_TZ)
    now_ct_str = now_ct.strftime("%a %b %d, %Y %-I:%M %p %Z")
    total_snaps = sum(r["n_snaps"] for r in board_rows)
    total_chart_points = sum(r.get("n_chart_points", r["n_snaps"]) for r in board_rows)
    all_reasons = load_reasons()
    status_info = load_scraper_status()

    # Determine board ages:
    # Base banner freshness on the OLDEST game's latest recorded line
    # so a single updated game does not mask that 15 games are stale.
    open_rows = [r for r in board_rows if not r.get("market_closed", False)]
    closed_count = len(board_rows) - len(open_rows)
    game_timestamps = [r["last_valid_ts"] for r in open_rows if r.get("last_valid_ts")]
    oldest_ts = min(game_timestamps) if game_timestamps else latest_ts
    newest_ts = max(game_timestamps) if game_timestamps else latest_ts

    banner_ts = oldest_ts or latest_ts
    stale_hours = 0.0
    stale_mins = 0
    is_stale = False
    last_success_str = "Unknown"
    initial_age_str = "just now"
    if banner_ts:
        try:
            last_ct = parse_ts_ct(banner_ts)
            diff = now_ct - last_ct
            sec = max(0, int(diff.total_seconds()))
            stale_mins = sec // 60
            stale_hours = sec / 3600.0
            last_success_str = last_ct.strftime("%a %b %d, %-I:%M %p %Z")
            if stale_mins < 1:
                initial_age_str = "just now"
            elif stale_mins < 60:
                initial_age_str = f"{stale_mins}m ago"
            else:
                initial_age_str = f"{stale_hours:.1f} hrs ago"
            stale_limit = get_stale_limit_hours(now_ct)
            if stale_hours >= stale_limit:
                is_stale = True
        except:
            pass

    missing_games = [r for r in board_rows if r.get("latest_market_missing")]
    missing_count = len(missing_games)
    stale_games = [r for r in board_rows if r.get("is_stale_game")]
    stale_count = len(stale_games)

    # Check if the most recent scraper pull failed
    pull_failed = False
    fail_desc = ""
    if status_info and status_info.get("success") is False:
        pull_failed = True
        err = status_info.get("error") or "Unknown error"
        if len(err) > 85:
            err = err[:82] + "..."
        ts_fail_str = "recent run"
        if status_info.get("ts"):
            try:
                fct = parse_ts_ct(status_info["ts"])
                ts_fail_str = fct.strftime("%-I:%M %p %Z")
            except:
                pass
        fail_desc = f"Odds pull was incomplete at {ts_fail_str} ({err}). Displaying the last verified line for affected games (oldest line: {last_success_str}, {initial_age_str}). Check the local runner log for details."

    # Status Badge
    if pull_failed:
        status_banner = f"""<div id='feed-banner' class='alert-banner warning' data-banner-kind='failed' data-feed-ts='{banner_ts}' data-feed-ts-label='{last_success_str}'>
            <span class='alert-icon'>⚠️</span>
            <b>SCRAPER DEGRADED:</b> {fail_desc}
        </div>"""
    elif missing_count > 0:
        missing_names = ", ".join(f"{r['away']}@{r['home']}" for r in missing_games[:4])
        status_banner = f"""<div id='feed-banner' class='alert-banner warning' data-banner-kind='degraded' data-feed-ts='{banner_ts}' data-feed-ts-label='{last_success_str}'>
            <span class='alert-icon'>⚠️</span>
            <b>PARTIAL FEED DEGRADATION:</b> {missing_count} of {len(board_rows)} games ({missing_names}) had no complete DraftKings market in the latest scrape and are showing prior lines. Board age based on oldest line: <span id='feed-time'>{last_success_str}</span> (<span id='feed-age-dynamic'>{initial_age_str}</span>).
        </div>"""
    elif is_stale or stale_count > 0:
        status_banner = f"""<div id='feed-banner' class='alert-banner stale' data-banner-kind='stale' data-feed-ts='{banner_ts}' data-feed-ts-label='{last_success_str}'>
            <span class='alert-icon'>⚠️</span>
            <b>SCRAPER STALE WARNING:</b> Oldest game line was captured <span id='feed-age-dynamic'>{initial_age_str}</span> (<span id='feed-time'>{last_success_str}</span>). Check the local runner log for details.
        </div>"""
    else:
        closed_note = f" {closed_count} game{'s have' if closed_count != 1 else ' has'} started and is showing its final verified pregame line." if closed_count else ""
        status_banner = f"""<div id='feed-banner' class='alert-banner healthy' data-banner-kind='healthy' data-feed-ts='{banner_ts}' data-feed-ts-label='{last_success_str}'>
            <span class='status-dot'></span>
            <b>Feed Healthy:</b> All {len(open_rows)} open markets updated.{closed_note} Board age based on oldest open market: <span id='feed-time'>{last_success_str}</span> (<span id='feed-age-dynamic'>{initial_age_str}</span>).
        </div>"""

    chart_lookup = {f.replace(".png", ""): f for f in chart_files}
    cache_token = int(now_ct.timestamp())
    table_rows = []
    mobile_cards = []
    current_slate = None

    for r in board_rows:
        # Insert separator row if contest window changes
        if r["slate_window"] != current_slate:
            current_slate = r["slate_window"]
            table_rows.append(f"""<tr class='slate-sep-row' data-slate='{r["slate_window"]}'>
                <td colspan='12' class='slate-sep-cell'>
                    <span class='sep-dash'>────</span>
                    <span class='sep-label'>{r["slate_label"]}</span>
                    <span class='sep-dash'>────</span>
                </td>
            </tr>""")

        row_classes = []
        if r["is_thu"]:
            row_classes.append("thu")
        if r.get("market_closed"):
            row_classes.append("closed-game")
        row_cls = " ".join(row_classes)
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
        if not reason_text and r["max_move"] >= 0.5:
            move_parts = []
            if abs(r["sp_d"]) >= 0.5 and r["dk_sp0"] is not None and r["dk_sp1"] is not None:
                # dk_sp0/dk_sp1 are the home team's line (positive = home is dog).
                # Convert to the favorite's perspective so the sign is always negative.
                fav_team = r["sp_fav_now"].split()[0] if r["sp_fav_now"] not in ("PK", "--") else ""
                if r["dk_sp1"] > 0:
                    # Away is favorite; their line is the negated home value
                    fav_sp0 = -r["dk_sp0"]
                    fav_sp1 = -r["dk_sp1"]
                else:
                    fav_sp0 = r["dk_sp0"]
                    fav_sp1 = r["dk_sp1"]
                sp0_str = f"{fav_sp0:+.1f}"
                sp1_str = f"{fav_sp1:+.1f}"
                move_parts.append(f"Spread {fav_team} {sp0_str} → {sp1_str}")
            if abs(r["t_d"]) >= 0.5:
                move_parts.append(f"Total {r['t0']:.1f} → {r['t1']:.1f}")
            reason_text = "; ".join(move_parts)
        safe_reason = escape(reason_text, quote=True)
        reason_cell = f"<td class='reason' title='{safe_reason}'>{safe_reason}</td>" if reason_text else "<td class='reason-empty'>--</td>"

        lv_str = r["last_valid_str"]
        if r.get("market_closed"):
            status_text = r.get("game_status_str") or "Game started"
            updated_cell = f"<td style='text-align:center;'><span class='pill-closed' title='Pregame market closed at kickoff. Showing the final verified pregame line from {lv_str}.'>{status_text}</span></td>"
        elif r["latest_market_missing"] or r["is_stale_game"]:
            updated_cell = f"<td style='text-align:center;'><span class='pill-stale' title='Market was missing or stale on the latest scraper run. Showing last verified line from {lv_str}.'>⚠️ {lv_str}</span></td>"
        else:
            updated_cell = f"<td style='text-align:center;'><span class='pill-fresh'>{lv_str}</span></td>"

        game_key = f"{r['away']}_{r['home']}"
        chart_file = chart_lookup.get(game_key)
        chart_src = f"{chart_file}?v={cache_token}" if chart_file else ""
        chart_html = (
            f"<img class='expanded-chart' src='{chart_src}' alt='{r['away']} at {r['home']} line movement chart'>"
            if chart_file else "<p class='chart-unavailable'>Chart unavailable for this matchup.</p>"
        )
        detail_stats = f"""
            <div class='detail-stats'>
                <div><span>Opening spread</span><strong>{r['sp_fav_open']}</strong></div>
                <div><span>Current spread</span><strong>{r['sp_fav_now']}</strong></div>
                <div><span>Opening total</span><strong>{tot_open_str}</strong></div>
                <div><span>Current total</span><strong>{tot_now_str}</strong></div>
                <div><span>Away implied</span><strong class='it-away'>{away_it_str}</strong></div>
                <div><span>Home implied</span><strong class='it-home'>{home_it_str}</strong></div>
                <div><span>Last valid pull</span><strong>{lv_str}</strong></div>
                <div><span>Chart dots</span><strong>{r.get('n_chart_points', r['n_snaps'])}</strong></div>
            </div>""".strip()

        table_rows.append(f"""<tr class='game-row {row_cls}' data-slate='{r["slate_window"]}' data-game='{game_key}' data-toggle-game='{game_key}' tabindex='0' role='button' aria-expanded='false' aria-controls='desktop-panel-{game_key}'>
            <td class='mu'>{tag}{r['away']} @ <b>{r['home']}</b><span class='view-chart'>View chart <span class='chevron'>⌄</span></span></td>
            <td>{r['sp_fav_open']}</td>
            <td><b>{r['sp_fav_now']}</b>{sp_flag}</td>
            {delta_cell(r['sp_d'], 1.0)}
            <td>{tot_open_str}</td>
            <td><b>{tot_now_str}</b>{t_flag}</td>
            {delta_cell(r['t_d'], 2.0)}
            <td class='it-away'>{away_it_str}</td>
            <td class='it-home'>{home_it_str}</td>
            {reason_cell}
            {updated_cell}
            <td class='snaps'>{r.get('n_chart_points', r['n_snaps'])}</td>
        </tr>
        <tr id='desktop-panel-{game_key}' class='chart-detail-row' data-slate='{r["slate_window"]}' data-game-panel='{game_key}' hidden>
            <td colspan='12'>
                <div class='chart-detail-shell'>
                    <div class='chart-detail-heading'>
                        <div><span class='eyebrow'>{r['slate_label']}</span><h2>{r['away']} @ {r['home']}</h2></div>
                        <span class='pull-note'><span class='pull-dot'></span> Every dot is a valid completed pull</span>
                    </div>
                    {detail_stats}
                    {chart_html}
                    <p class='movement-note'>{safe_reason or 'No movement from the tracker baseline.'}</p>
                </div>
            </td>
        </tr>""")

        movement_summary = safe_reason or "No movement from baseline"
        mobile_cards.append(f"""
        <article class='mobile-game-card {row_cls}' data-slate='{r["slate_window"]}' data-game='{game_key}'>
            <button class='mobile-game-summary' type='button' data-toggle-game='{game_key}' aria-expanded='false' aria-controls='mobile-panel-{game_key}'>
                <span class='mobile-game-main'>
                    <span class='mobile-slate'>{r['slate_label']}</span>
                    <strong>{r['away']} @ {r['home']}</strong>
                    <span>{movement_summary}</span>
                </span>
                <span class='mobile-current'>
                    <strong>{r['sp_fav_now']}</strong>
                    <strong>O/U {tot_now_str}</strong>
                    <span class='chevron'>⌄</span>
                </span>
            </button>
            <div id='mobile-panel-{game_key}' class='mobile-detail' data-game-panel='{game_key}' hidden>
                {detail_stats}
                {chart_html}
                <p class='pull-note'><span class='pull-dot'></span> Every dot is a valid completed pull · {r.get('n_chart_points', r['n_snaps'])} chart dots</p>
            </div>
        </article>""".strip())

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NFL Lines — DraftKings Tracker</title>
<meta http-equiv='refresh' content='1800'>
<meta http-equiv='cache-control' content='no-cache, no-store, must-revalidate'>
<meta http-equiv='pragma' content='no-cache'>
<meta http-equiv='expires' content='0'>
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
  .reason {{ color: #E0E2EC; font-size: 11.5px; max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
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

  /* Slate Window Separator */
  .slate-sep-row {{
    background: #0d0f19;
  }}
  .slate-sep-cell {{
    padding: 12px 14px 8px 14px !important;
    text-align: center;
    border-top: 1px solid #23273B;
    border-bottom: 1px solid #1A1D2D;
  }}
  .sep-dash {{
    color: #383D56;
    letter-spacing: 2px;
    font-size: 11px;
  }}
  .sep-label {{
    color: #8D92AA;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 1.2px;
    margin: 0 8px;
    text-transform: uppercase;
  }}

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
  .alert-banner.warning {{
    background: rgba(255, 170, 0, 0.12);
    border: 1px solid rgba(255, 170, 0, 0.4);
    color: #FFB300;
  }}
  .alert-banner.stale {{
    background: rgba(255, 68, 68, 0.15);
    border: 1px solid rgba(255, 68, 68, 0.5);
    color: #FF7070;
    font-size: 13px;
    animation: pulse 2s infinite;
  }}
  .pill-fresh {{
    background: rgba(34, 184, 160, 0.15);
    color: #4FE1C8;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    display: inline-block;
  }}
  .pill-stale {{
    background: rgba(255, 170, 0, 0.18);
    color: #FFB300;
    border: 1px solid rgba(255, 170, 0, 0.4);
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    display: inline-block;
  }}
  .pill-closed {{
    background: rgba(139, 146, 169, 0.14);
    color: #B6BCCF;
    border: 1px solid rgba(139, 146, 169, 0.3);
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 650;
    display: inline-block;
    white-space: nowrap;
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

  /* Dashboard shell and clearer hierarchy */
  body {{
    min-height: 100vh;
    background:
      radial-gradient(circle at 15% 0%, rgba(0, 229, 255, 0.07), transparent 34%),
      radial-gradient(circle at 90% 8%, rgba(255, 179, 0, 0.06), transparent 30%),
      {BG_PAGE};
  }}
  .app-shell {{ max-width: 1880px; margin: 0 auto; }}
  .page-header {{ margin-bottom: 18px; }}
  .title-row {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; }}
  .title-kicker {{ color: {TEAL_BRIGHT}; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase; }}
  h1 {{ font-size: clamp(24px, 2.4vw, 36px); letter-spacing: -0.7px; }}
  .sub {{ color: #A3A9BE; font-size: 13px; margin: 8px 0 10px; }}
  .legend-box {{ margin-left: 0; margin-top: 8px; }}
  details.about {{ color: #979DB2; font-size: 12px; max-width: 880px; }}
  details.about summary {{ cursor: pointer; color: #C9CDDA; font-weight: 650; width: fit-content; }}
  details.about p {{ padding-top: 8px; line-height: 1.65; }}

  .filter-bar {{
    display: flex;
    gap: 8px;
    align-items: center;
    overflow-x: auto;
    padding: 2px 0 14px;
    scrollbar-width: thin;
  }}
  .filter-bar::-webkit-scrollbar {{ display: none; }}
  .filter-button {{
    appearance: none;
    border: 1px solid #2A2E41;
    background: #151722;
    color: #AEB4C8;
    border-radius: 999px;
    padding: 7px 12px;
    font: inherit;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
    cursor: pointer;
    transition: 140ms ease;
  }}
  .filter-button:hover {{ border-color: #4B526D; color: #FFFFFF; }}
  .filter-button.active {{ background: rgba(0, 229, 255, 0.13); border-color: rgba(0, 229, 255, 0.55); color: #84F2FF; }}

  .desktop-board {{ display: block; }}
  .mobile-board {{ display: none; }}
  .table-wrap {{ overflow-x: auto; border: 1px solid #1F2332; border-radius: 12px; box-shadow: 0 16px 38px rgba(0,0,0,.22); }}
  .table-wrap table {{ min-width: 1220px; margin-bottom: 0; border-radius: 0; }}
  thead th {{ position: sticky; top: 0; z-index: 6; background: #151722; color: #959CB3; }}
  td {{ color: #A8AEC2; }}
  .game-row {{ cursor: pointer; transition: background 140ms ease, box-shadow 140ms ease; }}
  .game-row:hover td {{ background: #191C29; }}
  .game-row:focus-visible {{ outline: 2px solid {TEAL_BRIGHT}; outline-offset: -2px; }}
  .game-row[aria-expanded='true'] td {{ background: #1B1E2C; border-bottom-color: transparent; }}
  .game-row.closed-game td {{ background: rgba(125, 132, 154, 0.035); }}
  .game-row.closed-game .view-chart {{ color: #ADB4C8; }}
  .game-row[aria-expanded='true'] .chevron,
  .mobile-game-summary[aria-expanded='true'] .chevron {{ transform: rotate(180deg); }}
  .view-chart {{ display: block; margin-top: 3px; color: #7FEFFF; font-size: 9px; font-weight: 750; letter-spacing: .3px; }}
  .chevron {{ display: inline-block; transition: transform 160ms ease; }}
  tr.thu td {{ opacity: 1; }}
  tr.thu .mu {{ border-left: 3px solid #7A8099; }}
  .movement-badge {{ display: inline-flex; min-width: 30px; justify-content: center; padding: 2px 6px; border-radius: 999px; background: #24283A; color: #BFC5D8; }}
  .movement-badge.significant {{ background: rgba(135, 111, 255, .18); color: #C8BBFF; border: 1px solid rgba(135, 111, 255, .4); }}

  .chart-detail-row td {{ padding: 0; background: #10121B; }}
  .chart-detail-shell {{ padding: 22px; border-top: 1px solid rgba(0,229,255,.28); border-bottom: 1px solid #252A3C; }}
  .chart-detail-heading {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 14px; }}
  .chart-detail-heading h2 {{ color: #F6F7FB; font-size: 20px; }}
  .eyebrow {{ color: #7E859D; font-size: 9px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; }}
  .pull-note {{ color: #AAB0C3; font-size: 11px; }}
  .pull-dot {{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: {TEAL_BRIGHT}; box-shadow: 0 0 8px rgba(0,229,255,.75); margin-right: 5px; }}
  .detail-stats {{ display: grid; grid-template-columns: repeat(8, minmax(105px, 1fr)); gap: 8px; margin-bottom: 14px; }}
  .detail-stats > div {{ background: #181B28; border: 1px solid #24283A; border-radius: 8px; padding: 9px 10px; }}
  .detail-stats span {{ display: block; color: #7F869E; font-size: 9px; text-transform: uppercase; letter-spacing: .5px; }}
  .detail-stats strong {{ display: block; color: #F0F2F8; font-size: 12px; margin-top: 3px; }}
  .expanded-chart {{ display: block; width: min(1180px, 100%); height: auto; margin: 0 auto; border-radius: 10px; border: 1px solid #24283A; background: {BG_CHART}; }}
  .movement-note {{ color: #B4BACD; font-size: 12px; text-align: center; padding-top: 10px; }}
  .chart-unavailable {{ color: #8A90A6; padding: 30px; text-align: center; }}

  @media (max-width: 900px) {{
    body {{ padding: 14px; }}
    .filter-bar {{ scrollbar-width: none; }}
    .desktop-board {{ display: none; }}
    .mobile-board {{ display: grid; gap: 10px; }}
    .title-row {{ align-items: flex-start; }}
    .alert-banner {{ display: block; line-height: 1.55; }}
    .alert-banner .status-dot, .alert-banner .alert-icon {{ margin-right: 6px; }}
    .mobile-game-card {{ background: #141620; border: 1px solid #24283A; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,.18); }}
    .mobile-game-card.thu {{ border-left: 3px solid #7A8099; }}
    .mobile-game-card.closed-game {{ border-color: #3A3F52; }}
    .mobile-game-summary {{ width: 100%; display: flex; justify-content: space-between; gap: 14px; align-items: center; padding: 14px; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }}
    .mobile-game-main {{ display: grid; gap: 3px; min-width: 0; }}
    .mobile-game-main strong {{ color: #F3F5FA; font-size: 16px; }}
    .mobile-game-main > span:last-child {{ color: #9DA4B9; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 220px; }}
    .mobile-slate {{ color: #737B95; font-size: 8px; font-weight: 800; letter-spacing: .9px; text-transform: uppercase; }}
    .mobile-current {{ display: grid; gap: 3px; justify-items: end; flex: 0 0 auto; }}
    .mobile-current strong {{ color: #E8EBF4; font-size: 12px; }}
    .mobile-current .chevron {{ color: {TEAL_BRIGHT}; font-size: 16px; }}
    .mobile-detail {{ border-top: 1px solid #262B3E; padding: 12px; background: #10121B; }}
    .detail-stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .expanded-chart {{ width: 100%; }}
    .mobile-detail .pull-note {{ display: block; padding: 10px 2px 2px; text-align: center; }}
    .legend-box {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  }}

  @media (max-width: 480px) {{
    body {{ padding: 11px; }}
    h1 {{ font-size: 25px; line-height: 1.08; }}
    .sub {{ font-size: 12px; }}
    .alert-banner {{ font-size: 11.5px; padding: 10px 12px; }}
    .filter-bar {{ margin-right: -11px; padding-right: 11px; }}
    .mobile-game-main > span:last-child {{ max-width: 190px; }}
  }}
</style>
</head>
<body>
<main class='app-shell'>
  <header class='page-header'>
    <div class='title-row'>
      <div>
        <span class='title-kicker'>Live market board</span>
        <h1>NFL Line Movement</h1>
      </div>
    </div>
    <p class='sub'>
      DraftKings main lines &middot; Pinnacle cross-check &middot; Updated by the local Mac tracker<br>
      Page rendered {now_ct_str} &middot; {total_chart_points} valid chart dots &middot; {total_snaps} total pull attempts
      <span class='legend-box'>
        <span class='dot-teal'>● Away implied total</span>
        <span class='dot-amber'>● Home implied total</span>
        <span><span class='pull-dot'></span>Every dot = one valid completed pull</span>
      </span>
    </p>
    <details class='about'>
      <summary>About this tracker</summary>
      <p>Lines are pinned to DraftKings and checked against Pinnacle. An asterisk marks a 1+ point divergence. The baseline is the earliest capture retained for the active week. Normal cadence is every three hours, with faster Sunday and Monday-night kickoff coverage.</p>
    </details>
  </header>

  {status_banner}

  <nav class='filter-bar' aria-label='Filter games by slate'>
    <button class='filter-button active' type='button' data-filter='ALL'>All games</button>
    <button class='filter-button' type='button' data-filter='TNF'>TNF</button>
    <button class='filter-button' type='button' data-filter='OTHER_PRIMETIME'>Special</button>
    <button class='filter-button' type='button' data-filter='SUN_EARLY'>Sunday early</button>
    <button class='filter-button' type='button' data-filter='SUN_LATE'>Sunday late</button>
    <button class='filter-button' type='button' data-filter='SNF'>SNF</button>
    <button class='filter-button' type='button' data-filter='MNF'>MNF</button>
  </nav>

  <section class='desktop-board' aria-label='NFL line movement table'>
    <div class='table-wrap'>
      <table>
      <thead>
      <tr>
        <th>Matchup</th>
        <th title="Earliest spread captured this week">Opening</th>
        <th>Current</th>
        <th>Move</th>
        <th title="Earliest total captured this week">Opening O/U</th>
        <th>Current O/U</th>
        <th>Move</th>
        <th>Away IT</th>
        <th>Home IT</th>
        <th>Movement</th>
        <th style="text-align: center;" title="Timestamp of the latest completed pull">Last pull</th>
        <th style="text-align: center;">Chart dots</th>
      </tr>
      </thead>
      <tbody>
      {''.join(table_rows)}
      </tbody>
      </table>
    </div>
  </section>

  <section class='mobile-board' aria-label='NFL games'>
    {''.join(mobile_cards)}
  </section>
</main>

<script>
function closeAllGamePanels() {{
  document.querySelectorAll('[data-game-panel]').forEach(panel => panel.hidden = true);
  document.querySelectorAll('[data-toggle-game]').forEach(toggle => toggle.setAttribute('aria-expanded', 'false'));
}}

function toggleGame(gameKey) {{
  const toggles = Array.from(document.querySelectorAll('[data-toggle-game="' + gameKey + '"]'));
  const panels = Array.from(document.querySelectorAll('[data-game-panel="' + gameKey + '"]'));
  const shouldOpen = !toggles.some(toggle => toggle.getAttribute('aria-expanded') === 'true');
  closeAllGamePanels();
  if (shouldOpen) {{
    toggles.forEach(toggle => toggle.setAttribute('aria-expanded', 'true'));
    panels.forEach(panel => panel.hidden = false);
  }}
}}

document.querySelectorAll('[data-toggle-game]').forEach(toggle => {{
  toggle.addEventListener('click', () => toggleGame(toggle.dataset.toggleGame));
  if (toggle.tagName !== 'BUTTON') {{
    toggle.addEventListener('keydown', event => {{
      if (event.key === 'Enter' || event.key === ' ') {{
        event.preventDefault();
        toggleGame(toggle.dataset.toggleGame);
      }}
    }});
  }}
}});

function applySlateFilter(slate) {{
  closeAllGamePanels();
  document.querySelectorAll('.game-row').forEach(row => {{
    row.hidden = slate !== 'ALL' && row.dataset.slate !== slate;
  }});
  document.querySelectorAll('.mobile-game-card').forEach(card => {{
    card.hidden = slate !== 'ALL' && card.dataset.slate !== slate;
  }});
  document.querySelectorAll('.slate-sep-row').forEach(separator => {{
    const hasVisibleGame = Array.from(document.querySelectorAll('.game-row[data-slate="' + separator.dataset.slate + '"]')).some(row => !row.hidden);
    separator.hidden = !hasVisibleGame;
  }});
  document.querySelectorAll('.filter-button').forEach(button => {{
    button.classList.toggle('active', button.dataset.filter === slate);
  }});
}}

document.querySelectorAll('.filter-button').forEach(button => {{
  button.addEventListener('click', () => applySlateFilter(button.dataset.filter));
}});

function updateDynamicFeedAge() {{
  const banner = document.getElementById('feed-banner');
  if (!banner) return;
  const tsStr = banner.getAttribute('data-feed-ts');
  if (!tsStr) return;
  const feedDate = new Date(tsStr);
  if (isNaN(feedDate.getTime())) return;
  const now = new Date();
  const diffMs = Math.max(0, now - feedDate);
  const diffSec = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSec / 60);
  const diffHours = diffMs / (1000 * 60 * 60);

  const ageSpan = document.getElementById('feed-age-dynamic');
  if (ageSpan) {{
    if (diffSec < 60) {{
      ageSpan.textContent = 'just now (' + diffSec + 's ago)';
    }} else if (diffMins < 60) {{
      ageSpan.textContent = diffMins + 'm ago';
    }} else {{
      const hrs = Math.floor(diffMins / 60);
      const remMins = diffMins % 60;
      ageSpan.textContent = hrs + 'h ' + remMins + 'm ago (' + diffHours.toFixed(1) + ' hrs)';
    }}
  }}
  const isSunday = (now.getDay() === 0);
  const staleLimit = isSunday ? 1.5 : 4.0;
  const bannerKind = banner.getAttribute('data-banner-kind') || 'healthy';
  if (diffHours >= staleLimit && bannerKind === 'healthy') {{
    if (!banner.classList.contains('stale')) {{
      banner.className = 'alert-banner stale';
    }}
    const hrsDisplay = (Math.floor(diffHours * 10) / 10).toFixed(1);
    banner.innerHTML = "<span class='alert-icon'>\u26a0\ufe0f</span> <b>Feed Stale \u2014 No Update in " + hrsDisplay + " hrs.</b> Last pull: <span id='feed-time'>" + (banner.getAttribute('data-feed-ts-label') || '') + "</span>. Check the local runner log for details.";
  }}
}}
updateDynamicFeedAge();
setInterval(updateDynamicFeedAge, 5000);
</script>
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

    # Extract latest snapshot timestamp across all games
    latest_ts = None
    for snaps in games.values():
        if snaps:
            ts = snaps[-1].get("ts")
            if ts and (latest_ts is None or ts > latest_ts):
                latest_ts = ts

    board_rows = build_board_rows(games, latest_ts=latest_ts)

    generate_html(chart_files, board_rows, CHART_DIR, latest_ts=latest_ts)
    print(f"\nGenerated {len(chart_files)} charts -> {CHART_DIR}/index.html")


if __name__ == "__main__":
    main()
