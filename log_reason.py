#!/usr/bin/env python3
"""
NFL Line Movement Alert & Reason Logger
Tracks lines that move >= 1.0 point (spread or total).
Appends alerts to data/movement_alerts.jsonl and maintains a human-readable
reasons file data/movement_reasons.json that feeds directly into the dashboard.

Usage:
  python3 log_reason.py "DEN @ JAX" "Bo Nix shoulder injury reported at practice"
  python3 log_reason.py --list
"""

import json
import os
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ALERTS_FILE = os.path.join(DATA_DIR, "movement_alerts.jsonl")
REASONS_FILE = os.path.join(DATA_DIR, "movement_reasons.json")


def load_reasons():
    if os.path.exists(REASONS_FILE):
        try:
            with open(REASONS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_reasons(reasons):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REASONS_FILE, "w") as f:
        json.dump(reasons, f, indent=2)


def add_manual_reason(matchup_key, note):
    """Add or update a reason note for a matchup."""
    reasons = load_reasons()
    ts = datetime.now(timezone.utc).isoformat()
    clean_key = matchup_key.strip().upper().replace("VS", "@")
    
    if clean_key not in reasons:
        reasons[clean_key] = []
    
    entry = {
        "ts": ts,
        "note": note.strip()
    }
    reasons[clean_key].append(entry)
    save_reasons(reasons)
    print(f"Logged reason for {clean_key}: \"{note}\"")


def check_and_record_alerts(snapshots_by_game):
    """
    Called by plot_nfl_lines.py after each scrape:
    Detects any game where spread or total moved >= 1.0 point from baseline.
    Logs an alert record to ALERTS_FILE if not already recorded for that delta.
    """
    reasons = load_reasons()
    os.makedirs(DATA_DIR, exist_ok=True)

    existing_alert_keys = set()
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r") as f:
            for l in f:
                try:
                    a = json.loads(l)
                    existing_alert_keys.add((a["matchup"], a["type"], a["now_val"]))
                except:
                    pass

    new_alerts = []
    for gid, snaps in snapshots_by_game.items():
        if len(snaps) < 2:
            continue
        first, last = snaps[0], snaps[-1]
        away = last.get("away", "?")
        home = last.get("home", "?")
        matchup = f"{away} @ {home}"

        # Check Spread
        sp0, sp1 = first.get("dk_spread"), last.get("dk_spread")
        if sp0 is not None and sp1 is not None and abs(sp1 - sp0) >= 1.0:
            key = (matchup, "spread", sp1)
            if key not in existing_alert_keys:
                delta = sp1 - sp0
                alert = {
                    "ts": last.get("ts"),
                    "matchup": matchup,
                    "type": "spread",
                    "base_val": sp0,
                    "now_val": sp1,
                    "delta": round(delta, 1),
                    "summary": f"Spread moved {delta:+.1f} (from {home} {sp0:+.1f} to {home} {sp1:+.1f})"
                }
                new_alerts.append(alert)

        # Check Total
        t0, t1 = first.get("dk_total"), last.get("dk_total")
        if t0 is not None and t1 is not None and abs(t1 - t0) >= 1.0:
            key = (matchup, "total", t1)
            if key not in existing_alert_keys:
                delta = t1 - t0
                alert = {
                    "ts": last.get("ts"),
                    "matchup": matchup,
                    "type": "total",
                    "base_val": t0,
                    "now_val": t1,
                    "delta": round(delta, 1),
                    "summary": f"Total moved {delta:+.1f} (from {t0:.1f} to {t1:.1f})"
                }
                new_alerts.append(alert)

    if new_alerts:
        with open(ALERTS_FILE, "a") as f:
            for a in new_alerts:
                f.write(json.dumps(a) + "\n")
        print(f"Recorded {len(new_alerts)} significant line movement alerts (>= 1.0 pt)")

    return new_alerts


def list_reasons():
    reasons = load_reasons()
    if not reasons:
        print("No movement reasons logged yet.")
        return
    print("\n--- Logged Movement Reasons ---")
    for m, notes in reasons.items():
        print(f"\n{m}:")
        for n in notes:
            print(f"  [{n['ts'][:16]}] {n['note']}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(__doc__)
    elif sys.argv[1] == "--list":
        list_reasons()
    elif len(sys.argv) >= 3:
        add_manual_reason(sys.argv[1], " ".join(sys.argv[2:]))
    else:
        print("Usage: python3 log_reason.py \"AWAY @ HOME\" \"Reason for line move\"")
