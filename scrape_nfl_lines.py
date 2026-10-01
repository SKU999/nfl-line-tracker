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
import sys
import time
from datetime import datetime, timezone

# Use curl_cffi to impersonate real browser TLS fingerprint and bypass Cloudflare bot challenge
try:
    from curl_cffi import requests
    print("[INIT] curl_cffi successfully loaded.")

    _session = None

    def get_session():
        global _session
        if _session is None:
            _session = requests.Session(impersonate="chrome124")
            _session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://4codds.com/",
                "Origin": "https://4codds.com",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            })
        return _session

    def _req(url, retries=4):
        global _session
        last_err = "Unknown error"
        for attempt in range(retries):
            sess = get_session()
            try:
                resp = sess.get(url, timeout=25)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 429:
                    last_err = "HTTP 429 Rate Limit"
                    wait_sec = 2.5 * (attempt + 1)
                    print(f"[WARN] HTTP 429 Rate Limit on {url}, backing off {wait_sec:.1f}s...")
                    time.sleep(wait_sec)
                else:
                    last_err = f"HTTP {resp.status_code}"
                    print(f"[WARN] HTTP {resp.status_code} (attempt {attempt+1}) on {url}: {resp.text[:100]}")
            except Exception as e:
                last_err = str(e)
                print(f"[WARN] Request error (attempt {attempt+1}) on {url}: {e}")
                # Reset session on connection error to get fresh socket
                _session = None
            time.sleep(0.75 * (2 ** attempt))
        raise Exception(f"Failed to fetch {url} ({last_err}) after {retries} retries.")
except ImportError as err:
    print(f"[INIT] curl_cffi import failed: {err}, falling back to urllib.")
    import urllib.request
    def _req(url):
        r = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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

STATUS_FILE = os.path.join(DATA_DIR, "scraper_status.json")

PRIMARY = "DRAFTKINGS"
SHARP = "PINNACLE"


def find_book_main_line(lines_dict, consensus, side_a, side_b, book, current_line=None):
    """
    Find the book's main line:
    1. Collect all lines offered by the book.
    2. If consensus is known, filter to lines within 1.0 point of consensus.
       If none within 1.0 point, search all available lines.
    3. Among these candidate lines, pick the line whose side_a and side_b prices
       are closest to even (-110 / -110). Lines with both sides posted are prioritized.
    """
    candidates = []
    for lv_str, sides in lines_dict.items():
        try:
            lv = float(lv_str)
        except (ValueError, TypeError):
            continue
        odds_a = None
        for entry in sides.get(side_a, []):
            if entry[0] == book:
                odds_a = entry[1]
                break
        odds_b = None
        for entry in sides.get(side_b, []):
            if entry[0] == book:
                odds_b = entry[1]
                break
        if odds_a is not None or odds_b is not None:
            candidates.append((lv, odds_a, odds_b))

    if not candidates:
        return None, None, None

    pool = candidates
    if consensus is not None:
        near = [c for c in candidates if abs(c[0] - consensus) <= 1.0 + 1e-4]
        if near:
            pool = near

    def score_line(c):
        lv, a, b = c
        if a is not None and b is not None:
            diff = abs(abs(a) - 110) + abs(abs(b) - 110)
            dist_cons = abs(lv - consensus) if consensus is not None else 0
            return (0, diff, dist_cons)
        else:
            val = a if a is not None else b
            dist_cons = abs(lv - consensus) if consensus is not None else 0
            return (1, abs(abs(val) - 110), dist_cons)

    best = min(pool, key=score_line)

    # Hysteresis: If current_line was previously recorded and is still available in the candidate pool,
    # only switch to a new line if the new line is CLEARLY more balanced (vig diff at least 8 cents lower).
    # This prevents artificial half-point flip-flops on negligible juice wiggles.
    if current_line is not None:
        curr_cand = next((c for c in pool if abs(c[0] - current_line) < 1e-4), None)
        if curr_cand is not None:
            curr_score = score_line(curr_cand)
            best_score = score_line(best)
            if curr_score[0] == 0 and best_score[0] == 0:
                if best_score[1] >= curr_score[1] - 8:
                    return curr_cand[0], curr_cand[1], curr_cand[2]

    return best[0], best[1], best[2]


def process_game(game, prev_snap=None):
    gid = game["id"]
    consensus = game.get("main", {})
    prev_dk_sp = prev_snap.get("dk_spread") if prev_snap else None
    prev_dk_tot = prev_snap.get("dk_total") if prev_snap else None
    prev_pin_sp = prev_snap.get("pin_spread") if prev_snap else None
    prev_pin_tot = prev_snap.get("pin_total") if prev_snap else None

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

        lv, ho, ao = find_book_main_line(lines, consensus.get("sp"), "home", "away", PRIMARY, current_line=prev_dk_sp)
        snap["dk_spread"] = lv
        snap["dk_sp_home_odds"] = ho
        snap["dk_sp_away_odds"] = ao

        lv2, ho2, ao2 = find_book_main_line(lines, consensus.get("sp"), "home", "away", SHARP, current_line=prev_pin_sp)
        snap["pin_spread"] = lv2
        snap["pin_sp_home_odds"] = ho2
        snap["pin_sp_away_odds"] = ao2
    except Exception as e:
        snap["sp_error"] = str(e)
        print(f"[ERROR] Failed to fetch SP for {gid} ({snap.get('away')}@{snap.get('home')}): {e}")

    time.sleep(0.35)

    # Total
    try:
        tot = _req(GAME_MKT_URL.format(gid=gid, mkt="tot"))
        lines = tot.get("lines", {})

        lv, ov, un = find_book_main_line(lines, consensus.get("tot"), "over", "under", PRIMARY, current_line=prev_dk_tot)
        snap["dk_total"] = lv
        snap["dk_tot_over"] = ov
        snap["dk_tot_under"] = un

        lv2, ov2, un2 = find_book_main_line(lines, consensus.get("tot"), "over", "under", SHARP, current_line=prev_pin_tot)
        snap["pin_total"] = lv2
        snap["pin_tot_over"] = ov2
        snap["pin_tot_under"] = un2
    except Exception as e:
        snap["tot_error"] = str(e)
        print(f"[ERROR] Failed to fetch TOT for {gid} ({snap.get('away')}@{snap.get('home')}): {e}")

    # Implied Team Totals
    dk_sp = snap.get("dk_spread")
    dk_tot = snap.get("dk_total")
    if dk_sp is not None and dk_tot is not None:
        snap["home_impl"] = round((dk_tot - dk_sp) / 2, 2)
        snap["away_impl"] = round((dk_tot + dk_sp) / 2, 2)

    return snap


