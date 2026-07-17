#!/usr/bin/env python3
"""Check every listed Pacific Science Center performance of The Odyssey."""

import argparse
import csv
import html
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from playwright.sync_api import Browser, Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


EVENT_URL = "https://my.pacificsciencecenter.org/79140"
OUTPUT_DIR = Path("output")
UNKNOWN_DIR = OUTPUT_DIR / "unknown"
DOCS_DIR = Path("docs")
SHOWTIME_RE = re.compile(
    r"(?P<label>(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s*[AP]M)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PerformanceSeed:
    event_name: str
    performance_id: str
    date: str
    time: str
    performance_url: str
    sort_key: datetime


@dataclass
class PageSignals:
    sold_out_text: bool
    purchase_heading: bool
    purchase_form: bool
    positive_quantities: List[int]
    disabled_quantity_selectors: int
    positive_zone_counts: List[int]
    add_to_cart_present: bool
    add_to_cart_disabled: bool
    http_status: Optional[int]


@dataclass
class Result:
    event_name: str
    performance_id: str
    date: str
    time: str
    status: str
    max_selectable_quantity: Optional[int]
    performance_url: str
    checked_at: str
    evidence: str


def parse_showtime(label: str) -> Tuple[str, str, datetime]:
    """Parse a Tessitura showtime label into stable output fields."""
    normalized = re.sub(r"\s+", " ", label).strip()
    parsed = datetime.strptime(normalized.upper(), "%A, %B %d, %Y %I:%M%p")
    display_time = parsed.strftime("%I:%M %p").lstrip("0")
    return parsed.strftime("%Y-%m-%d"), display_time, parsed


def extract_current_showtime(body_text: str) -> Tuple[str, str, datetime]:
    """Extract the current performance date from the Item Details block."""
    item_details = re.search(
        r"ITEM DETAILS\s+DATE\s+(.*?)\s+LOCATION\b", body_text, re.IGNORECASE | re.DOTALL
    )
    if not item_details:
        raise ValueError("Could not locate the Item Details date block")
    match = SHOWTIME_RE.search(item_details.group(1))
    if not match:
        raise ValueError("Could not parse the current performance date/time")
    return parse_showtime(match.group("label"))


def extract_event_name(body_text: str, title: str) -> str:
    match = re.search(
        r"\bNAME\s+(.*?)\s+DESCRIPTION\b", body_text, re.IGNORECASE | re.DOTALL
    )
    if match:
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        if name:
            return name
    fallback = title.split("|")[0].strip()
    return fallback or "The Odyssey"


def performance_id_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if not parts or not parts[-1].isdigit():
        raise ValueError("No numeric performance ID in URL: {}".format(url))
    return parts[-1]


def classify_signals(signals: PageSignals) -> Tuple[str, Optional[int], List[str]]:
    """Classify strong DOM signals, preserving ambiguity as UNKNOWN."""
    evidence = []  # type: List[str]
    max_quantity = max(signals.positive_quantities) if signals.positive_quantities else None
    has_quantity_availability = bool(signals.positive_quantities)
    has_zone_availability = bool(signals.positive_zone_counts)
    has_strong_availability = signals.purchase_form and (
        has_quantity_availability or has_zone_availability
    )

    if signals.http_status is not None:
        evidence.append("main document HTTP {}".format(signals.http_status))
    if signals.sold_out_text:
        evidence.append("explicit 'Sold Out!' text")
    if signals.purchase_heading:
        evidence.append("'Purchase items' heading")
    if signals.purchase_form:
        evidence.append("ticket-selector form present")
    if has_quantity_availability:
        evidence.append("enabled quantity options through {}".format(max_quantity))
    if has_zone_availability:
        evidence.append(
            "positive zone availability count(s): {}".format(
                ", ".join(str(value) for value in sorted(set(signals.positive_zone_counts)))
            )
        )
    if signals.disabled_quantity_selectors:
        evidence.append(
            "{} disabled quantity selector(s)".format(signals.disabled_quantity_selectors)
        )
    if signals.add_to_cart_present:
        evidence.append(
            "Add To Cart button {}"
            .format("disabled pending a selection" if signals.add_to_cart_disabled else "enabled")
        )

    if signals.sold_out_text and has_strong_availability:
        evidence.append("conflicting sold-out and availability signals")
        return "UNKNOWN", max_quantity, evidence
    if signals.sold_out_text:
        return "SOLD_OUT", None, evidence
    if has_strong_availability and signals.purchase_heading:
        return "AVAILABLE", max_quantity, evidence

    evidence.append("no conclusive combination of availability or sold-out signals")
    return "UNKNOWN", max_quantity, evidence


def navigate_with_retries(page: Page, url: str, verbose: bool, attempts: int = 3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.locator("body").wait_for(state="attached", timeout=10_000)
            page.locator("#tn-additional-events-select").wait_for(state="attached", timeout=15_000)
            page.wait_for_timeout(750)
            return response
        except (PlaywrightTimeout, PlaywrightError) as exc:
            last_error = exc
            if verbose:
                print("  navigation attempt {}/{} failed: {}".format(attempt, attempts, exc))
            if attempt < attempts:
                page.wait_for_timeout(1_500 * attempt)
    raise RuntimeError("navigation failed after {} attempts: {}".format(attempts, last_error))


def discover_performances(page: Page, verbose: bool) -> List[PerformanceSeed]:
    response = navigate_with_retries(page, EVENT_URL, verbose)
    if response is not None and response.status >= 400:
        raise RuntimeError("event page returned HTTP {}".format(response.status))

    body_text = page.locator("body").inner_text()
    event_name = extract_event_name(body_text, page.title())
    date, show_time, sort_key = extract_current_showtime(body_text)
    current_url = page.url.split("?", 1)[0].rstrip("/")
    discovered = [
        PerformanceSeed(
            event_name=event_name,
            performance_id=performance_id_from_url(current_url),
            date=date,
            time=show_time,
            performance_url=current_url,
            sort_key=sort_key,
        )
    ]

    options = page.locator("#tn-additional-events-select option").evaluate_all(
        """options => options.map(option => ({
            text: (option.textContent || '').trim(),
            value: option.value,
            disabled: option.disabled
        }))"""
    )
    for option in options:
        if option["disabled"] or not option["value"]:
            continue
        option_date, option_time, option_sort_key = parse_showtime(option["text"])
        option_url = option["value"].split("?", 1)[0].rstrip("/")
        discovered.append(
            PerformanceSeed(
                event_name=event_name,
                performance_id=performance_id_from_url(option_url),
                date=option_date,
                time=option_time,
                performance_url=option_url,
                sort_key=option_sort_key,
            )
        )

    deduplicated = {}  # type: Dict[str, PerformanceSeed]
    for performance in discovered:
        deduplicated[performance.performance_id] = performance
    results = sorted(deduplicated.values(), key=lambda item: (item.sort_key, item.performance_id))
    if verbose:
        print("Discovered {} unique performances from the live selector.".format(len(results)))
    return results


def collect_signals(page: Page, http_status: Optional[int]) -> PageSignals:
    body_text = page.locator("body").inner_text()
    quantity_data = page.locator(".tn-ticket-selector__pricetype-select").evaluate_all(
        """selects => selects.map(select => ({
            disabled: !!select.disabled,
            visible: !!(select.offsetWidth || select.offsetHeight || select.getClientRects().length),
            values: Array.from(select.options).map(option => option.value)
        }))"""
    )
    positive_quantities = []  # type: List[int]
    disabled_quantity_selectors = 0
    for selector in quantity_data:
        if selector["disabled"]:
            disabled_quantity_selectors += 1
            continue
        if not selector["visible"]:
            continue
        for value in selector["values"]:
            if str(value).isdigit() and int(value) > 0:
                positive_quantities.append(int(value))

    zone_counts = []
    for value in page.locator("[data-tn-zone-available-count]").evaluate_all(
        "els => els.map(el => el.getAttribute('data-tn-zone-available-count'))"
    ):
        if value and str(value).isdigit() and int(value) > 0:
            zone_counts.append(int(value))

    add_button = page.locator("#tn-add-to-cart-button")
    add_button_present = add_button.count() > 0
    return PageSignals(
        sold_out_text=bool(re.search(r"\bSold\s+Out!", body_text, re.IGNORECASE)),
        purchase_heading=page.locator("h2", has_text=re.compile(r"Purchase items", re.I)).count()
        > 0,
        purchase_form=page.locator("#tn-events-detail-best-available-form").count() > 0,
        positive_quantities=positive_quantities,
        disabled_quantity_selectors=disabled_quantity_selectors,
        positive_zone_counts=zone_counts,
        add_to_cart_present=add_button_present,
        add_to_cart_disabled=add_button.is_disabled() if add_button_present else False,
        http_status=http_status,
    )


def save_unknown_diagnostics(page: Page, performance_id: str, checked_at: str) -> List[str]:
    UNKNOWN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = re.sub(r"[^0-9]", "", checked_at)[:14]
    stem = "odyssey_{}_{}".format(performance_id, stamp)
    saved = []
    html_path = UNKNOWN_DIR / "{}.html".format(stem)
    html_path.write_text(page.content(), encoding="utf-8")
    saved.append(str(html_path))
    screenshot_path = UNKNOWN_DIR / "{}.png".format(stem)
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        saved.append(str(screenshot_path))
    except PlaywrightError as exc:
        saved.append("screenshot failed: {}".format(exc))
    return saved


def check_performance(page: Page, seed: PerformanceSeed, verbose: bool) -> Tuple[Result, bool]:
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    navigation_failed = False
    try:
        response = navigate_with_retries(page, seed.performance_url, verbose)
        http_status = response.status if response is not None else None
        signals = collect_signals(page, http_status)
        status, max_quantity, evidence = classify_signals(signals)

        try:
            actual_date, actual_time, _ = extract_current_showtime(page.locator("body").inner_text())
            if (actual_date, actual_time) != (seed.date, seed.time):
                status = "UNKNOWN"
                evidence.append(
                    "page date/time {} {} did not match discovered {} {}".format(
                        actual_date, actual_time, seed.date, seed.time
                    )
                )
        except ValueError as exc:
            status = "UNKNOWN"
            evidence.append(str(exc))
    except Exception as exc:
        navigation_failed = True
        status = "UNKNOWN"
        max_quantity = None
        evidence = ["navigation/site error: {}".format(exc)]

    if status == "UNKNOWN":
        try:
            saved = save_unknown_diagnostics(page, seed.performance_id, checked_at)
            evidence.append("diagnostics: {}".format(", ".join(saved)))
        except Exception as exc:
            evidence.append("could not save diagnostics: {}".format(exc))

    return (
        Result(
            event_name=seed.event_name,
            performance_id=seed.performance_id,
            date=seed.date,
            time=seed.time,
            status=status,
            max_selectable_quantity=max_quantity,
            performance_url=seed.performance_url,
            checked_at=checked_at,
            evidence="; ".join(evidence),
        ),
        navigation_failed,
    )


def markdown_escape(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def write_markdown(path: Path, title: str, results: Sequence[Result]) -> None:
    headers = ["Date", "Time", "Status", "Max quantity", "Performance ID", "URL", "Evidence"]
    lines = ["# {}".format(title), "", "| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for result in results:
        values = [
            result.date,
            result.time,
            result.status,
            result.max_selectable_quantity,
            result.performance_id,
            "[tickets]({})".format(result.performance_url),
            result.evidence,
        ]
        lines.append("| " + " | ".join(markdown_escape(value) for value in values) + " |")
    if not results:
        lines.extend(["", "No matching performances were found at check time."])
    lines.extend(
        [
            "",
            "> Availability can change immediately after this check. Confirm on the ticket page before making plans.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def render_shareable_html(results: Sequence[Result]) -> str:
    available = [result for result in results if result.status == "AVAILABLE"]
    grouped = []  # type: List[Tuple[str, List[Result]]]
    for result in available:
        if not grouped or grouped[-1][0] != result.date:
            grouped.append((result.date, []))
        grouped[-1][1].append(result)

    checked_at = max((result.checked_at for result in results), default="")
    rows = []
    for date_value, showings in grouped:
        parsed_date = datetime.strptime(date_value, "%Y-%m-%d")
        display_date = "{}, {} {}".format(
            parsed_date.strftime("%a"), parsed_date.strftime("%b"), parsed_date.day
        )
        links = []
        for showing in showings:
            low_badge = ""
            if showing.max_selectable_quantity is not None and showing.max_selectable_quantity <= 5:
                low_badge = (
                    '<span class="low" aria-label="Low availability">only {}</span>'
                    .format(showing.max_selectable_quantity)
                )
            links.append(
                '<span class="showing"><a href="{}" target="_blank" '
                'rel="noopener noreferrer">{}</a>{}</span>'.format(
                    html.escape(showing.performance_url, quote=True),
                    html.escape(showing.time),
                    low_badge,
                )
            )
        rows.append(
            "<tr><th scope=\"row\">{}</th><td>{}</td></tr>".format(
                html.escape(display_date), "".join(links)
            )
        )

    empty_row = ""
    if not rows:
        empty_row = '<tr><td colspan="2" class="empty">No available showtimes found.</td></tr>'

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Available Pacific Science Center IMAX showtimes for The Odyssey.">
  <title>The Odyssey — PacSci IMAX Showtimes</title>
  <style>
    :root {{ color-scheme: dark; --ink:#f7f7f2; --muted:#aaaeb8; --line:#292c35; --panel:#171920; --red:#ff544d; --gold:#ffd166; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#0b0c10; color:var(--ink); font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    body::before {{ content:""; position:fixed; inset:0 0 auto; height:5px; background:linear-gradient(90deg,#165dff,#8b5cf6,var(--red)); }}
    main {{ width:min(920px,calc(100% - 32px)); margin:0 auto; padding:64px 0 72px; }}
    .eyebrow {{ margin:0 0 8px; color:var(--red); font-size:.76rem; font-weight:800; letter-spacing:.18em; text-transform:uppercase; }}
    h1 {{ margin:0; font-size:clamp(2.4rem,8vw,5.6rem); line-height:.93; letter-spacing:-.055em; }}
    .lede {{ max-width:650px; margin:22px 0 10px; color:var(--muted); font-size:1.08rem; }}
    .summary {{ display:inline-flex; gap:8px; align-items:center; margin:10px 0 30px; padding:8px 12px; border:1px solid var(--line); border-radius:999px; background:var(--panel); font-size:.9rem; }}
    .dot {{ width:8px; height:8px; border-radius:50%; background:#43d17d; box-shadow:0 0 12px #43d17d; }}
    .table-wrap {{ overflow:hidden; border:1px solid var(--line); border-radius:16px; background:var(--panel); box-shadow:0 24px 80px #0008; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ padding:17px 20px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    thead th {{ color:var(--muted); background:#12141a; font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; }}
    tbody th {{ width:150px; white-space:nowrap; font-weight:700; }}
    tbody tr:last-child th,tbody tr:last-child td {{ border-bottom:0; }}
    tbody tr:hover {{ background:#1b1e27; }}
    .showing {{ display:inline-flex; align-items:center; gap:6px; margin:0 13px 7px 0; }}
    .showing a {{ color:var(--ink); font-weight:750; text-decoration-color:#6f7482; text-underline-offset:4px; }}
    .showing a:hover,.showing a:focus {{ color:#9fc0ff; text-decoration-color:#9fc0ff; }}
    .showing a::after {{ content:" ↗"; color:#7d8290; font-size:.78em; }}
    .low {{ padding:2px 7px; border:1px solid #6b5724; border-radius:999px; color:var(--gold); background:#2b2415; font-size:.72rem; white-space:nowrap; }}
    .empty {{ padding:40px 20px; color:var(--muted); text-align:center; }}
    footer {{ margin-top:24px; color:var(--muted); font-size:.86rem; }}
    footer p {{ margin:7px 0; }}
    footer a {{ color:#bbc9ea; }}
    @media (max-width:620px) {{
      main {{ width:min(100% - 20px,920px); padding-top:48px; }}
      .table-wrap {{ border-radius:12px; }}
      th,td {{ padding:15px 13px; }}
      tbody th {{ width:105px; white-space:normal; }}
      .showing {{ display:flex; width:max-content; margin-bottom:9px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">Pacific Science Center · IMAX</p>
      <h1>The Odyssey</h1>
      <p class="lede">Available showtimes in Seattle. Select a time to open that performance’s official ticket page.</p>
      <p class="summary"><span class="dot" aria-hidden="true"></span><strong>{show_count}</strong> showings available across <strong>{date_count}</strong> days</p>
    </header>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Date</th><th>Available showtimes</th></tr></thead>
        <tbody>
          {rows}
          {empty_row}
        </tbody>
      </table>
    </div>
    <footer>
      <p>Last checked: <time id="checked-at" datetime="{checked_at}">{checked_at_fallback}</time>.</p>
      <p>Availability can change at any moment. Confirm on the official ticket page before making plans.</p>
      <p><a href="https://my.pacificsciencecenter.org/79140">View the main PacSci event page</a></p>
    </footer>
  </main>
  <script>
    const checked = document.querySelector('#checked-at');
    if (checked && checked.dateTime) {{
      checked.textContent = new Date(checked.dateTime).toLocaleString(undefined, {{ dateStyle:'medium', timeStyle:'short' }});
    }}
  </script>
</body>
</html>
""".format(
        show_count=len(available),
        date_count=len(grouped),
        rows="\n          ".join(rows),
        empty_row=empty_row,
        checked_at=html.escape(checked_at, quote=True),
        checked_at_fallback=html.escape(checked_at or "not yet checked"),
    )


def write_outputs(results: Sequence[Result]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "odyssey_availability.csv"
    fieldnames = [
        "event_name",
        "performance_id",
        "date",
        "time",
        "status",
        "max_selectable_quantity",
        "performance_url",
        "checked_at",
        "evidence",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    write_markdown(
        OUTPUT_DIR / "odyssey_available.md",
        "The Odyssey — Available Performances",
        [result for result in results if result.status == "AVAILABLE"],
    )
    write_markdown(OUTPUT_DIR / "odyssey_all.md", "The Odyssey — All Performances", results)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(render_shareable_html(results), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover and check Pacific Science Center's The Odyssey performances."
    )
    parser.add_argument("--headed", action="store_true", help="Show Chromium for debugging")
    parser.add_argument("--limit", type=int, help="Check only the first N discovered performances")
    parser.add_argument("--performance-id", help="Check one discovered performance ID")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay between performance checks (default: 1.0)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-performance evidence")
    return parser


def validate_args(parser: argparse.ArgumentParser, args) -> None:
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds cannot be negative")
    if args.limit is not None and args.performance_id:
        parser.error("--limit and --performance-id cannot be used together")


def block_heavy_resources(route) -> None:
    if route.request.resource_type in {"image", "media", "font"}:
        route.abort()
    else:
        route.continue_()


def run(args) -> int:
    results = []  # type: List[Result]
    incomplete = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = context.new_page()
                page.route("**/*", block_heavy_resources)
                performances = discover_performances(page, args.verbose)

                if args.performance_id:
                    performances = [
                        item for item in performances if item.performance_id == args.performance_id
                    ]
                    if not performances:
                        print(
                            "Performance ID {} was not present in the live event selector."
                            .format(args.performance_id),
                            file=sys.stderr,
                        )
                        return 2
                elif args.limit is not None:
                    performances = performances[: args.limit]

                if not performances:
                    print("No performances were discovered.", file=sys.stderr)
                    return 2

                total = len(performances)
                for index, performance in enumerate(performances, start=1):
                    print(
                        "[{}/{}] {} {} (ID {})".format(
                            index, total, performance.date, performance.time, performance.performance_id
                        )
                    )
                    result, navigation_failed = check_performance(page, performance, args.verbose)
                    results.append(result)
                    incomplete = incomplete or navigation_failed
                    if args.verbose:
                        print("  {} — {}".format(result.status, result.evidence))
                    if index < total and args.delay_seconds:
                        time.sleep(args.delay_seconds)
            finally:
                browser.close()
    except Exception as exc:
        if results:
            write_outputs(results)
        print("Fatal browser/site error: {}".format(exc), file=sys.stderr)
        return 4

    write_outputs(results)
    counts = Counter(result.status for result in results)
    print(
        "Summary: {} performances — {} available, {} sold out, {} unknown.".format(
            len(results), counts["AVAILABLE"], counts["SOLD_OUT"], counts["UNKNOWN"]
        )
    )
    print(
        "Wrote output/odyssey_availability.csv, output/odyssey_available.md, "
        "output/odyssey_all.md, docs/index.html"
    )

    if incomplete:
        print("Run incomplete: one or more pages failed navigation after retries.", file=sys.stderr)
        return 4
    if results and counts["UNKNOWN"] == len(results):
        print("Every performance was UNKNOWN.", file=sys.stderr)
        return 3
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
