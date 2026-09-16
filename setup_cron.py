#!/usr/bin/env python3
"""
NFL Line Tracker — Cron Scheduler (v2 Comprehensive Window)
Schedule breakdown:
1. Wed-Sat: Every 3 hours (0, 3, 6, 9, 12, 15, 18, 21 CT)
2. Sunday Early Window (6 AM - 12 PM CT):
   - Hourly 6am, 7am, 8am, 9am, 10am
   - 11:00 AM, 11:30 AM, 11:55 AM (captures the final sharp steam before 12:00 PM kickoff)
3. Sunday Afternoon & Primetime (1 PM - 10 PM CT):
   - 3:00 PM, 3:20 PM (final steam before 3:25 PM late window)
   - 6:00 PM, 7:10 PM (final steam before 7:20 PM SNF kickoff)
   - 10:00 PM (post-SNF recap snapshot)
4. Monday:
   - Every 3 hours (9am, 12pm, 3pm, 6pm CT)
   - 7:10 PM CT (final steam before 7:15 PM MNF kickoff)
   - 10:30 PM CT (post-MNF close)

Usage:
  python3 setup_cron.py install   # Add cron jobs
  python3 setup_cron.py remove    # Remove cron jobs
  python3 setup_cron.py status    # Show current cron entries
"""

import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRAPER = os.path.join(SCRIPT_DIR, "scrape_nfl_lines.py")
PLOTTER = os.path.join(SCRIPT_DIR, "plot_nfl_lines.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "data", "cron.log")
PYTHON = sys.executable or "/usr/bin/python3"

MARKER = "# NFL-LINE-TRACKER"
CMD = f'{PYTHON} {SCRAPER} >> {LOG_FILE} 2>&1 && {PYTHON} {PLOTTER} >> {LOG_FILE} 2>&1'

CRON_LINES = [
    # 1. Wed-Sat every 3 hours
    f"0 0,3,6,9,12,15,18,21 * * 3,4,5,6 {CMD} {MARKER}",
    # 2. Sunday Early Window: 6,7,8,9,10 AM hourly
    f"0 6,7,8,9,10 * * 0 {CMD} {MARKER}",
    # 3. Sunday Early Kickoff Steam: 11:00, 11:30, 11:55 AM
    f"0,30,55 11 * * 0 {CMD} {MARKER}",
    # 4. Sunday Late Window & SNF Steam: 3:00 PM, 3:20 PM, 6:00 PM, 7:10 PM, 10:00 PM
    f"0,20 15 * * 0 {CMD} {MARKER}",
    f"0 18 * * 0 {CMD} {MARKER}",
    f"10 19 * * 0 {CMD} {MARKER}",
    f"0 22 * * 0 {CMD} {MARKER}",
    # 5. Monday Window: 9am, 12pm, 3pm, 6pm, 7:10pm (MNF steam), 10:30pm
    f"0 9,12,15,18 * * 1 {CMD} {MARKER}",
    f"10 19 * * 1 {CMD} {MARKER}",
    f"30 22 * * 1 {CMD} {MARKER}",
]


def get_current_crontab():
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if res.returncode == 0:
            return res.stdout
        return ""
    except:
        return ""


def install():
    current = get_current_crontab()
    lines = [l for l in current.strip().split("\n") if MARKER not in l and l.strip()]
    lines.extend(CRON_LINES)
    new_crontab = "\n".join(lines) + "\n"

    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode == 0:
        print("✅ Comprehensive NFL Tracker Cron Schedule Installed!")
        print("\nActive Windows:")
        print("  • Wed–Sat: Every 3 hours (0, 3, 6, 9, 12, 15, 18, 21 CT)")
        print("  • Sunday Early Window: 6, 7, 8, 9, 10 AM CT")
        print("  • Sunday 12 PM Kickoff Steam: 11:00 AM, 11:30 AM, 11:55 AM CT")
        print("  • Sunday 3:25 PM Late Window Steam: 3:00 PM, 3:20 PM CT")
        print("  • Sunday Night Football Steam: 6:00 PM, 7:10 PM CT, 10:00 PM wrap")
        print("  • Monday (MNF Steam): 9am, 12pm, 3pm, 6pm, 7:10 PM CT, 10:30 PM wrap")
        print(f"\nLogs: {LOG_FILE}")
    else:
        print(f"❌ Error: {proc.stderr}")


def remove():
    current = get_current_crontab()
    lines = [l for l in current.strip().split("\n") if MARKER not in l and l.strip()]
    new_crontab = "\n".join(lines) + "\n" if lines else ""

    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode == 0:
        print("✅ NFL Tracker cron jobs removed.")
    else:
        print(f"❌ Error: {proc.stderr}")


def status():
    current = get_current_crontab()
    nfl_lines = [l for l in current.strip().split("\n") if MARKER in l]
    if nfl_lines:
        print(f"✅ {len(nfl_lines)} NFL Line Tracker cron schedules active:")
        for l in nfl_lines:
            print(f"  {l}")
    else:
        print("❌ No NFL Line Tracker cron jobs active. Run: python3 setup_cron.py install")


if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    if action == "install": install()
    elif action == "remove": remove()
    elif action == "status": status()
    else: print("Usage: python3 setup_cron.py [install|remove|status]")