def load_latest_snapshots():
    latest = {}
    if not os.path.exists(DATA_FILE):
        return latest
    try:
        with open(DATA_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                s = json.loads(line)
                mu = f"{s.get('away')}@{s.get('home')}"
                latest[mu] = s
    except Exception as e:
        print(f"[WARN] Error reading existing snapshots for dedup: {e}")
    return latest


def is_duplicate_snapshot(curr, prev):
    if not prev:
        return False
    try:
        t1 = datetime.fromisoformat(prev["ts"].replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(curr["ts"].replace("Z", "+00:00"))
        diff_min = abs((t2 - t1).total_seconds()) / 60.0
    except Exception:
        diff_min = 999.0

    lines_identical = (
        curr.get("dk_spread") == prev.get("dk_spread") and
        curr.get("dk_total") == prev.get("dk_total") and
        curr.get("pin_spread") == prev.get("pin_spread") and
        curr.get("pin_total") == prev.get("pin_total")
    )
    # If lines haven't moved and less than 75 minutes have elapsed, it's a redundant duplicate run
    return lines_identical and (diff_min < 75.0)


def save_snapshots(snapshots):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    latest_by_game = load_latest_snapshots()
    to_save = []
    skipped = 0

    for snap in snapshots:
        mu = f"{snap.get('away')}@{snap.get('home')}"
        prev = latest_by_game.get(mu)
        if is_duplicate_snapshot(snap, prev):
            skipped += 1
            continue
        to_save.append(snap)
        latest_by_game[mu] = snap

    if to_save:
        # 1. Active working file
        with open(DATA_FILE, "a") as f:
            for snap in to_save:
                f.write(json.dumps(snap) + "\n")

        # 2. Immutable Perpetual Raw Archive
        with open(PERPETUAL_FILE, "a") as f:
            for snap in to_save:
                f.write(json.dumps(snap) + "\n")

    print(f"[STORAGE] Saved {len(to_save)} new/changed snapshots ({skipped} duplicate/unchanged within 75m suppressed).")


def write_status(success, error=None, games_count=0, valid_games_count=0, invalid_games=None):
    """Write run status to data/scraper_status.json for dashboard visibility."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "error": error,
            "games_count": games_count,
            "valid_games_count": valid_games_count,
            "invalid_games": invalid_games or [],
        }
        with open(STATUS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to write status file: {e}")


def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Mark in-progress/provisional status
    write_status(False, error="Scrape in progress or interrupted", games_count=0)
    try:
        board = _req(BOARD_URL)
        games = [g for g in board.get("games", []) if g.get("league") == "NFL"]
        print(f"[{ts}] Processing {len(games)} NFL games for perpetual archive...")

        latest_by_game = load_latest_snapshots()
        snaps = []
        for g in games:
            mu = f"{g['away']['short']}@{g['home']['short']}"
            prev_snap = latest_by_game.get(mu)
            try:
                s = process_game(g, prev_snap=prev_snap)
                snaps.append(s)
            except Exception as ge:
                print(f"[WARN] Error processing game {g.get('id')}: {ge}")
            time.sleep(0.4)

        if snaps:
            save_snapshots(snaps)
            print(f"[{ts}] Saved {len(snaps)} snapshots to active database and perpetual archive.")
            invalid_games = [
                f"{s.get('away')}@{s.get('home')}"
                for s in snaps
                if s.get("dk_spread") is None or s.get("dk_total") is None
            ]
            valid_games_count = len(snaps) - len(invalid_games)
            if invalid_games:
                msg = (
                    f"Missing complete DraftKings market for {len(invalid_games)} of "
                    f"{len(snaps)} games: {', '.join(invalid_games)}"
                )
                print(f"[{ts}] [DEGRADED] {msg}")
                write_status(
                    False,
                    error=msg,
                    games_count=len(snaps),
                    valid_games_count=valid_games_count,
                    invalid_games=invalid_games,
                )
                sys.exit(1)
            write_status(
                True,
                error=None,
                games_count=len(snaps),
                valid_games_count=valid_games_count,
                invalid_games=[],
            )
        else:
            msg = "No games collected from board"
            print(f"[{ts}] {msg}")
            write_status(False, error=msg, games_count=0)
            sys.exit(1)
    except Exception as e:
        print(f"[{ts}] [CRITICAL] Scraper failed: {e}")
        write_status(False, error=str(e), games_count=0)
        sys.exit(1)


if __name__ == "__main__":
    main()
