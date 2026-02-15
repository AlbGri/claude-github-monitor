# Claude Code GitHub Tracker

**Tracking Claude Code adoption across public GitHub repositories.**

This project monitors how widely [Claude Code](https://claude.ai/claude-code) is used across public GitHub repositories by analyzing commit metadata via the GitHub Search API. It runs daily, collecting the number of Claude-attributed commits and comparing them to the total number of public commits.

<!-- Badges placeholder -->

## Latest Data

| Date | Claude Commits* | Total Commits | % |
|------|----------------:|--------------:|--:|
| *Data collection in progress* | | | |

*\*Claude commits is the sum of API counts across separate search queries and may include cross-query duplicates. Total commits is the denominator for adoption rate.*

## Methodology

The tracker searches for public commits matching these patterns:

1. **`"Co-authored-by" "anthropic.com"`** -- Claude Code automatically appends a `Co-Authored-By` trailer with an `@anthropic.com` email to every commit it creates.
2. **`"Generated with Claude Code"`** -- Some users include this tag in commit messages (from the Claude Code README badge).

For each day, the script queries the [GitHub Commits Search API](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-commits) and reads the `total_count` field from the response. This requires only one API request per query (no pagination needed), making the data collection fast and efficient.

### Data accuracy

`claude_commits` is the sum of `total_count` values from two API queries. This is technically an **upper bound** because a commit matching both patterns is counted twice. However, the structural undercounting factors (see below) far outweigh this overlap, so the real number of Claude-authored commits is almost certainly **higher** than reported.

GitHub [documents](https://docs.github.com/en/rest/search/search#about-search) that `total_count` may be an **approximation** for very large result sets. The exact margin is unspecified.

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
python claude_github_tracker.py --date 2026-02-10

# Date range
python claude_github_tracker.py --from 2026-01-01 --to 2026-02-15

# Last 7 days (default)
python claude_github_tracker.py

# Skip dates already in the CSV
python claude_github_tracker.py --from 2026-01-01 --to 2026-02-15 --skip-existing
```

Output CSV is saved in `data/`.

## Automation

A GitHub Action (`.github/workflows/daily-track.yml`) runs the tracker automatically every day at 06:00 UTC. It:

1. Checks out the repository
2. Installs Python and dependencies
3. Runs the tracker for the previous day (complete data) with `--skip-existing`
4. Commits and pushes updated CSV back to the repository

The action uses a repository secret `GH_PAT` for API authentication. To set it up:

1. Go to your GitHub repo > **Settings** > **Secrets and variables** > **Actions**
2. Click **New repository secret**
3. Name: `GH_PAT`, Value: your GitHub Personal Access Token

Manual runs are also supported via the "Run workflow" button in the Actions tab.

## Limitations

- **Lower bound by design**: only **public** repositories are indexed. Private, internal, and enterprise usage is invisible.
- **Trailer opt-out**: users can disable or modify the `Co-Authored-By` trailer, making those commits undetectable.
- **Cross-query overlap**: `claude_commits` may double-count commits matching both search patterns (upper bound effect).
- **API approximation**: GitHub's `total_count` may be approximate for large result sets, affecting both numerator and denominator.
- **API rate limits**: the script uses 10 req/min (limit is 30 for authenticated users). Historical backfills take ~18 min per 365 days.

## Related

- [SemiAnalysis - "Anthropic - All Hands On Deck"](https://semianalysis.com/) -- Industry analysis referencing Claude Code's share of GitHub commits
- [GitHub Archive](https://www.gharchive.org/) -- Public dataset of all GitHub events (alternative data source for deeper analysis)
- [Anthropic](https://www.anthropic.com/) -- Maker of Claude Code

## License

[MIT](LICENSE)
