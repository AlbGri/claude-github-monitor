# Claude Code GitHub Tracker

**Tracking Claude Code adoption across public GitHub repositories.**

This project monitors how widely [Claude Code](https://claude.ai/claude-code) is used across public GitHub repositories by analyzing commit metadata via the GitHub Search API. It runs daily, collecting the number of repositories where Claude Code contributed to at least one commit.

<!-- Badges placeholder -->

## Latest Data

| Date       | Distinct Repos | Total Commits* |
|------------|---------------:|---------------:|
| 2026-02-10 |            987 |        172,676 |

*\*Total commits is the sum of API counts across separate search queries and may include cross-query duplicates. Distinct repos is deduplicated and is the primary reliable metric.*

## Methodology

The tracker searches for public commits matching these patterns:

1. **`"Co-authored-by" "anthropic.com"`** -- Claude Code automatically appends a `Co-Authored-By` trailer with an `@anthropic.com` email to every commit it creates.
2. **`"Generated with Claude Code"`** -- Some users include this tag in commit messages (from the Claude Code README badge).

For each day, the script queries the [GitHub Commits Search API](https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-commits), paginates through results (up to the API limit of 1,000 items per query), and extracts repository names. Repositories are deduplicated across queries using a set, making `distinct_repos` the most accurate metric.

### Known limitations of the methodology

- The API returns a maximum of **1,000 results per query**. Days with more matching commits will have accurate `total_count` from the API but incomplete repository coverage.
- Only **public repositories** are indexed. Private and internal repos are excluded.
- Users can **disable or modify** the Co-Authored-By trailer, so the real adoption is higher than what this tracker captures.
- `total_commits` sums counts from two separate queries that may overlap, making it an **upper bound**.

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

Output CSVs are saved in `data/`.

## Automation

A GitHub Action (`.github/workflows/daily-track.yml`) runs the tracker automatically every day at 06:00 UTC. It:

1. Checks out the repository
2. Installs Python and dependencies
3. Runs the tracker for the current date with `--skip-existing`
4. Commits and pushes updated CSVs back to the repository

The action uses a repository secret `GH_PAT` for API authentication. To set it up:

1. Go to your GitHub repo > **Settings** > **Secrets and variables** > **Actions**
2. Click **New repository secret**
3. Name: `GH_PAT`, Value: your GitHub Personal Access Token

Manual runs are also supported via the "Run workflow" button in the Actions tab.

## Limitations

- **Underestimate**: this tracker captures a lower bound of real Claude Code usage. Private repos, modified trailers, and the 1,000-result API cap all contribute to undercounting.
- **API rate limits**: authenticated users get 30 search requests per minute. The script uses a conservative 10 req/min to avoid hitting limits.
- **Public repos only**: no visibility into enterprise or private usage.
- **Cross-query duplicates**: `total_commits` may count the same commit twice if it matches both search patterns. `distinct_repos` is deduplicated.

## Related

- [SemiAnalysis - "Anthropic - All Hands On Deck"](https://semianalysis.com/) -- Industry analysis referencing Claude Code's share of GitHub commits
- [GitHub Archive](https://www.gharchive.org/) -- Public dataset of all GitHub events (alternative data source for deeper analysis)
- [Anthropic](https://www.anthropic.com/) -- Maker of Claude Code

## License

[MIT](LICENSE)
