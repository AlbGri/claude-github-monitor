#!/usr/bin/env python3
"""
Claude Code GitHub Tracker
--------------------------
Traccia l'adozione di Claude Code su GitHub analizzando i commit pubblici
che contengono il trailer Co-Authored-By di Anthropic.

Usa la GitHub Search API (commits endpoint).

Requisiti:
  - Python 3.10+
  - pip install requests
  - Un GitHub Personal Access Token (gratuito) impostato come variabile d'ambiente:
    export GITHUB_TOKEN="ghp_tuotoken"

Uso:
  # Singolo giorno
  python claude_github_tracker.py --date 2026-09-05

  # Range di date
  python claude_github_tracker.py --from 2026-01-01 --to 2026-09-10

  # Ultimi 30 giorni mancanti (default)
  python claude_github_tracker.py --skip-existing

  # Backfill della sola serie per modello, piu' veloce
  python claude_github_tracker.py --from 2025-12-15 --to 2026-09-10 --models-only --rate 20

Output:
  data/claude_commits_daily.csv     date, co_authored
  data/claude_commits_by_model.csv  date, model, commits (formato lungo)

Note:
  - Dal 2026-01-08 il trailer nomina il modello ("Co-Authored-By: Claude Opus 5 <...>").
    Le query per modello sono configurate in data/model_queries.csv.
  - La copertura (somma per modello / co_authored) e' il presidio contro l'obsolescenza
    di quel file: se scende sotto il 95% probabilmente e' uscito un modello nuovo.
  - Il denominatore "tutti i commit pubblici" e' stato rimosso: la Search API non lo
    misura, per una query senza termini restituisce una stima dell'indice che varia
    di un fattore 5 per la stessa data. Lo storico resta in git.
"""

import os
import sys
import csv
import logging
import time
import argparse
import statistics
from datetime import datetime, timedelta, timezone
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

QUERY_CO_AUTHORED = '"Co-authored-by" "anthropic.com"'

OUTPUT_DIR = Path("data")
OUTPUT_CSV = OUTPUT_DIR / "claude_commits_daily.csv"
MODEL_CSV = OUTPUT_DIR / "claude_commits_by_model.csv"
MODEL_QUERIES_CSV = OUTPUT_DIR / "model_queries.csv"

CSV_FIELDS = ["date", "co_authored"]
MODEL_CSV_FIELDS = ["date", "model", "commits"]

# Limite reale della Search API autenticata: 30 req/min.
DEFAULT_REQUESTS_PER_MINUTE = 10

# Soglie di allarme
MIN_MODEL_COVERAGE = 0.95
MAX_MODEL_COVERAGE = 1.05
MAX_DEVIATION = 0.5
MAX_403_RETRIES = 3


# --- API ---

