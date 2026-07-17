Build a durable ticket-availability checker for Pacific Science Center’s IMAX presentation of “The Odyssey.”

The main event page is:

https://my.pacificsciencecenter.org/79140

Background:
- Event ID 79140 represents The Odyssey.
- There are approximately 20 days with about 3 performances per day.
- The event page has a dropdown or selector containing the individual showtimes.
- Each individual performance appears to have its own URL, such as:
  https://my.pacificsciencecenter.org/79140/79156
- An available showing exposes ticket-purchasing controls, including wording such as “Purchase items” or “Available Groups.”
- A sold-out showing displays wording such as “Sold Out!”
- Do not assume that merely appearing in the dropdown means a performance is available.

Goal:
Create a Python Playwright program that discovers every listed performance and determines which performances currently have tickets available.

Before editing anything:
1. Inspect the current directory.
2. Run:
   pwd
   git branch --show-current 2>/dev/null || true
   git status --short 2>/dev/null || true
   find . -maxdepth 2 -type f | sort | head -200
3. Report what already exists and avoid overwriting unrelated work.

Functional requirements:

1. Use Python 3 and Playwright with Chromium.
2. Start from the event page rather than relying on a hard-coded list of performance IDs.
3. Discover all dates, times, performance IDs, and individual performance URLs from the site’s actual browser DOM, page links, JavaScript state, or network responses.
4. Visit or otherwise inspect every individual performance.
5. Classify each performance as exactly one of:
   - AVAILABLE
   - SOLD_OUT
   - UNKNOWN
6. Use multiple signals where practical:
   - explicit “Sold Out!” text,
   - purchase or ticket-selection controls,
   - available ticket quantity selectors,
   - disabled purchase controls,
   - relevant page or API response data.
7. Never classify an ambiguous page as sold out. Use UNKNOWN and preserve diagnostics.
8. Capture these fields:
   - event_name
   - performance_id
   - date
   - time
   - status
   - max_selectable_quantity, if discoverable
   - performance_url
   - checked_at
   - evidence
9. Produce:
   - output/odyssey_availability.csv containing all performances,
   - output/odyssey_available.md containing a Markdown table of AVAILABLE performances only,
   - output/odyssey_all.md containing all performances and statuses,
   - output/unknown/ screenshots and saved HTML for UNKNOWN results.
10. Sort results chronologically.
11. Deduplicate performances.
12. Print a concise console summary, including counts for available, sold out, and unknown.
13. Exit nonzero if:
   - no performances are discovered,
   - every performance is UNKNOWN,
   - or a fatal browser/site error prevents a complete run.
14. Be respectful of the site:
   - use one browser session,
   - process performances sequentially or with very low concurrency,
   - add a modest delay between performance checks,
   - do not attempt to bypass CAPTCHAs, access controls, queues, or rate limits.
15. Do not purchase tickets, add tickets to a cart, log in, or submit personal/payment information.

Reliability requirements:
- Prefer durable selectors based on roles, labels, visible text, links, and data attributes.
- Avoid brittle absolute XPath selectors and fixed element positions.
- Account for delayed JavaScript rendering.
- Handle navigation failures and retry transient errors a small number of times.
- Log enough evidence to explain every classification.
- Make headless mode configurable.
- Add a --headed option for debugging.
- Add a --limit option for testing only the first N performances.
- Add a --performance-id option for checking one known performance.
- Add a --delay-seconds option.
- Add a --verbose option.

Project files:
- check_odyssey.py
- requirements.txt or pyproject.toml
- README.md
- tests for parsing/classification logic where feasible
- .gitignore
- output/.gitkeep

README requirements:
- installation instructions,
- Playwright browser installation,
- example commands,
- output descriptions,
- troubleshooting,
- explanation of AVAILABLE, SOLD_OUT, and UNKNOWN,
- warning that availability may change immediately after checking.

Suggested commands should work approximately like:

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python check_odyssey.py
python check_odyssey.py --headed --verbose
python check_odyssey.py --limit 3 --headed
python check_odyssey.py --performance-id 79156 --headed

Implementation process:
1. Inspect the live page with Playwright.
2. Determine how performance choices map to individual performance IDs or URLs.
3. Implement discovery.
4. Implement classification.
5. Test against at least these supplied examples:
   - July 21 at 4:05 p.m. was reported available.
   - July 21 at 7:30 p.m. was reported sold out.
   These are validation clues, not permanent assumptions; current site status is authoritative.
6. Run a limited headed test.
7. Run the complete checker.
8. Inspect the generated files.
9. Report:
   - architecture,
   - selectors and signals used,
   - test results,
   - number of performances found,
   - counts by status,
   - any UNKNOWN cases,
   - exact command for the next manual run.

Do not stop after merely scaffolding the project. Continue until there is a working end-to-end run or until a specific external obstacle is demonstrated with diagnostics.