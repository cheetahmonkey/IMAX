import unittest

from check_imax import Film, Result, configured_films, render_index, render_shareable_html


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
        self.assertEqual([film.event_id for film in films], ["80814", "81348"])

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


if __name__ == "__main__":
    unittest.main()
