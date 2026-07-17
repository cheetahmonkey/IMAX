# The Odyssey IMAX ticket checker

This project uses one Playwright/Chromium browser session to discover every listed
Pacific Science Center performance of *The Odyssey* and classify its current ticket
status. It reads the live date/time selector on the event page; performance IDs are
not hard-coded.

## Install

Python 3.8 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

On Linux, Playwright may report missing operating-system libraries. If so, follow
its displayed instructions or run `playwright install-deps chromium` with the
appropriate system privileges.

## Run

```bash
python check_odyssey.py
python check_odyssey.py --headed --verbose
python check_odyssey.py --limit 3 --headed
python check_odyssey.py --performance-id 79156 --headed
python check_odyssey.py --delay-seconds 2
```

`--headed` shows Chromium for debugging. `--limit` checks only the first N
chronological performances. `--performance-id` filters the performances discovered
from the live event page to one ID. `--delay-seconds` controls the respectful pause
between checks (default: one second), and `--verbose` prints detailed evidence.

The checker never selects a ticket, adds anything to a cart, logs in, or submits a
form. Performances are processed sequentially in a single browser session.

## Status rules

- `AVAILABLE`: the page has the purchase form and heading, plus an enabled positive
  quantity option or a positive zone-availability count.
- `SOLD_OUT`: the page explicitly says `Sold Out!` and has no conflicting strong
  availability signals.
- `UNKNOWN`: the page is incomplete, ambiguous, internally contradictory, or cannot
  be interpreted safely. `UNKNOWN` is never silently treated as sold out.

The Add To Cart button is normally disabled until a quantity is selected, including
on available performances, so its initial disabled state is only supporting evidence.

## Output

- `output/odyssey_availability.csv`: every checked performance and its evidence.
- `output/odyssey_available.md`: only performances classified `AVAILABLE`.
- `output/odyssey_all.md`: every checked performance in a Markdown table.
- `output/unknown/`: timestamped HTML and screenshots for `UNKNOWN` results.
- `docs/index.html`: a mobile-friendly, shareable table for GitHub Pages. Each
  showtime links directly to its official ticket page.

Rows are deduplicated by performance ID and sorted chronologically. The process exits
nonzero if discovery finds nothing, all checked results are `UNKNOWN`, or a fatal
browser/site error prevents a complete run.

## Troubleshooting

- If Chromium is missing, run `playwright install chromium` in the active virtualenv.
- If a headed run says no display is available, use a desktop terminal, `xvfb-run`,
  or omit `--headed` for headless mode.
- If the site times out, rerun with `--verbose`; navigation is retried three times and
  unknown-page diagnostics are preserved.
- Cookie banners do not affect the read-only DOM checks and do not need to be accepted.
- Use `python -m unittest discover -s tests -v` to run the parsing/classification tests.

Ticket availability can change immediately after a check. Always confirm the live
ticket page before making plans.

## GitHub Pages

The public page is generated at `docs/index.html` on every successful run. Configure
GitHub Pages to deploy from the repository's default branch and the `/docs` folder.
For this repository, the expected URL is:

https://lepenseur1.github.io/IMAX/
