import unittest
import json
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from check_imax import (
    Film, MissingShowtimesError, PerformanceSeed, Result, configured_films, feature_rollover_due,
    navigate_with_retries, render_index, render_shareable_html, discover_current_feature,
    main,
)


def result(name, performance_id, url):
    return Result(
        event_name=name,
        performance_id=performance_id,
        date="2026-10-14",
        time="4:45 PM",
        status="AVAILABLE",
        max_selectable_quantity=2,
        performance_url=url,
        checked_at="2026-10-12T05:00:00+00:00",
        evidence="test",
    )


class FilmConfigurationTests(unittest.TestCase):
    def test_current_feature_event_id_is_configured(self):
        films = configured_films()
        configured_id = json.loads(Path("current_feature.json").read_text())["event_id"]
        self.assertEqual([film.event_id for film in films], ["80814", configured_id])

    def test_feature_rollover_waits_until_after_final_show(self):
        with TemporaryDirectory() as directory:
            Path(directory, "current_feature_availability.csv").write_text(
                "date,status\n2026-10-18,AVAILABLE\n2026-10-22,AVAILABLE\n",
                encoding="utf-8",
            )
            with patch("check_imax.OUTPUT_DIR", Path(directory)):
                self.assertFalse(feature_rollover_due(date(2026, 10, 22)))
                self.assertTrue(feature_rollover_due(date(2026, 10, 23)))

    def test_missing_selector_is_distinct_from_other_navigation_errors(self):
        page = MagicMock()
        page.locator.return_value.first.wait_for.side_effect = PlaywrightTimeout("no selector")
        with self.assertRaises(MissingShowtimesError):
            navigate_with_retries(page, "https://my.pacificsciencecenter.org/81344", False)
        self.assertEqual(page.goto.call_count, 3)

    def test_film_pages_use_the_film_name_and_event_url(self):
        film = Film("current_feature", "81348", "Digger")
        rendered = render_shareable_html(
            [result("Digger", "81359", "https://my.pacificsciencecenter.org/81348/81359")],
            film,
        )
        self.assertIn("<h1>Digger</h1>", rendered)
        self.assertIn('href="https://my.pacificsciencecenter.org/81348"', rendered)
        self.assertIn('href="https://my.pacificsciencecenter.org/81348/81359"', rendered)
        self.assertNotIn("The Odyssey", rendered)

    def test_index_links_to_both_films(self):
        films = [Film("dune_three", "80814", "Dune: Part 3"), Film("current_feature", "81348", "Digger")]
        results = {
            "dune_three": [result("Dune: Part 3", "80816", "https://example.test/80814/80816")],
            "current_feature": [result("Digger", "81359", "https://example.test/81348/81359")],
        }
        rendered = render_index(films, results)
        self.assertIn('href="dune_three.html"', rendered)
        self.assertIn('href="current_feature.html"', rendered)
        self.assertIn("Dune: Part 3", rendered)
        self.assertIn("Digger", rendered)


class FeatureReplacementTests(unittest.TestCase):
    def seed(self, day="2099-01-01"):
        return PerformanceSeed("New feature", "90001", day, "4:30 PM",
                               "https://my.pacificsciencecenter.org/90000/90001",
                               datetime.fromisoformat(day))

    def page(self, ticket_links):
        page = MagicMock()
        page.goto.return_value.status = 200
        posters = MagicMock()
        posters.evaluate_all.return_value = [
            "https://pacificsciencecenter.org/shows/film-{}/".format(i)
            for i in range(len(ticket_links))
        ]
        links = MagicMock()
        links.evaluate_all.side_effect = ticket_links
        heading = MagicMock()
        heading.first.inner_text.return_value = "New feature"
        page.locator.side_effect = lambda selector: {
            ".movie-posters--short .movie-poster__link": posters,
            "a[href*='my.pacificsciencecenter.org/']": links,
            "h1": heading,
        }[selector]
        return page

    def test_skips_retired_poster_and_separately_tracked_film(self):
        page = self.page([
            ["https://my.pacificsciencecenter.org/account/login"],
            ["https://my.pacificsciencecenter.org/80814/80817"],
            ["https://my.pacificsciencecenter.org/90000/90001",
             "https://my.pacificsciencecenter.org/90000/90002"],
        ])
        with patch("check_imax.discover_performances", return_value=[self.seed()]):
            replacement = discover_current_feature(page, ["80814", "81344"])
        self.assertEqual(replacement, Film("current_feature", "90000", "New feature"))

    def test_does_not_replace_with_ended_candidate(self):
        page = self.page([["https://my.pacificsciencecenter.org/90000/90001"]])
        with patch("check_imax.discover_performances", return_value=[self.seed("2000-01-01")]):
            with self.assertRaisesRegex(RuntimeError, "no replacement"):
                discover_current_feature(page)

    def test_ambiguous_event_links_do_not_choose_a_film(self):
        page = self.page([["https://my.pacificsciencecenter.org/90000/90001",
                           "https://my.pacificsciencecenter.org/91000/91001"]])
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            discover_current_feature(page)

    def test_replacement_is_saved_only_after_successful_check(self):
        for status, missing_selector in (("AVAILABLE", True), ("UNKNOWN", True), ("AVAILABLE", False)):
            with self.subTest(status=status, missing_selector=missing_selector), TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "current_feature.json"
                config.write_text('{"event_id": "81344"}\n')
                checked = result("New feature", "90001", self.seed().performance_url)
                checked.status = status
                with patch("check_imax.CURRENT_FEATURE_CONFIG", config), \
                     patch("check_imax.OUTPUT_DIR", root / "output"), \
                     patch("check_imax.DOCS_DIR", root / "docs"), \
                     patch("check_imax.sync_playwright"), \
                     patch("check_imax.feature_rollover_due", return_value=missing_selector), \
                     patch("check_imax.discover_performances", side_effect=[MissingShowtimesError() if missing_selector else [self.seed("2000-01-01")], [self.seed()]]), \
                     patch("check_imax.discover_current_feature", return_value=Film("current_feature", "90000", "New feature")), \
                     patch("check_imax.check_performance", return_value=(checked, False)):
                    exit_code = main(["--film", "current_feature"])
                self.assertEqual(exit_code, 0 if status == "AVAILABLE" else 3)
                self.assertEqual(json.loads(config.read_text())["event_id"],
                                 "90000" if status == "AVAILABLE" else "81344")
                if status == "AVAILABLE":
                    self.assertIn("New feature", (root / "docs/current_feature.html").read_text())
                else:
                    self.assertFalse((root / "docs/current_feature.html").exists())


if __name__ == "__main__":
    unittest.main()
