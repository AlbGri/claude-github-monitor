# Changelog

Notable changes to this project. Dates are the day the change went live.

## 1.0.0 -- 2026-09-12

The measurement was reworked after a review found the published dashboard was
showing a picture that inverted reality.

### Removed

- **Adoption rate and the `total_commits` denominator.** The denominator came from
  a `committer-date:` query with no search term, and for that degenerate case the
  Search API returns an estimate of the index size rather than a count. Re-reading
  2026-08-01 gave 7,718,879 against the 36,811,124 captured live, and two dates
  read in the same minute gave 8.8M for 4 August against 50.8M for 16 August. The
  dashboard had been reporting 34.3M daily commits against a real GitHub volume of
  3-9M, and an adoption rate falling from 5.94% in May to 1.08% in August while
  Claude commits were more than doubling. The metric is gone rather than published
  with a caveat.
- **The `generated` column.** `"Generated with Claude Code"` stopped being written
  to commit messages on 2026-01-08: the ratio against `co_authored` fell from 0.996
  to 0.474 that day and to 0.005 by September. It was consuming a third of the
  daily API budget for 0.5% of the signal.
- `data/model_releases.csv` and `verify_overlap.py`, both superseded.

### Added

- **Per-model breakdown.** Since early January 2026 the trailer names the model, so
  `data/claude_commits_by_model.csv` records one row per model per day, backfilled
  to 2025-12-15. All 270 days land inside the 95-105% coverage band. Measured share
  over the window: Opus 4.8 18.2%, Sonnet 4.6 15.4%, Opus 4.6 14.9%, Opus 5 14.6%,
  Opus 4.7 10.6%, Fable 5 10.4%, Sonnet 5 6.7%, Opus 4.5 3.8%.
- **Coverage check.** Every run divides the per-model sum by the day's total and
  warns below 95%, which means a model is missing from `data/model_queries.csv`, or
  above 105%, which means a query phrase is matching more than it should.
- **A data table** on the dashboard, listing the last 14 days per model.

### Changed

- The dashboard is a stacked area per model on a single axis, replacing the
  dual-axis line and the static release bands. KPI cards now show growth against 30
  days ago and the leading model of the last 7 days.
- `data/claude_commits_daily.csv` is `date,co_authored`. The earlier four-column
  form remains at `git show 8d7c219:data/claude_commits_daily.csv`.
- `co_authored` was re-read for 2025-12-15 to 2026-09-10 so both series come from
  one reading of the index, a revision of +9.1% at the median. This also corrected
  old outliers: 2026-06-28 had been recorded at 997,018 between neighbours of
  578,806 and 535,581, and reads 498,761 today.

### Fixed

- **Silent failure.** Every API error used to return `0`, indistinguishable from a
  genuine zero. Errors now return no value, the day is not written, and the script
  exits non-zero so the workflow fails visibly instead of staying green and empty.
- **Partial days written on a failed query.** On 2026-09-03 the Opus 5 query hit
  the rate limit and the day was written without it -- 432,000 commits missing --
  after which `--skip-existing` treated the date as complete. A failed query now
  invalidates the whole day.
- **Local time instead of UTC.** The default window used the machine clock, so an
  evening run in Europe would request a UTC day still in progress and write partial
  data. This is how the row removed in February got in.
- **Unbounded recursion** in the rate-limit handler, now a three-attempt loop.
- The self-healing window went from 8 to 30 days, so an outage longer than a week
  no longer leaves a permanent hole.
- The daily workflow was staging only one of the two data files.

## 0.3.0 -- 2026-02-22

- Model release bands loaded from a CSV, with the model shown in the chart tooltip.

## 0.2.0 -- 2026-02-16

- 2025 historical data backfilled; 7-day averages and a full timeline on the chart.
- Fullscreen mode, release bands, Claude commits on the left axis, a fourth KPI card.
- Self-healing in the daily action after an expired token wrote a row of zeroes.

## 0.1.0 -- 2026-02-15

- Daily tracker over the GitHub Commits Search API, GitHub Action, and a GitHub
  Pages dashboard.
- `co_authored` and `generated` recorded as separate columns.
