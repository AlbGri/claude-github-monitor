#!/usr/bin/env python3
"""
Verifica overlap tra le due query di ricerca Claude Code.

Scarica fino a 1000 commit per ciascuna query e confronta gli SHA
per determinare la percentuale di sovrapposizione reale.

Uso:
  python verify_overlap.py --date 2026-02-14
  python verify_overlap.py --date 2025-03-15  # pochi commit, overlap esatto
"""

import os
import sys
import time
import argparse
import logging

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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
SEARCH_COMMITS_URL = "https://api.github.com/search/commits"
REQUEST_DELAY = 6

QUERIES = {
    "co_authored": '"Co-authored-by" "anthropic.com"',
    "generated": '"Generated with Claude Code"',
}


def get_headers():
    headers = {
        "Accept": "application/vnd.github.cloak-preview+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def fetch_shas(date_str, query, label):
    """Scarica fino a 1000 SHA per una query+data."""
    full_query = f"{query} committer-date:{date_str}"
    shas = set()
    total_count = 0
    page = 1

    while True:
        params = {
            "q": full_query,
            "per_page": 100,
            "page": page,
            "sort": "committer-date",
            "order": "desc",
        }

        response = requests.get(SEARCH_COMMITS_URL, headers=get_headers(), params=params)

        if response.status_code == 403:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - int(time.time()), 10)
            log.warning("Rate limit, attendo %ds...", wait)
            time.sleep(wait)
            continue

        if response.status_code != 200:
            log.error("HTTP %d per %s", response.status_code, label)
            break

        data = response.json()
        total_count = data.get("total_count", 0)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            sha = item.get("sha", "")
            if sha:
                shas.add(sha)

        if len(items) < 100 or page * 100 >= min(total_count, 1000):
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return total_count, shas


def main():
    parser = argparse.ArgumentParser(description="Verifica overlap tra query Claude Code")
    parser.add_argument("--date", required=True, help="Data da verificare (YYYY-MM-DD)")
    args = parser.parse_args()

    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN non impostato, rate limit molto basso.")

    date_str = args.date
    results = {}

    for label, query in QUERIES.items():
        log.info("Scarico SHA per '%s' del %s...", label, date_str)
        total_count, shas = fetch_shas(date_str, query, label)
        results[label] = {"total_count": total_count, "shas": shas}
        log.info("  total_count=%d, SHA scaricati=%d", total_count, len(shas))
        time.sleep(REQUEST_DELAY)

    shas_co = results["co_authored"]["shas"]
    shas_gen = results["generated"]["shas"]
    overlap = shas_co & shas_gen
    union = shas_co | shas_gen

    print("\n" + "=" * 60)
    print(f"OVERLAP VERIFICATION - {date_str}")
    print("=" * 60)
    print(f"co_authored  total_count: {results['co_authored']['total_count']:>10,}")
    print(f"             SHA fetched: {len(shas_co):>10,}")
    print(f"generated    total_count: {results['generated']['total_count']:>10,}")
    print(f"             SHA fetched: {len(shas_gen):>10,}")
    print("-" * 60)
    print(f"Overlap (intersection):   {len(overlap):>10,}")
    print(f"Union (unique commits):   {len(union):>10,}")

    if shas_gen:
        pct_gen_in_co = len(overlap) / len(shas_gen) * 100
        print(f"% generated in co_authored: {pct_gen_in_co:>8.1f}%")

    if shas_co:
        pct_co_in_gen = len(overlap) / len(shas_co) * 100
        print(f"% co_authored in generated: {pct_co_in_gen:>8.1f}%")

    capped = (results["co_authored"]["total_count"] > 1000
              or results["generated"]["total_count"] > 1000)
    if capped:
        print("\nNota: almeno una query supera 1000 risultati.")
        print("L'overlap e' calcolato su un campione (max 1000 SHA per query).")
    else:
        print("\nDati completi: tutti gli SHA sono stati scaricati.")

    if shas_gen and len(overlap) / len(shas_gen) > 0.9:
        print("\nConclusione: overlap alto -> usare max(co_authored, generated)")
    elif shas_gen:
        print("\nConclusione: overlap basso -> la somma aggiunge informazione")

    print("=" * 60)


if __name__ == "__main__":
    main()
