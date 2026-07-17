import unittest

from check_odyssey import PageSignals, Result, classify_signals, parse_showtime, render_shareable_html


def signals(**overrides):
    defaults = dict(
        sold_out_text=False,
        purchase_heading=False,
        purchase_form=False,
        positive_quantities=[],
        disabled_quantity_selectors=0,
        positive_zone_counts=[],
        add_to_cart_present=False,
        add_to_cart_disabled=False,
        http_status=200,
    )
    defaults.update(overrides)
    return PageSignals(**defaults)


class ShowtimeParsingTests(unittest.TestCase):
    def test_parses_selector_label(self):
        date, show_time, parsed = parse_showtime("Tuesday, July 21, 2026 4:05PM")
        self.assertEqual(date, "2026-07-21")
        self.assertEqual(show_time, "4:05 PM")
        self.assertEqual(parsed.hour, 16)


class ClassificationTests(unittest.TestCase):
    def test_available_requires_purchase_ui_and_positive_capacity(self):
        status, max_quantity, _ = classify_signals(
            signals(
                purchase_heading=True,
                purchase_form=True,
                positive_quantities=[1, 2, 50],
                positive_zone_counts=[84],
                add_to_cart_present=True,
                add_to_cart_disabled=True,
            )
        )
        self.assertEqual(status, "AVAILABLE")
        self.assertEqual(max_quantity, 50)

    def test_explicit_sold_out_is_sold_out(self):
        status, max_quantity, _ = classify_signals(signals(sold_out_text=True))
        self.assertEqual(status, "SOLD_OUT")
        self.assertIsNone(max_quantity)

    def test_conflicting_signals_are_unknown(self):
        status, _, evidence = classify_signals(
            signals(
                sold_out_text=True,
                purchase_heading=True,
                purchase_form=True,
                positive_quantities=[1],
            )
        )
        self.assertEqual(status, "UNKNOWN")
        self.assertTrue(any("conflicting" in item for item in evidence))

    def test_disabled_or_incomplete_purchase_ui_is_unknown(self):
        status, _, _ = classify_signals(
            signals(purchase_heading=True, purchase_form=True, disabled_quantity_selectors=3)
        )
        self.assertEqual(status, "UNKNOWN")


class HtmlRenderingTests(unittest.TestCase):
    def test_time_is_the_link_and_low_availability_is_visible(self):
        result = Result(
            event_name="The Odyssey",
            performance_id="79165",
            date="2026-07-19",
            time="12:40 PM",
            status="AVAILABLE",
            max_selectable_quantity=2,
            performance_url="https://example.test/79140/79165",
            checked_at="2026-07-17T18:55:13+00:00",
            evidence="test",
        )
        rendered = render_shareable_html([result])
        self.assertIn('href="https://example.test/79140/79165"', rendered)
        self.assertIn(">12:40 PM</a>", rendered)
        self.assertIn("only 2", rendered)
        self.assertIn("1</strong> showings", rendered)


if __name__ == "__main__":
    unittest.main()
