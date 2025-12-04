#!/usr/bin/env python3
import csv
import sys
import requests
import argparse
import os
import re
from urllib.parse import urlparse
from datetime import datetime


REPO_CONFIG = [
    {
        "repo": "svemailproject/TheySoldMyEmail",   # Original
        "offset": 0,
    },
    {
        "repo": "Bob-Nixkoenner/TheySoldMyEmail",   # dein Fork
        "offset": 2000,
    },
]



PER_PAGE = 100
LATEST_FILENAME = "issues-latest.csv"

SKIP_HOSTS = {
    "github.com",
    "www.github.com",
    "api.github.com",
}


def normalize_host(host: str) -> str:
    """
    Nimmt einen Host und gibt eine bereinigte Domain zurück
    (klein, ohne Userinfo/Port). Gibt "" zurück, wenn es
    nicht nach Domain aussieht.
    """
    host = (host or "").strip().lower()
    if not host:
        return ""

    # Userinfo entfernen
    if "@" in host:
        host = host.split("@", 1)[-1]

    # Port entfernen
    if ":" in host:
        host = host.split(":", 1)[0]

    # muss mindestens einen Punkt haben
    if "." not in host:
        return ""

    return host


def clickable_domain(domain: str) -> str:
    """
    Aus der erkannten Domain eine klickbare Variante bauen:
    immer "www." + Domain (ohne führendes www.).
    LibreOffice/Excel machen daraus anklickbare Links.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return ""

    if domain.startswith("www."):
        domain = domain[4:]

    if not domain:
        return ""

    return f"www.{domain}"


def extract_from_title(title: str) -> str:
    if not title:
        return ""
    tokens = title.strip().split()
    candidate = None

    # Bevorzugt Token mit Punkt oder Slash
    for tok in tokens:
        if "." in tok or "/" in tok:
            candidate = tok
            break

    # Fallback: erstes Wort
    if candidate is None and tokens:
        candidate = tokens[0]
    if candidate is None:
        return ""

    candidate = candidate.strip(" ,;()[]{}<>\"'")
    if not candidate:
        return ""

    # Schema ergänzen falls fehlt
    if candidate.startswith(("http://", "https://")):
        parsed = urlparse(candidate)
    else:
        parsed = urlparse("http://" + candidate)

    host = parsed.netloc or parsed.path
    return normalize_host(host)


def extract_from_body(body: str) -> str:
    if not body:
        return ""
    text = body.strip()
    if not text:
        return ""

    # 1) Zeilen mit "domain"
    for line in text.splitlines():
        low = line.lower()
        if "domain" in low:
            # URL in dieser Zeile
            m = re.search(r'https?://([^\s/)+]+)', line, flags=re.IGNORECASE)
            if m:
                host = normalize_host(m.group(1))
                if host and host not in SKIP_HOSTS:
                    return host
            # nackte Domain in dieser Zeile
            m = re.search(r'\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b', line, flags=re.IGNORECASE)
            if m:
                host = normalize_host(m.group(1))
                if host and host not in SKIP_HOSTS:
                    return host

    # 2) Allgemeine URLs im Body
    for host in re.findall(r'https?://([^\s/)+]+)', text, flags=re.IGNORECASE):
        host = normalize_host(host)
        if host and host not in SKIP_HOSTS:
            return host

    # 3) Nackte Domains im Body
    for host in re.findall(r'\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b', text, flags=re.IGNORECASE):
        host = normalize_host(host)
        if host and host not in SKIP_HOSTS:
            return host

    return ""


def extract_domain(title: str, body: str):
    """
    Versucht zuerst Body, dann Titel.
    Gibt (domain, source) zurück.
    domain = nackte Domain (ohne www.-Zwang),
    source = "body" / "title" / "none".
    """
    # Body
    d = extract_from_body(body)
    if d:
        return d, "body"

    # Titel
    d = extract_from_title(title)
    if d:
        return d, "title"

    return "", "none"


def fetch_open_issues(repo: str):
    api_url = f"https://api.github.com/repos/{repo}/issues"
    page = 1
    headers = {
        "Accept": "application/vnd.github+json",
        # Optional: Token bei Bedarf
        # "Authorization": "Bearer YOUR_TOKEN_HERE"
    }

    while True:
        params = {
            "state": "open",
            "per_page": PER_PAGE,
            "page": page,
        }
        r = requests.get(api_url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        issues = r.json()
        if not issues:
            break

        for issue in issues:
            if "pull_request" in issue:
                continue
            yield issue

        if "next" in r.links:
            page += 1
        else:
            break


def rotate_latest_if_exists():
    if os.path.exists(LATEST_FILENAME):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived = f"issues-{ts}.csv"
        os.rename(LATEST_FILENAME, archived)
        return archived
    return None


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Exportiert offene GitHub-Issues aus mehreren Repos in eine CSV.\n"
            "Die Repos und Offsets werden in REPO_CONFIG definiert."
        )
    )
    parser.add_argument(
        "-o", "--output",
        help="Pfad zur Ausgabedatei. Ohne Angabe: nutzt issues-latest.csv mit Auto-Rotation."
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="CSV auf stdout ausgeben (keine Dateien, keine Rotation)."
    )
    args = parser.parse_args()

    if not REPO_CONFIG:
        print("REPO_CONFIG ist leer – bitte mindestens ein Repo eintragen.")
        sys.exit(1)

    if args.stdout:
        out = sys.stdout
        close_out = False
    else:
        if args.output:
            filename = args.output
        else:
            archived = rotate_latest_if_exists()
            if archived:
                print(f"Vorherige Version archiviert als: {archived}")
            filename = LATEST_FILENAME

        # BOM für Excel/LibreOffice-Erkennung
        out = open(filename, "w", newline="", encoding="utf-8-sig")
        close_out = True

    writer = csv.writer(out, delimiter=";")
    writer.writerow([
        "issue_number",     # interne ID = offset + GitHub-Issue-Nummer
        "issue_url",
        "title",
        "domain",
        "domain_source",
        "author",
        "created_at",
        "repo",             # z.B. svemailproject/TheySoldMyEmail-Advent
        "gh_issue_number",  # originale GitHub-Issue-Nummer
    ])

    total_written = 0

    for cfg in REPO_CONFIG:
        repo = cfg["repo"]
        offset = int(cfg.get("offset", 0))

        print(f"[INFO] Hole Issues aus {repo} (Offset {offset})...")
        count_repo = 0

        for issue in fetch_open_issues(repo):
            gh_number = issue.get("number")
            if gh_number is None:
                continue

            internal_number = offset + int(gh_number)

            title = (issue.get("title") or "").strip()
            body = issue.get("body") or ""
            issue_url = f"https://github.com/{repo}/issues/{gh_number}"
            author = (issue.get("user") or {}).get("login", "")
            created = issue.get("created_at", "")

            raw_domain, source = extract_domain(title, body)
            dom = clickable_domain(raw_domain)

            writer.writerow([
                internal_number,
                issue_url,
                title,
                dom,
                source,
                author,
                created,
                repo,
                gh_number,
            ])

            count_repo += 1
            total_written += 1

        print(f"[INFO] Repo {repo}: {count_repo} Issues exportiert.")

    if close_out:
        out.close()
        print(f"[INFO] CSV geschrieben: {filename}, insgesamt {total_written} Issues.")


if __name__ == "__main__":
    main()
