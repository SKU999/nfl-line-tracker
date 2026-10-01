import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

# The health tests do not render charts. Stub Matplotlib so the production
# module can be imported in minimal CI environments.
matplotlib = types.ModuleType("matplotlib")
matplotlib.use = lambda *_args, **_kwargs: None
pyplot = types.ModuleType("matplotlib.pyplot")
dates = types.ModuleType("matplotlib.dates")
ticker = types.ModuleType("matplotlib.ticker")
ticker.MaxNLocator = object
sys.modules.setdefault("matplotlib", matplotlib)
sys.modules.setdefault("matplotlib.pyplot", pyplot)
sys.modules.setdefault("matplotlib.dates", dates)
sys.modules.setdefault("matplotlib.ticker", ticker)

import plot_nfl_lines as plotter
import scrape_nfl_lines as scraper


class FeedHealthTests(unittest.TestCase):
    def test_latest_missing_market_is_immediate_degradation(self):
        snaps = [
            {
                "ts": "2026-10-01T05:00:00+00:00",
                "away": "PIT",
                "home": "CLE",
                "start": "2026-10-02T00:15:00+00:00",
                "dk_spread": 2.5,
                "dk_total": 38.5,
                "away_impl": 20.5,
                "home_impl": 18.0,
            },
            {
                "ts": "2026-10-01T08:00:00+00:00",
                "away": "PIT",
                "home": "CLE",
                "start": "2026-10-02T00:15:00+00:00",
                "dk_spread": None,
                "dk_total": None,
            },
        ]

        rows = plotter.build_board_rows(
            {"PIT@CLE": snaps},
            latest_ts="2026-10-01T08:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["latest_market_missing"])
        self.assertEqual(rows[0]["dk_sp1"], 2.5)
        self.assertEqual(rows[0]["t1"], 38.5)

    def test_status_records_invalid_matchups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_status_file = scraper.STATUS_FILE
            old_data_dir = scraper.DATA_DIR
            try:
                scraper.DATA_DIR = temp_dir
                scraper.STATUS_FILE = str(Path(temp_dir) / "scraper_status.json")
                scraper.write_status(
                    False,
                    error="Missing complete DraftKings market for 1 of 17 games: PIT@CLE",
                    games_count=17,
                    valid_games_count=16,
                    invalid_games=["PIT@CLE"],
                )
                status = json.loads(Path(scraper.STATUS_FILE).read_text())
            finally:
                scraper.STATUS_FILE = old_status_file
                scraper.DATA_DIR = old_data_dir

        self.assertFalse(status["success"])
        self.assertEqual(status["valid_games_count"], 16)
        self.assertEqual(status["invalid_games"], ["PIT@CLE"])

    def test_degraded_banner_is_not_replaced_by_generic_stale_js(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            status_path = temp_path / "scraper_status.json"
            status_path.write_text(json.dumps({
                "ts": "2026-10-01T08:00:00+00:00",
                "success": True,
                "error": None,
                "games_count": 17,
            }))
            old_status_file = plotter.STATUS_FILE
            try:
                plotter.STATUS_FILE = str(status_path)
                rows = [{
                    "away": "PIT",
                    "home": "CLE",
                    "n_snaps": 2,
                    "last_valid_ts": "2026-10-01T05:00:00+00:00",
                    "last_valid_str": "12:00 AM CT",
                    "latest_market_missing": True,
                    "is_stale_game": False,
                    "slate_window": "TNF",
                    "slate_label": "Thursday Night Football",
                    "is_thu": True,
                    "sp_div": 0,
                    "t_div": 0,
                    "sp_d": 0,
                    "t_d": 0,
                    "max_move": 0,
                    "sp_fav_open": "PIT -2.5",
                    "sp_fav_now": "PIT -2.5",
                    "dk_sp0": 2.5,
                    "dk_sp1": 2.5,
                    "t0": 38.5,
                    "t1": 38.5,
                    "ai": 20.5,
                    "hi": 18.0,
                }]
                plotter.generate_html([], rows, temp_dir, latest_ts="2026-10-01T08:00:00+00:00")
                html = (temp_path / "index.html").read_text()
            finally:
                plotter.STATUS_FILE = old_status_file

        self.assertIn("PARTIAL FEED DEGRADATION", html)
        self.assertIn("PIT@CLE", html)
        self.assertIn("data-banner-kind='degraded'", html)
        self.assertIn("bannerKind === 'healthy'", html)


if __name__ == "__main__":
    unittest.main()
