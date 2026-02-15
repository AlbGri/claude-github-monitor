#!/usr/bin/env python3
"""
Claude Code GitHub Tracker
--------------------------
Traccia l'adozione di Claude Code su GitHub analizzando i commit pubblici
che contengono "Co-authored-by" + pattern Anthropic/Claude.

Usa la GitHub Search API (commits endpoint).

Requisiti:
  - Python 3.8+
  - pip install requests
  - Un GitHub Personal Access Token (gratuito) impostato come variabile d'ambiente:
    export GITHUB_TOKEN="ghp_tuotoken"

Uso:
  # Singolo giorno
  python claude_github_tracker.py --date 2026-02-10

  # Range di date
  python claude_github_tracker.py --from 2026-01-01 --to 2026-02-15

  # Ultima settimana (default se nessun parametro)
  python claude_github_tracker.py

Note:
  - total_commits e' la somma dei conteggi API per ciascuna query di ricerca.
    Poiche' le query possono avere sovrapposizioni, il valore e' un upper bound.
  - distinct_repos e' il conteggio deduplicato dei repository e rappresenta
    la metrica piu' affidabile.
"""

import os
import sys
import csv
import logging
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installa requests: pip install requests")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# --- Configurazione ---

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
API_BASE = "https://api.github.com"
SEARCH_COMMITS_URL = f"{API_BASE}/search/commits"

# Pattern di ricerca per identificare commit di Claude Code
SEARCH_QUERIES = [
    '"Co-authored-by" "anthropic.com"',
    '"Generated with Claude Code"',
]

# File di output
OUTPUT_DIR = Path("data")
OUTPUT_CSV = OUTPUT_DIR / "claude_commits_daily.csv"
OUTPUT_REPOS_CSV = OUTPUT_DIR / "claude_repos_daily.csv"

# Rate limiting
REQUESTS_PER_MINUTE = 10  # conservativo (limite reale: 30 per autenticati)
REQUEST_DELAY = 60 / REQUESTS_PER_MINUTE


# --- Funzioni ---

def get_headers():
    """Costruisce gli header per le richieste all'API GitHub."""
    headers = {
        "Accept": "application/vnd.github.cloak-preview+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    else:
        log.warning("Nessun GITHUB_TOKEN impostato.")
        log.warning("Senza token il rate limit e' molto basso (10 req/min).")
        log.warning("Crea un token su https://github.com/settings/tokens")
    return headers


def search_commits_for_date(date_str, query):
    """
    Cerca commit per una data specifica con una query.
    Ritorna (total_count, set_repo_names, items_campione).
    """
    full_query = f"{query} committer-date:{date_str}"
    params = {
        "q": full_query,
        "per_page": 100,
        "page": 1,
        "sort": "committer-date",
        "order": "desc",
    }

    repos = set()
    total_count = 0
    sample_items = []
    page = 1

    while True:
        params["page"] = page
        response = requests.get(
            SEARCH_COMMITS_URL,
            headers=get_headers(),
            params=params,
        )

        if response.status_code == 403:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - int(time.time()), 10)
            log.warning("Rate limit raggiunto, attendo %ds...", wait)
            time.sleep(wait)
            continue

        if response.status_code == 422:
            log.error("Errore 422 per query: %s", full_query)
            break

        if response.status_code != 200:
            log.error("Errore %d: %s", response.status_code, response.text[:200])
            break

        data = response.json()
        total_count = data.get("total_count", 0)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            repo = item.get("repository", {}).get("full_name", "")
            if repo:
                repos.add(repo)
            if len(sample_items) < 5:
                sample_items.append({
                    "sha": item.get("sha", "")[:8],
                    "repo": repo,
                    "message": item.get("commit", {}).get("message", "")[:120],
                    "date": item.get("commit", {}).get("committer", {}).get("date", ""),
                })

        if len(items) < 100 or page * 100 >= min(total_count, 1000):
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return total_count, repos, sample_items


def collect_day_data(date_str):
    """
    Raccoglie dati per un singolo giorno, combinando tutte le query di ricerca.

    Nota: total_commits somma i conteggi API di query diverse, quindi puo'
    includere duplicati. distinct_repos e' deduplicato ed e' la metrica primaria.
    """
    all_repos = set()
    total_commits = 0
    all_samples = []

    for query in SEARCH_QUERIES:
        log.info("Cerco: %s per %s...", query, date_str)
        count, repos, samples = search_commits_for_date(date_str, query)
        log.info("  -> %d commit, %d repo distinti", count, len(repos))
        total_commits += count
        all_repos.update(repos)
        all_samples.extend(samples)
        time.sleep(REQUEST_DELAY)

    return {
        "date": date_str,
        "total_commits": total_commits,
        "distinct_repos": len(all_repos),
        "repos": sorted(all_repos),
        "samples": all_samples[:5],
    }


