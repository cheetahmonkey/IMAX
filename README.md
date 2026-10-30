# PacSci IMAX ticket checker

This checker discovers every listed performance for **Dune: Part 3** and one
configurable **Current Feature** on Pacific Science Center's ticket site. It visits
each performance in one Playwright/Chromium session and classifies it as `AVAILABLE`,
`SOLD_OUT`, or `UNKNOWN`. It never selects tickets or submits a form.

The Dune event ID is `80814`. The Current Feature is configured in
[`current_feature.json`](current_feature.json). When the feature changes, the
scheduled checker can replace `event_id` automatically: it does
so only after the last stored show date has passed, the old event has no showtime
selector, and PacSci's current feature listing points to a different ticket event.
You can also replace `event_id` manually. The displayed film title comes from the
live ticket page. The checker discovers performance IDs and showtimes from that
event's selector; they are never entered into the config file.

## Install

Python 3.8 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

On Linux, follow Playwright's displayed instructions if Chromium needs system
libraries.

## Run

```bash
.venv/bin/python check_imax.py
.venv/bin/python check_imax.py --film current_feature
.venv/bin/python check_imax.py --film dune_three --limit 3 --headed
.venv/bin/python check_imax.py --film current_feature --performance-id 81359 --verbose
.venv/bin/python check_imax.py --delay-seconds 2
```

The default run checks both films and updates the landing page. `--film` selects one
film. `--limit` checks the first N chronological performances; `--performance-id`
requires a selected film. `--delay-seconds` controls the pause between checks
(default: one second). `--headed` shows Chromium, and `--verbose` prints evidence.
Limited and single-performance runs replace that film's output files, but do not
replace the landing page. Run the default command again to restore complete files.

For a scheduled refresh, use `scripts/refresh_imax.sh`. Its `--publish` option commits
and pushes generated files after a successful run. The local legacy
`scripts/refresh_odyssey.sh` can call that command if it is still scheduled.

## Status rules

- `AVAILABLE`: the purchase form and heading appear with an enabled positive
  quantity or positive zone availability count.
- `SOLD_OUT`: the visible page explicitly says `Sold Out!` without conflicting strong
  availability signals.
- `UNKNOWN`: the page is incomplete, ambiguous, contradictory, or could not be
  interpreted safely. A page saying tickets are no longer available *or cancelled*
  stays `UNKNOWN`.

The Add To Cart button is usually disabled until a quantity is selected, including
on available performances. Its initial disabled state is supporting evidence only.

## Output

For each film slug (`dune_three` and `current_feature`):

- `output/<slug>_availability.csv`: all checked performances and evidence.
- `output/<slug>_available.md`: available performances only.
- `output/<slug>_all.md`: all performances and statuses.
- `docs/<slug>.html`: shareable page with official ticket links.

`docs/index.html` links to both film pages after a complete two-film run.
`output/unknown/` holds timestamped HTML and screenshots for `UNKNOWN` results.
The old Odyssey checker and its generated files are retained for reference.

Rows are deduplicated by performance ID and sorted chronologically. A run exits
nonzero if discovery finds nothing, all results for either film are `UNKNOWN`, or a
browser/site failure prevents completion. Generated pages update only after a
successful run.

Run `python -m unittest discover -s tests -v` for parsing and classification tests.
If Chromium is missing, run `playwright install chromium` in the active virtualenv.
For a headed run without a display, use a desktop terminal or omit `--headed`.

Ticket availability can change immediately after a check. Confirm the live ticket
page before making plans.

## GitHub Pages

Serve the repository's default branch from `/docs`. The expected URL is
https://cheetahmonkey.github.io/IMAX/.

## Windows daily scheduling (WSL)

Run `scripts/install_windows_task.ps1` in Windows PowerShell to register
`IMAX Daily Refresh`. Its defaults target the `Ubuntu` WSL distribution, Linux
user `mmm`, and `/home/mmm/code/IMAX`; use the script parameters on another laptop.
The task publishes daily at **03:15 Windows local time**, wakes the laptop when
supported, runs on battery, and catches up missed runs at the owner's next sign-in.
It requires that Windows user to be signed in; it does not run before sign-in.
Failures retry three times, 15 minutes apart. Concurrent runs are prevented.

The action runs `scripts/run_imax_scheduled.sh --if-due`. A successful run records
`logs/last_success`, so additional sign-ins do not repeat the same daily refresh.
Logs are in `logs/imax_refresh.log`. The task automatically commits and pushes
only the generated publication files and current feature configuration.
Configure this repo's Git author identity and authenticate GitHub before enabling
it; verify with an on-demand run in Task Scheduler and check Last Run Result `0`.

For Healthchecks, create the ignored local file `.imax-scheduler.env`:

```bash
IMAX_HEALTHCHECK_URL=https://hc-ping.com/YOUR-CHECK-ID
```

Set its permissions to `600`. The wrapper sends `/start`, success after scan and
push, or `/fail` if the refresh fails. A failed success ping causes a task retry.
The ping URL is never committed. In the Healthchecks dashboard, configure the
check's schedule as `15 3 * * *` in `America/Los_Angeles` with an appropriate grace
period (for example, one hour). Laptop downtime beyond the grace period will alert.
The ping URL alone cannot configure that dashboard schedule.
