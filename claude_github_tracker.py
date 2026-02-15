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

Output CSV (data/claude_commits_daily.csv):
  date, claude_commits, total_commits

Note:
  - claude_commits e' la somma dei conteggi API per ciascuna query di ricerca.
    Poiche' le query possono avere sovrapposizioni, il valore e' un upper bound.
  - total_commits e' il numero totale di commit pubblici su GitHub per quel giorno
    (denominatore per calcolare la percentuale di adozione).
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
    return headers


def get_commit_count(date_str, query=""):
    """
    Interroga l'API per il total_count di commit che matchano la query per una data.

    Usa una singola richiesta con per_page=1 per leggere solo total_count,
    senza scaricare i dettagli degli item.
    """
    q = f"{query} committer-date:{date_str}" if query else f"committer-date:{date_str}"
    params = {"q": q, "per_page": 1}

    try:
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
            return get_commit_count(date_str, query)

        if response.status_code == 200:
            count = response.json().get("total_count", 0)
            return count

        log.warning("Query failed for %s (HTTP %d): %s", date_str, response.status_code, q)
    except Exception as e:
        log.error("Error querying %s: %s", date_str, e)

    return 0


def collect_day_data(date_str):
    """
    Raccoglie dati per un singolo giorno.

    Per ciascuna query di ricerca legge total_count dall'API (una sola richiesta
    per query), poi somma i conteggi. Infine recupera il totale di tutti i commit
    pubblici come denominatore.

    Nota: claude_commits somma i conteggi API di query diverse, quindi puo'
    includere duplicati cross-query ed e' un upper bound.
    """
    claude_commits = 0

    for query in SEARCH_QUERIES:
        log.info("Cerco: %s per %s...", query, date_str)
        count = get_commit_count(date_str, query)
        log.info("  -> %d commit", count)
        claude_commits += count
        time.sleep(REQUEST_DELAY)

    # Denominatore: tutti i commit pubblici del giorno
    log.info("Recupero total commits per %s...", date_str)
    time.sleep(REQUEST_DELAY)
    total_commits = get_commit_count(date_str)
    log.info("  Total commits on %s: %d", date_str, total_commits)

    return {
        "date": date_str,
        "claude_commits": claude_commits,
        "total_commits": total_commits,
    }


def load_existing_data():
    """Carica dati esistenti dal CSV per preservarli tra le esecuzioni."""
    existing = {}

    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing[row["date"]] = {
                    "date": row["date"],
                    "claude_commits": int(row["claude_commits"]),
                    "total_commits": int(row["total_commits"]),
                }

    return existing


def save_daily_data(all_data):
    """Salva i dati giornalieri nel CSV."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "claude_commits", "total_commits"]
        )
        writer.writeheader()
        for day in sorted(all_data, key=lambda x: x["date"]):
            writer.writerow({
                "date": day["date"],
                "claude_commits": day["claude_commits"],
                "total_commits": day["total_commits"],
            })


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
    print("\n" + "=" * 65)
    print("RIEPILOGO")
    print("=" * 65)
    print(f"{'Data':<14} {'Claude Commits':>15} {'Total Commits':>15} {'%':>8}")
    print("-" * 65)
    for day in sorted(all_data, key=lambda x: x["date"]):
        pct = ""
        if day["total_commits"] > 0:
            pct = f"{day['claude_commits'] / day['total_commits'] * 100:.2f}%"
        print(
            f"{day['date']:<14} {day['claude_commits']:>15,}"
            f" {day['total_commits']:>15,} {pct:>8}"
        )
    print("-" * 65)

    if all_data:
        total_claude = sum(d["claude_commits"] for d in all_data)
        total_all = sum(d["total_commits"] for d in all_data)
        pct = f"{total_claude / total_all * 100:.2f}%" if total_all > 0 else ""
        print(
            f"{'TOTALE':<14} {total_claude:>15,}"
            f" {total_all:>15,} {pct:>8}"
        )

    print(f"\nDati salvati in: {OUTPUT_CSV}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Traccia l'adozione di Claude Code su GitHub")
    parser.add_argument("--date", help="Singola data (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_date", help="Data inizio range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="Data fine range (YYYY-MM-DD)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Salta date gia' presenti nel CSV")
    args = parser.parse_args()

    if not GITHUB_TOKEN:
        log.warning("Nessun GITHUB_TOKEN impostato.")
        log.warning("Senza token il rate limit e' molto basso (10 req/min).")
        log.warning("Crea un token su https://github.com/settings/tokens")

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
                "claude_commits": 0,
                "total_commits": 0,
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