def get_headers() -> dict[str, str]:
    """Costruisce gli header per le richieste all'API GitHub."""
    headers = {
        "Accept": "application/vnd.github.cloak-preview+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def get_commit_count(date_str: str, query: str) -> int | None:
    """Interroga l'API per il total_count di commit che matchano la query per una data.

    Usa una singola richiesta con per_page=1 per leggere solo total_count, senza
    scaricare i dettagli degli item.

    Args:
        date_str: Data in formato YYYY-MM-DD.
        query: Termini di ricerca gia' quotati, senza il qualificatore di data.

    Returns:
        Il numero di commit, che puo' essere legittimamente 0, oppure None se la
        richiesta e' fallita. Distinguere i due casi e' essenziale: un errore
        silenziosamente convertito in 0 ha tenuto nascosta per otto mesi la morte
        del pattern "Generated with Claude Code".
    """
    params = {"q": f"{query} committer-date:{date_str}", "per_page": 1}

    for attempt in range(MAX_403_RETRIES):
        try:
            response = requests.get(SEARCH_COMMITS_URL, headers=get_headers(), params=params)
        except Exception as e:
            log.error("Errore di rete per %s (%s): %s", date_str, query, e)
            return None

        if response.status_code == 200:
            return response.json().get("total_count", 0)

        if response.status_code == 403:
            reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
            wait = max(reset_time - int(time.time()), 10)
            log.warning(
                "Rate limit raggiunto (tentativo %d/%d), attendo %ds...",
                attempt + 1, MAX_403_RETRIES, wait,
            )
            time.sleep(wait)
            continue

        log.error(
            "Query fallita per %s (HTTP %d): %s",
            date_str, response.status_code, params["q"],
        )
        return None

    log.error("Rate limit non rientrato dopo %d tentativi per %s", MAX_403_RETRIES, date_str)
    return None


# --- Configurazione modelli ---

def load_model_queries() -> list[tuple[str, str]]:
    """Carica le query per modello da data/model_queries.csv.

    Le frasi devono sempre includere il numero di versione completo con il decimale.
    La ricerca GitHub spezza "4.8" in token, quindi la frase "Co-Authored-By: Claude
    Opus 4" matcha anche 4.6, 4.7 e 4.8: misurato il 2026-09-05, 40.010 contro i
    39.774 della somma delle tre varianti. Una frase senza decimale gonfia la
    copertura sopra il 100% e falsa la serie.

    Returns:
        Lista di coppie (nome modello, frase di ricerca senza virgolette).
    """
    if not MODEL_QUERIES_CSV.exists():
        log.error("File mancante: %s", MODEL_QUERIES_CSV)
        return []

    with open(MODEL_QUERIES_CSV, "r", encoding="utf-8") as f:
        return [(row["model"], row["phrase"]) for row in csv.DictReader(f)]


# --- Raccolta ---

def collect_model_data(
    date_str: str, model_queries: list[tuple[str, str]], delay: float
) -> dict[str, int] | None:
    """Raccoglie i conteggi per modello di un singolo giorno.

    Una sola query fallita invalida il giorno intero. Saltare il singolo modello
    sembrava piu' robusto, ma il 2026-09-03 e' stato scritto senza Opus 5 - 432.000
    commit persi in un giorno - e da quel momento --skip-existing lo considerava
    completo. Meglio non scrivere nulla e riprovare alla corsa successiva.

    Returns:
        La mappa modello -> commit, senza i modelli a zero per tenere compatto il
        CSV, oppure None se una qualsiasi query e' fallita.
    """
    counts = {}

    for i, (model, phrase) in enumerate(model_queries):
        count = get_commit_count(date_str, f'"{phrase}"')
        if count is None:
            log.warning("  %s: query fallita, giorno invalidato", model)
            return None
        if count > 0:
            counts[model] = count

        if i < len(model_queries) - 1:
            time.sleep(delay)

    return counts


def check_deviation(history: dict[str, int], date_str: str, value: int) -> None:
    """Segnala uno scostamento anomalo rispetto alla mediana dei 7 giorni precedenti.

    Il dato viene comunque scritto: uno scostamento puo' essere crescita vera. Serve
    solo a rendere visibile nel log un eventuale cambio di pattern.
    """
    previous = [history[d] for d in sorted(history) if d < date_str][-7:]
    if len(previous) < 7:
        return

    median = statistics.median(previous)
    if median > 0 and abs(value - median) / median > MAX_DEVIATION:
        log.warning(
            "  %s: scostamento %.0f%% dalla mediana 7gg (%d vs %d)",
            date_str, (value - median) / median * 100, value, median,
        )


# --- Persistenza ---

def load_existing_data() -> dict[str, int]:
    """Carica il CSV principale. Tollera colonne extra da checkout con schema vecchio."""
    existing = {}

    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = int(row["co_authored"])
                except (KeyError, TypeError, ValueError):
                    log.warning("Riga non valida nel CSV principale, ignorata: %s", row)

    return existing


def load_existing_models() -> dict[str, dict[str, int]]:
    """Carica il CSV per modello in una mappa data -> {modello: commit}."""
    existing: dict[str, dict[str, int]] = {}

    if MODEL_CSV.exists():
        with open(MODEL_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing.setdefault(row["date"], {})[row["model"]] = int(row["commits"])
                except (KeyError, TypeError, ValueError):
                    log.warning("Riga non valida nel CSV per modello, ignorata: %s", row)

    return existing


def save_daily_data(all_data: dict[str, int]) -> None:
    """Salva il CSV principale, ordinato per data."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for date_str in sorted(all_data):
            writer.writerow({"date": date_str, "co_authored": all_data[date_str]})


def save_model_data(all_models: dict[str, dict[str, int]]) -> None:
    """Salva il CSV per modello in formato lungo, ordinato per data e nome modello.

    L'ordinamento per nome e non per volume tiene stabili i diff in git.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    with open(MODEL_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MODEL_CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for date_str in sorted(all_models):
            for model in sorted(all_models[date_str]):
                writer.writerow({
                    "date": date_str,
                    "model": model,
                    "commits": all_models[date_str][model],
                })


# --- Output ---

def utc_today() -> datetime:
    """Data odierna in UTC, come la vede committer-date nella Search API.

    La GitHub Action gira in UTC, una macchina locale quasi mai: usando l'ora
    locale, una corsa serale in Europa chiederebbe un giorno UTC ancora in corso e
    scriverebbe dati parziali, che --skip-existing poi non correggerebbe piu'.
    """
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day)


def generate_date_range(from_date: datetime, to_date: datetime) -> list[str]:
    """Genera la lista di date tra from_date e to_date, estremi inclusi."""
    dates = []
    current = from_date
    while current <= to_date:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def print_summary(processed: list[str], all_data: dict[str, int],
                  all_models: dict[str, dict[str, int]]) -> None:
    """Stampa un riepilogo dei giorni processati in questa esecuzione."""
    print("\n" + "=" * 78)
    print("RIEPILOGO")
    print("=" * 78)
    print(f"{'Data':<12} {'Co-Authored':>13} {'Copertura':>10}  {'Modello prevalente':<22}")
    print("-" * 78)

    for date_str in sorted(processed):
        co = all_data.get(date_str, 0)
        models = all_models.get(date_str, {})
        coverage = f"{sum(models.values()) / co * 100:.1f}%" if co and models else "-"
        top = max(models, key=models.get) if models else "-"
        print(f"{date_str:<12} {co:>13,} {coverage:>10}  {top:<22}")

    print("-" * 78)
    print(f"Giorni processati: {len(processed)}")
    print(f"Dati salvati in: {OUTPUT_CSV} e {MODEL_CSV}")


# --- Main ---

def main() -> None:
    parser = argparse.ArgumentParser(description="Traccia l'adozione di Claude Code su GitHub")
    parser.add_argument("--date", help="Singola data (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_date", help="Data inizio range (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="Data fine range (YYYY-MM-DD)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Salta date gia' presenti")
    parser.add_argument("--models-only", action="store_true",
                        help="Raccoglie solo la serie per modello, per date gia' nel CSV")
    parser.add_argument("--only-model", metavar="NOME",
                        help="Limita la raccolta a un solo modello, lasciando intatti "
                             "gli altri conteggi gia' presenti per quelle date")
    parser.add_argument("--rate", type=int, default=DEFAULT_REQUESTS_PER_MINUTE,
                        help=f"Richieste al minuto (default {DEFAULT_REQUESTS_PER_MINUTE}, max 30)")
    args = parser.parse_args()

    if not GITHUB_TOKEN:
        log.warning("Nessun GITHUB_TOKEN impostato.")
        log.warning("Senza token il rate limit e' molto basso (10 req/min).")
        log.warning("Crea un token su https://github.com/settings/tokens")

    delay = 60 / max(1, min(args.rate, 30))

    model_queries = load_model_queries()
    if not model_queries:
        log.error("Nessuna query per modello configurata, impossibile procedere.")
        sys.exit(1)

    if args.only_model:
        model_queries = [q for q in model_queries if q[0] == args.only_model]
        if not model_queries:
            log.error("Modello '%s' non presente in %s", args.only_model, MODEL_QUERIES_CSV)
            sys.exit(1)

    if args.date:
        dates = [args.date]
    elif args.from_date:
        from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(args.to_date, "%Y-%m-%d") if args.to_date else utc_today()
        dates = generate_date_range(from_dt, to_dt)
    else:
        # Finestra larga: con --skip-existing costa un giorno solo, ma permette di
        # recuperare da un'interruzione del workflow fino a 30 giorni.
        to_dt = utc_today() - timedelta(days=1)  # ieri, per evitare dati parziali
        from_dt = to_dt - timedelta(days=30)
        dates = generate_date_range(from_dt, to_dt)

    all_data = load_existing_data()
    all_models = load_existing_models()

    if args.skip_existing:
        # Una data e' "fatta" solo se ha entrambe le serie: altrimenti riprendere un
        # backfill interrotto salterebbe i giorni a cui manca la parte per modello.
        if args.models_only:
            dates = [d for d in dates if d not in all_models]
        else:
            dates = [d for d in dates if d not in all_data or d not in all_models]

    if not dates:
        log.info("Nessuna data da processare.")
        return

    log.info("Claude Code GitHub Tracker")
    log.info("Date da analizzare: %s -> %s (%d giorni)", dates[0], dates[-1], len(dates))
    log.info("Modelli configurati: %d | %d req/min", len(model_queries), args.rate)
    log.info("Token GitHub: %s", "configurato" if GITHUB_TOKEN else "MANCANTE")

    processed = []

    for i, date_str in enumerate(dates):
        log.info("[%d/%d] Analisi %s...", i + 1, len(dates), date_str)
        try:
            if args.models_only:
                co_authored = all_data.get(date_str)
                if co_authored is None:
                    raise RuntimeError("data non presente nel CSV principale")
                if co_authored == 0:
                    raise RuntimeError("co_authored=0 nel CSV: rileggere il giorno senza --models-only")
            else:
                co_authored = get_commit_count(date_str, QUERY_CO_AUTHORED)
                if co_authored is None:
                    raise RuntimeError("query co_authored fallita")
                if co_authored == 0:
                    raise RuntimeError("co_authored=0: token scaduto o pattern non piu' valido")
                log.info("  co_authored: %d", co_authored)
                check_deviation(all_data, date_str, co_authored)
                all_data[date_str] = co_authored
                time.sleep(delay)

            models = collect_model_data(date_str, model_queries, delay)
            if models is None:
                raise RuntimeError("query per modello fallita")
            if not models:
                raise RuntimeError("nessun conteggio per modello raccolto")

            if args.only_model:
                # Aggiorna le sole chiavi richieste: gli altri modelli del giorno non
                # sono stati interrogati e sovrascrivere il giorno li cancellerebbe.
                day = all_models.setdefault(date_str, {})
                for model, _ in model_queries:
                    if model in models:
                        day[model] = models[model]
                    else:
                        day.pop(model, None)
            else:
                all_models[date_str] = models
                day = models

            coverage = sum(day.values()) / co_authored
            if coverage < MIN_MODEL_COVERAGE:
                log.warning(
                    "  copertura per modello %.1f%%: probabile modello non in %s",
                    coverage * 100, MODEL_QUERIES_CSV,
                )
            elif coverage > MAX_MODEL_COVERAGE:
                log.warning(
                    "  copertura per modello %.1f%%: probabile collisione di prefisso in %s",
                    coverage * 100, MODEL_QUERIES_CSV,
                )
            else:
                log.info("  copertura per modello: %.1f%%", coverage * 100)

            processed.append(date_str)
        except Exception as e:
            log.error("Errore per %s: %s, giorno saltato.", date_str, e)

        # Salvataggio progressivo: rende il backfill interrompibile e riprendibile.
        save_daily_data(all_data)
        save_model_data(all_models)

        if i < len(dates) - 1:
            time.sleep(delay)

    if not processed:
        log.error("Nessun giorno scritto su %d richiesti.", len(dates))
        sys.exit(1)

    print_summary(processed, all_data, all_models)


if __name__ == "__main__":
    main()
