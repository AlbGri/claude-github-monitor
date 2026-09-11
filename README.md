# Claude Code GitHub Tracker

**Tracking Claude Code adoption across public GitHub repositories.**

This project monitors how widely [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) is used across public GitHub repositories by analyzing commit metadata via the GitHub Search API. It runs daily, collecting the number of Claude-attributed commits and breaking them down by Claude model.

<!-- Badges placeholder -->

## Latest Data

**[Live Dashboard](https://albgri.github.io/claude-github-monitor/)** -- Daily commit volume split by model, with 7-day averages and a data table.

## Methodology

Claude Code appends a `Co-Authored-By` trailer with an `@anthropic.com` email to every commit it creates. The tracker counts those commits with the query `"Co-authored-by" "anthropic.com"`, reading the `total_count` field from the [GitHub Commits Search API](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-commits) -- one request per query, no pagination.

Since early January 2026 the trailer also names the model (`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`), so a second pass runs one query per model listed in `data/model_queries.csv` and produces a per-model breakdown. On 2026-09-05 those queries accounted for 99.3% of the day's total.

### Data accuracy

Every run checks **coverage**: the per-model counts divided by the day's total. A value below 95% means a model is missing from `data/model_queries.csv`; above 105% means a query phrase is matching more than it should. Both are logged as warnings.

Model phrases must always carry the full version number including the decimal. GitHub's search tokenizes `4.8`, so the phrase `Co-Authored-By: Claude Opus 4` also matches 4.6, 4.7 and 4.8 -- measured on 2026-09-05, 40,010 against the 39,774 of the three variants summed.

A name with no decimal cannot be separated that way, so `Sonnet 4` is the one phrase that carries the full trailer including `<noreply@anthropic.com>`. That form is exact but **not** a general fix: the trailer address is not always `noreply@anthropic.com`, and appending it drops Opus 5 by 29% and Fable 5 by 87%. Use it only to break a collision.

A single failed query invalidates the whole day rather than dropping one model. Skipping just the failed model looked safer until 2026-09-03 was written without Opus 5 -- 432,000 commits missing -- and `--skip-existing` then treated the day as complete.

Counts drift upward slightly when a date is re-read later, because GitHub's commit index is still catching up at capture time: 2026-09-05 was captured at 736,312 and read back six days later at 829,757. Structural undercounting (private repos, trailer opt-out) is far larger, so the real figure is in any case **higher** than reported.

### Why there is no adoption rate

Earlier versions divided Claude commits by the total number of public commits per day, obtained with a bare `committer-date:` query. That query has no search term, and for that degenerate case the Search API returns an estimate of the index size rather than a count: re-reading 2026-08-01 gave 7,718,879 against the 36,811,124 captured live, and two dates read in the same minute gave 8.8M for 4 August and 50.8M for 16 August. The metric was removed rather than published with a caveat. The historical column is still in git history.

## Setup

### Prerequisites

- Python 3.8+
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (free, no special scopes needed)

### Installation

```bash
git clone https://github.com/AlbGri/claude-github-monitor.git
cd claude-github-monitor
pip install -r requirements.txt
```

### Usage

Set your GitHub token:

```bash
# Linux/macOS
export GITHUB_TOKEN="ghp_yourtoken"

# Windows (cmd)
set GITHUB_TOKEN=ghp_yourtoken

# Windows (PowerShell)
$env:GITHUB_TOKEN = "ghp_yourtoken"
```

Run the tracker:

```bash
# Single day
python claude_github_tracker.py --date 2026-09-05

# Date range
python claude_github_tracker.py --from 2026-01-01 --to 2026-09-10

# Last 30 days, skipping what is already collected (default)
python claude_github_tracker.py --skip-existing

# Backfill only the per-model series, faster
python claude_github_tracker.py --from 2025-12-15 --to 2026-09-10 --models-only --rate 25
```

Two CSVs are produced:

| File | Columns |
|---|---|
| `data/claude_commits_daily.csv` | `date`, `co_authored` |
| `data/claude_commits_by_model.csv` | `date`, `model`, `commits` (long format; zero rows omitted) |

The per-model series starts on 2025-12-15. Before that the trailer did not name the model: on 2025-08-01 the unnamed form accounted for 18,448 commits out of 18,464.

`data/model_queries.csv` holds the search phrase for each model and is the one file to update when a new model ships.

## Automation

A GitHub Action (`.github/workflows/daily-track.yml`) runs the tracker automatically every day at 06:00 UTC. It:

1. Checks out the repository
2. Installs Python and dependencies
3. Runs the tracker with `--skip-existing` over a 30-day window, so a missed day is picked up on the next run instead of leaving a permanent hole
4. Commits and pushes both updated CSVs back to the repository

The tracker exits non-zero when no day could be written, so a dead token or a pattern that stopped matching fails the workflow visibly instead of leaving it green and empty.

The action uses a repository secret `GH_PAT` for API authentication. To set it up:

1. Go to your GitHub repo > **Settings** > **Secrets and variables** > **Actions**
2. Click **New repository secret**
3. Name: `GH_PAT`, Value: your GitHub Personal Access Token

Manual runs are also supported via the "Run workflow" button in the Actions tab.

## Limitations

- **Lower bound by design**: only **public** repositories are indexed. Private, internal, and enterprise usage is invisible.
- **Trailer opt-out**: users can disable or modify the `Co-Authored-By` trailer, making those commits undetectable.
- **Model coverage depends on config**: a model absent from `data/model_queries.csv` lands nowhere. The coverage check makes that visible in the logs, but it does not fix itself.
- **No denominator**: the tracker reports absolute volume, not a share of all GitHub activity. See *Why there is no adoption rate* above.
- **API rate limits**: the script defaults to 10 req/min (the limit is 30 for authenticated users) and issues one query per model per day. A full per-model backfill of 270 days takes about 3 hours at `--rate 25`.

## Related

- [GitHub Archive](https://www.gharchive.org/) -- Public dataset of all GitHub events (alternative data source for deeper analysis)
- [Anthropic](https://www.anthropic.com/) -- Maker of Claude Code

## Changelog

Notable changes are recorded in [CHANGELOG.md](CHANGELOG.md). Version 1.0.0 removed
the adoption-rate metric and added the per-model breakdown.

## License

[MIT](LICENSE)
