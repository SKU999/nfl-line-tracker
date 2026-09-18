#!/usr/bin/env python3
"""
NFL Line Tracker — Scraper (v6 Perpetual Archive)
1. Pinned to DraftKings (with Pinnacle sharp check).
2. Perpetual Ledger: EVERY scrape is permanently appended to:
     - data/nfl_lines.jsonl (active rolling view)
     - data/archive/nfl_lines_perpetual_raw.jsonl (PERPETUAL IMMUTABLE ARCHIVE)
   Never wiped, never truncated. Stores raw book lines, consensus, and calculated totals.
"""

import json
import os
import time
from datetime import datetime, timezone

# Use curl_cffi to impersonate real browser TLS fingerprint and bypass Cloudflare bot challenge
try:
    from curl_cffi import requests
    _session = requests.Session(impersonate="chrome124")
    def _req(url):
        resp = _session.get(
            url,
            timeout=25,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.json()
except ImportError:
    import urllib.request
    def _req(url):
        r = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(r, timeout=20) as resp:
            return json.loads(resp.read().decode())


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "nfl_lines.jsonl")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
PERPETUAL_FILE = os.path.join(ARCHIVE_DIR, "nfl_lines_perpetual_raw.jsonl")

BOARD_URL = "https://4codds.com/api/v2/board/football"
GAME_MKT_URL = "https://4codds.com/api/v2/game/{gid}/market/{mkt}"

EXCLUDE_BOOKS = {
    "NOVIG", "KALSHI", "POLYMARKET", "POLYMARKETUS",
    "PREDICTFUN", "PROPHETX", "REBET",
}

PRIMARY = "DRAFTKINGS"
SHARP = "PINNACLE"


def find_book_at_line(lines_dict, line_val, side, book):
    key = str(line_val)
    for k in [key, key.rstrip("0").rstrip("."), key + ".0"]:
        if k in lines_dict:
            for entry in lines_dict[k].get(side, []):
                if entry[0] == book:
                    return float(k) if "." in k else int(k), entry[1]
    return None, None


def find_book_main_line(lines_dict, consensus, side_a, side_b, book):
    if consensus is not None:
        for offset in [0, 0.5, -0.5, 1, -1]:
            candidate = consensus + offset
            _, odds_a = find_book_at_line(lines_dict, candidate, side_a, book)
            _, odds_b = find_book_at_line(lines_dict, candidate, side_b, book)
            if odds_a is not None or odds_b is not None:
                return candidate, odds_a, odds_b

    best = (None, None, None, 999)
    for lv_str, sides in lines_dict.items():
        odds_a = odds_b = None
        for entry in sides.get(side_a, []):
            if entry[0] == book:
                odds_a = entry[1]
                break
        for entry in sides.get(side_b, []):
            if entry[0] == book:
                odds_b = entry[1]
                break
        if odds_a is not None and odds_b is not None:
            vig = abs(abs(odds_a) - 110) + abs(abs(odds_b) - 110)
            try:
                lv = float(lv_str)
            except:
                continue
            if vig < best[3]:
                best = (lv, odds_a, odds_b, vig)

    if best[0] is not None:
        return best[0], best[1], best[2]
    return None, None, None


def process_game(game):
    gid = game["id"]
    consensus = game.get("main", {})
    snap = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "game_id": gid,
        "away": game["away"]["short"],
        "home": game["home"]["short"],
        "away_full": game["away"]["name"],
        "home_full": game["home"]["name"],
        "start": game.get("start", ""),
        "consensus_sp": consensus.get("sp"),
        "consensus_tot": consensus.get("tot"),
    }

    # Spread
    try:
        sp = _req(GAME_MKT_URL.format(gid=gid, mkt="sp"))
        lines = sp.get("lines", {})

        lv, ho, ao = find_book_main_line(lines, consensus.get("sp"), "home", "away", PRIMARY)
        snap["dk_spread"] = lv
        snap["dk_sp_home_odds"] = ho
        snap["dk_sp_away_odds"] = ao

        lv2, ho2, ao2 = find_book_main_line(lines, consensus.get("sp"), "home", "away", SHARP)
        snap["pin_spread"] = lv2
        snap["pin_sp_home_odds"] = ho2
        snap["pin_sp_away_odds"] = ao2
    except Exception as e:
        snap["sp_error"] = str(e)

    time.sleep(0.12)

    # Total
    try:
        tot = _req(GAME_MKT_URL.format(gid=gid, mkt="tot"))
        lines = tot.get("lines", {})

        lv, ov, un = find_book_main_line(lines, consensus.get("tot"), "over", "under", PRIMARY)
        snap["dk_total"] = lv
        snap["dk_tot_over"] = ov
        snap["dk_tot_under"] = un

        lv2, ov2, un2 = find_book_main_line(lines, consensus.get("tot"), "over", "under", SHARP)
        snap["pin_total"] = lv2
        snap["pin_tot_over"] = ov2
        snap["pin_tot_under"] = un2
    except Exception as e:
        snap["tot_error"] = str(e)

    # Implied Team Totals
    dk_sp = snap.get("dk_spread")
    dk_tot = snap.get("dk_total")
    if dk_sp is not None and dk_tot is not None:
        snap["home_impl"] = round((dk_tot - dk_sp) / 2, 2)
        snap["away_impl"] = round((dk_tot + dk_sp) / 2, 2)

    return snap


def save_snapshots(snapshots):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 1. Active working file
    with open(DATA_FILE, "a") as f:
        for snap in snapshots:
            f.write(json.dumps(snap) + "\n")

    # 2. Immutable Perpetual Raw Archive (Kept forever for historical backtesting)
    with open(PERPETUAL_FILE, "a") as f:
        for snap in snapshots:
            f.write(json.dumps(snap) + "\n")


def main():
    board = _req(BOARD_URL)
    games = [g for g in board.get("games", []) if g.get("league") == "NFL"]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Processing {len(games)} NFL games for perpetual archive...")

    snaps = []
    for g in games:
        s = process_game(g)
        snaps.append(s)
        time.sleep(0.12)

    save_snapshots(snaps)
    print(f"[{ts}] Saved {len(snaps)} snapshots to active database and perpetual archive.")


if __name__ == "__main__":
    main()