def load_existing_data():
    """Carica dati esistenti da entrambi i CSV per preservarli tra le esecuzioni."""
    existing = {}

    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing[row["date"]] = {
                    "date": row["date"],
                    "total_commits": int(row["total_commits"]),
                    "distinct_repos": int(row["distinct_repos"]),
                    "repos": [],
                    "samples": [],
                }

    if OUTPUT_REPOS_CSV.exists():
        with open(OUTPUT_REPOS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["date"] in existing:
                    existing[row["date"]]["repos"].append(row["repo"])

    return existing


def save_daily_data(all_data):
    """Salva i dati giornalieri nei CSV."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "total_commits", "distinct_repos"])
        writer.writeheader()
        for day in sorted(all_data, key=lambda x: x["date"]):
            writer.writerow({
                "date": day["date"],
                "total_commits": day["total_commits"],
                "distinct_repos": day["distinct_repos"],
            })

    with open(OUTPUT_REPOS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "repo"])
        writer.writeheader()
        for day in sorted(all_data, key=lambda x: x["date"]):
            for repo in day["repos"]:
                writer.writerow({"date": day["date"], "repo": repo})


def generate_date_range(from_date, to_date):
    """Genera lista di date tra from_date e to_date."""
    dates = []
    current = from_date
    while current <= to_date:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def print_summary(all_data):
    """Stampa un riepilogo dei dati raccolti."""
    print("\n" + "=" * 60)
    print("RIEPILOGO")
    print("=" * 60)
    print(f"{'Data':<14} {'Commit':>10} {'Repo distinti':>15}")
    print("-" * 60)
    for day in sorted(all_data, key=lambda x: x["date"]):
        print(f"{day['date']:<14} {day['total_commits']:>10} {day['distinct_repos']:>15}")
    print("-" * 60)

    if all_data:
        total_commits = sum(d["total_commits"] for d in all_data)
        all_repos = set()
        for d in all_data:
            all_repos.update(d["repos"])
        print(f"{'TOTALE':<14} {total_commits:>10} {len(all_repos):>15}")

    if all_data and all_data[0].get("samples"):
        print("\nEsempi di commit trovati:")
        for s in all_data[0]["samples"][:3]:
            print(f"  [{s['sha']}] {s['repo']}")
            print(f"           {s['message'][:80]}")

    print(f"\nDati salvati in: {OUTPUT_CSV}")
    print(f"Lista repo in:  {OUTPUT_REPOS_CSV}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Traccia l'adozione di Claude Code su GitHub")
    parser.add_argument("--date", help="Singola data (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_date", help="Data inizio range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="Data fine range (YYYY-MM-DD)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Salta date gia' presenti nel CSV")
    args = parser.parse_args()

    # Determina il range di date
    if args.date:
        dates = [args.date]
    elif args.from_date:
        from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(args.to_date, "%Y-%m-%d") if args.to_date else datetime.now()
        dates = generate_date_range(from_dt, to_dt)
    else:
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=7)
        dates = generate_date_range(from_dt, to_dt)

    # Carica dati esistenti e merge con i nuovi
    existing = load_existing_data()
    if args.skip_existing:
        dates = [d for d in dates if d not in existing]

    if not dates:
        log.info("Nessuna data da processare.")
        return

    log.info("Claude Code GitHub Tracker")
    log.info("Date da analizzare: %s -> %s (%d giorni)", dates[0], dates[-1], len(dates))
    log.info("Token GitHub: %s", "configurato" if GITHUB_TOKEN else "MANCANTE")

    # Parti dai dati esistenti, i nuovi verranno aggiunti/aggiornati
    all_data = dict(existing)
    new_data = []

    for i, date_str in enumerate(dates):
        log.info("[%d/%d] Analisi %s...", i + 1, len(dates), date_str)
        try:
            day_data = collect_day_data(date_str)
            all_data[date_str] = day_data
            new_data.append(day_data)
        except Exception as e:
            log.error("Errore per %s: %s", date_str, e)
            error_data = {
                "date": date_str,
                "total_commits": 0,
                "distinct_repos": 0,
                "repos": [],
                "samples": [],
            }
            all_data[date_str] = error_data
            new_data.append(error_data)

        # Salva progressivamente (tutti i dati: esistenti + nuovi)
        save_daily_data(list(all_data.values()))

        if i < len(dates) - 1:
            time.sleep(REQUEST_DELAY)

    print_summary(new_data)


if __name__ == "__main__":
    main()
