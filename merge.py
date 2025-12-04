#!/usr/bin/env python3
import csv
import os
import argparse

DEFAULT_SOURCE = "issues-latest.csv"
DEFAULT_DB = "issues-db.csv"
DELIMITER = ";"

# Issues, die bei der Domain-Duplikatprüfung ignoriert werden sollen
IGNORE_DOMAIN_DUP_ISSUES = {"98"}


def read_csv_dict(path):
    if not os.path.exists(path):
        return [], []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        fieldnames = reader.fieldnames or []
        rows = [row for row in reader]

    return fieldnames, rows


def write_csv_dict(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=DELIMITER)
        writer.writeheader()
        for row in rows:
            out = {fn: row.get(fn, "") for fn in fieldnames}
            writer.writerow(out)


def build_fieldnames(db_fields, src_fields):
    fieldnames = []

    for fn in db_fields:
        if fn not in fieldnames:
            fieldnames.append(fn)

    for fn in src_fields:
        if fn not in fieldnames:
            fieldnames.append(fn)

    return fieldnames


def merge_rows(db_rows, src_rows, key_field, src_fieldnames):
    db_index = {}
    ordered_keys = []

    for row in db_rows:
        key = (row.get(key_field) or "").strip()
        if key:
            if key not in db_index:
                db_index[key] = row
                ordered_keys.append(key)
        else:
            pseudo_key = f"__NO_KEY__{len(ordered_keys)}"
            db_index[pseudo_key] = row
            ordered_keys.append(pseudo_key)

    for srow in src_rows:
        skey = (srow.get(key_field) or "").strip()
        if not skey:
            continue

        if skey not in db_index:
            db_index[skey] = dict(srow)
            ordered_keys.append(skey)
        else:
            drow = db_index[skey]
            for fn in src_fieldnames:
                sval = (srow.get(fn) or "").strip()
                dval = (drow.get(fn) or "").strip()
                if sval and not dval:
                    drow[fn] = sval

    merged_rows = [db_index[k] for k in ordered_keys]
    return merged_rows


def normalize_domain_for_dup(domain: str) -> str:
    if not domain:
        return ""
    d = domain.strip().lower()

    if d.startswith("http://"):
        d = d[7:]
    elif d.startswith("https://"):
        d = d[8:]

    if d.startswith("www."):
        d = d[4:]

    return d


def report_duplicates(rows):
    # 1) Doppelte issue_number
    seen_issue = {}
    dup_issue = {}

    for row in rows:
        num = (row.get("issue_number") or "").strip()
        if not num:
            continue
        if num in seen_issue:
            dup_issue.setdefault(num, []).append(row)
        else:
            seen_issue[num] = row

    if dup_issue:
        print("\n[WARN] Doppelte issue_number in DB gefunden:")
        for num, extra_rows in dup_issue.items():
            print(f"  issue_number {num} mehrfach vorhanden "
                  f"(insgesamt {len(extra_rows) + 1} Einträge)")
    else:
        print("[OK] Keine doppelten issue_number gefunden.")

    # 2) Doppelte Domains
    if not rows or "domain" not in rows[0]:
        print("[INFO] Keine 'domain'-Spalte gefunden, Domain-Duplikatprüfung übersprungen.")
        return

    # Haben wir eine Repo-Spalte? Wenn ja, prüfen wir je Repo.
    has_repo = any("repo" in r for r in rows)

    domain_map = {}
    for row in rows:
        num = (row.get("issue_number") or "").strip()

        # bestimmte Issues (z.B. Übersicht) bei Domain-Duplikaten ignorieren
        if num in IGNORE_DOMAIN_DUP_ISSUES:
            continue

        raw = row.get("domain") or ""
        nd = normalize_domain_for_dup(raw)
        if not nd:
            continue

        if has_repo:
            repo = (row.get("repo") or "").strip()
            key = (repo, nd)
        else:
            key = nd

        domain_map.setdefault(key, []).append(num if num else "?")

    if has_repo:
        # Duplikate je Repo
        dup_domains = {k: lst for k, lst in domain_map.items() if len(lst) > 1}

        if dup_domains:
            print("\n[INFO] Doppelte Domains je Repo gefunden "
                  "(normalisiert, ohne www., exkl. Ignore-Liste):")
            for (repo, dom), issues in sorted(
                dup_domains.items(),
                key=lambda x: ((x[0][0] or ""), x[0][1])
            ):
                issues_clean = ", ".join(sorted(set(i for i in issues if i)))
                repo_label = repo or "<unbekanntes Repo>"
                print(f"  [{repo_label}] {dom}  -> Issues: {issues_clean}")
        else:
            print("[OK] Keine doppelten Domains je Repo gefunden.")
    else:
        # Altes Verhalten: Duplikate global
        dup_domains = {d: lst for d, lst in domain_map.items() if len(lst) > 1}

        if dup_domains:
            print("\n[INFO] Doppelte Domains gefunden "
                  "(normalisiert, ohne www., exkl. Ignore-Liste):")
            for d, issues in sorted(dup_domains.items(), key=lambda x: x[0]):
                issues_clean = ", ".join(sorted(set(i for i in issues if i)))
                print(f"  {d}  -> Issues: {issues_clean}")
        else:
            print("[OK] Keine doppelten Domains gefunden.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Mergt issues-latest Export in eine persistente issues-db CSV, "
            "fügt neue Issues hinzu, lässt manuelle Änderungen in Ruhe "
            "und meldet Duplikate im Terminal."
        )
    )
    parser.add_argument(
        "-s", "--source",
        default=DEFAULT_SOURCE,
        help=f"Input-CSV aus dem Export-Script (Standard: {DEFAULT_SOURCE})"
    )
    parser.add_argument(
        "-d", "--db",
        default=DEFAULT_DB,
        help=f"Persistente Datenbank-CSV (Standard: {DEFAULT_DB})"
    )

    args = parser.parse_args()

    src_fields, src_rows = read_csv_dict(args.source)
    if not src_rows:
        print(f"Keine Daten in Source-Datei gefunden: {args.source}")
        return

    if "issue_number" not in src_fields:
        print("Fehler: 'issue_number' Spalte in Source fehlt.")
        return

    db_fields, db_rows = read_csv_dict(args.db)

    if not db_rows:
        write_csv_dict(args.db, src_fields, src_rows)
        print(f"Neue DB angelegt aus {args.source}: {args.db}")
        report_duplicates(src_rows)
        return

    fieldnames = build_fieldnames(db_fields, src_fields)
    merged_rows = merge_rows(db_rows, src_rows, "issue_number", src_fields)
    write_csv_dict(args.db, fieldnames, merged_rows)

    print(f"DB aktualisiert: {args.db}")
    print(f"Quelle: {args.source}, Einträge gesamt: {len(merged_rows)}")

    report_duplicates(merged_rows)


if __name__ == "__main__":
    main()
