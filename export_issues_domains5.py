#!/usr/bin/env python3
import csv
import sys
import requests
import argparse
import os
from urllib.parse import urlparse
from datetime import datetime

REPO = "svemailproject/TheySoldMyEmail"
API_URL = f"https://api.github.com/repos/{REPO}/issues"
PER_PAGE = 100

LATEST_FILENAME = "issues-latest.csv"

# Häufige Multi-Part-TLDs für bessere Root-Domain-Erkennung
MULTI_PART_TLDS = {
    "co.uk", "org.uk", "gov.uk", "ac.uk",
    "com.au", "net.au", "org.au",
    "co.nz",
    "com.br", "com.ar", "com.mx",
    "co.jp",
}


def extract_domains(title: str):
    """
    Nimmt den Issue-Titel und gibt zurück:
    - domain: normalisierte Domain/Host (ohne Schema, mit evtl. www/subdomain)
    - root_domain: ohne www. und ohne Subdomains (soweit heuristisch erkennbar)
    Falls nichts Verwertbares gefunden wird:
    - domain und root_domain = leerer String
    """
    original = (title or "").strip()
    if not original:
        return "", ""

    tokens = original.split()
    candidate = None

    # Bevorzugt ein Token mit Punkt oder Slash
    for tok in tokens:
        if "." in tok or "/" in tok:
            candidate = tok
            break

    # Wenn nichts mit Punkt gefunden: nimm erstes Wort als Notlösung
    if candidate is None and tokens:
        candidate = tokens[0]
    elif candidate is None:
        return "", ""

    # Randzeichen entfernen
    candidate = candidate.strip(" ,;()[]{}<>\"'")

    # Für urlparse: Schema ergänzen falls fehlt
    if candidate.startswith(("http://", "https://")):
        parsed = urlparse(candidate)
    else:
        parsed = urlparse("http://" + candidate)

    host = parsed.netloc or parsed.path

    # Userinfo und Port entfernen
    if "@" in host:
        host = host.split("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]

    host = host.strip().lower()

    # Wenn kein Punkt: vermutlich keine Domain
    if not host or "." not in host:
        return "", ""

    domain = host

    # www. entfernen
    if host.startswith("www."):
        without_www = host[4:]
    else:
        without_www = host

    parts = without_www.split(".")
    root_domain = without_www

    # Subdomains via Heuristik entfernen
    if len(parts) > 2:
        last_two = ".".join(parts[-2:])
        if last_two in MULTI_PART_TLDS and len(parts) >= 3:
            root_domain = ".".join(parts[-3:])
        else:
            root_domain = last_two

    return domain, root_domain


def fetch_open_issues():
    """
    Holt alle offenen Issues (ohne Pull Requests) mit Pagination.
    """
    page = 1
    headers = {
        # Optional:
        # "Authorization": "Bearer YOUR_TOKEN_HERE"
    }

    while True:
        params = {
            "state": "open",
            "per_page": PER_PAGE,
            "page": page,
        }
        r = requests.get(API_URL, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        issues = r.json()

        if not issues:
            break

        for issue in issues:
            # PRs rausfiltern
            if "pull_request" in issue:
                continue
            yield issue

        if "next" in r.links:
            page += 1
        else:
            break


def rotate_latest_if_exists():
    """
    Wenn LATEST_FILENAME existiert, nach issues-YYYYMMDD_HHMMSS.csv umbenennen.
    """
    if os.path.exists(LATEST_FILENAME):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived = f"issues-{ts}.csv"
        os.rename(LATEST_FILENAME, archived)
        return archived
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Exportiert offene GitHub-Issues mit Domains als CSV."
    )
    parser.add_argument(
        "-o", "--output",
        help="Pfad zur Ausgabedatei. Ohne Angabe: nutzt issues-latest.csv mit Auto-Rotation."
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Schreibt CSV auf stdout (keine Dateien, kein Auto-Rotation)."
    )
    args = parser.parse_args()

    # stdout-Modus: keine Rotation, kein Dateikram
    if args.stdout:
        out = sys.stdout
        close_out = False
    else:
        # Wenn explizit -o genutzt wird: keine Auto-Rotation, einfach in diese Datei schreiben
        if args.output:
            filename = args.output
        else:
            # Auto-Rotation für issues-latest.csv
            archived = rotate_latest_if_exists()
            if archived:
                print(f"Vorherige Version archiviert als: {archived}")
            filename = LATEST_FILENAME

        out = open(filename, "w", newline="", encoding="utf-8")
        close_out = True

    writer = csv.writer(out, delimiter=";")
    writer.writerow([
        "issue_number",
        "issue_url",
        "author",
        "domain",
        "root_domain",
        "title",
        "labels",
        "created_at",
    ])

    for issue in fetch_open_issues():
        number = issue.get("number")
        title = (issue.get("title") or "").strip()
        issue_url = f"https://github.com/{REPO}/issues/{number}"
        author = (issue.get("user") or {}).get("login", "")

        domain, root_domain = extract_domains(title)
        labels = ",".join(lbl.get("name", "") for lbl in issue.get("labels", []))
        created = issue.get("created_at", "")

        writer.writerow([
            number,
            issue_url,
            author,
            domain,
            root_domain,
            title,
            labels,
            created,
        ])

    if close_out:
        out.close()
        print(f"CSV geschrieben: {filename}")


if __name__ == "__main__":
    main()
