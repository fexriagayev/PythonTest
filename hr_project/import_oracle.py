"""
Oracle INSERT skriptindən (Promt.txt) app.db-yə data köçürməsi.

İstifadə:
    python scripts/import_oracle.py --sql Promt.txt --db app.db --dry-run   # yoxlama, heç nə yazılmır
    python scripts/import_oracle.py --sql Promt.txt --db app.db             # icra (əvvəl ehtiyat surət alır)

Prinsiplər:
  * Oracle-da hər soraqçı ayrı cədvəldir və ID-lər (məs. -1) müxtəlif cədvəllərdə təkrarlana bilər.
    app.db-də hamısı tək `dictionary_items` cədvəlindədir -> hər soraqçı öz `category`-si ilə yazılır,
    YENİ ID alır. (Oracle cədvəli, köhnə ID) -> yeni ID xəritəsi qurulur və FK-lar bu xəritə ilə çevrilir.
  * İşçilər (employees) və əmrlər (orders) ayrı cədvəllərdir, ID toqquşması yoxdur -> Oracle ID-ləri saxlanılır
    (sonrakı tabel/əmək kitabçası skriptlərində FK_EMPLOYEE / FK_ORDER birbaşa işləsin deyə).
  * Hamısı bir transaction-dadır, xəta olarsa tam rollback.
"""
import argparse, collections, datetime, json, os, shutil, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_parse import parse_inserts

# Oracle soraqçı cədvəli -> (module_code, category)
DICT_MAP = {
    "MID_GENDERS":          ("HR", "gender"),
    "MID_MARITAL_STATUSES": ("HR", "family_status"),
    "MID_EDUCATION_TYPES":  ("HR", "education_type"),
    "MID_DISABILITY_TYPES": ("HR", "benefits"),      # employees.benefit_id (güzəşt)
    "MID_ORDER_TYPES":      ("HR", "order_type"),
}

# Təmizlənəcək cədvəllər — FK-ya görə uşaqdan valideynə
CLEAN_TABLES = [
    "payroll_payments", "payroll_entries", "payroll_runs",
    "leave_request_monthly_payments", "salary_addition_employees", "salary_additions",
    "briqada_work_entries", "briqada_work_periods",
    "tabel_employee_rows", "tabel_periods",
    "leave_requests", "employment_contract_notifications", "employment_records",
    "vacation_compensations", "salary_cards", "insurance_policies", "documents",
    "employee_educations", "briqadalar", "employees", "obyekts", "orders",
]


def s(v):
    return v.strip() if isinstance(v, str) else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--map-out", default="oracle_id_map.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    text = open(a.sql, encoding="utf-8").read()
    by = collections.defaultdict(list)
    for tb, row in parse_inserts(text):
        by[tb].append(row)

    unknown = set(by) - set(DICT_MAP) - {"MI_EMPLOYEES", "MI_ORDERS"}
    if unknown:
        sys.exit(f"Bu cədvəllər üçün xəritə yoxdur: {sorted(unknown)}")

    # Təkrarlanan eyni soraqçı bloklarını ID üzrə təkilləşdir
    dicts = {}
    for tb in DICT_MAP:
        seen = {}
        for r in by.get(tb, []):
            if r["ID"] in seen and seen[r["ID"]] != r:
                sys.exit(f"{tb}: ID {r['ID']} iki fərqli dəyərlə təkrarlanır")
            seen[r["ID"]] = r
        dicts[tb] = sorted(seen.values(), key=lambda r: (r.get("PRIORITY") or 0, r["ID"]))

    if not a.dry_run:
        bak = f"{a.db}.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy2(a.db, bak)
        print("Ehtiyat surət:", bak)

    con = sqlite3.connect(a.db)
    con.execute("PRAGMA foreign_keys=ON")
    cur = con.cursor()
    existing = {r[0] for r in cur.execute("select name from sqlite_master where type='table'")}
    report = {"deleted": {}, "inserted": {}}

    try:
        cur.execute("BEGIN")
        # 1) Təmizləmə
        for t in CLEAN_TABLES:
            if t in existing:
                report["deleted"][t] = cur.execute(f'DELETE FROM "{t}"').rowcount
        for tb, (mod, cat) in DICT_MAP.items():
            n = cur.execute("DELETE FROM dictionary_items WHERE module_code=? AND category=?", (mod, cat)).rowcount
            report["deleted"][f"dictionary_items[{cat}]"] = n
        if "sqlite_sequence" in existing:
            cur.execute("DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join("?" * len(CLEAN_TABLES)), CLEAN_TABLES)

        # 2) Soraqçılar -> dictionary_items (yeni ID) + xəritə
        idmap = {}
        for tb, (mod, cat) in DICT_MAP.items():
            idmap[tb] = {}
            for r in dicts[tb]:
                cur.execute(
                    "INSERT INTO dictionary_items (module_code, category, name, value, is_active) VALUES (?,?,?,?,?)",
                    (mod, cat, s(r["VALUE"]), None, 1 if r["STATE"] == "A" else 0))
                idmap[tb][r["ID"]] = cur.lastrowid
            report["inserted"][f"dictionary_items[{cat}]"] = len(idmap[tb])

        def m(tb, old):
            return None if old is None else idmap[tb][old]  # KeyError = pozulmuş FK, dərhal dayanır

        # 3) İşçilər (Oracle ID saxlanılır)
        for r in sorted(by["MI_EMPLOYEES"], key=lambda r: r["ID"]):
            cur.execute(
                """INSERT INTO employees (id, full_name, gender_id, family_status_id, education_type_id,
                       birth_date, benefit_id, fin_code, id_card_number, social_insurance_number, note, is_active)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["ID"], s(r["FULL_NAME"]), m("MID_GENDERS", r["FK_GENDER"]),
                 m("MID_MARITAL_STATUSES", r["FK_MARITAL_STATUS"]),
                 m("MID_EDUCATION_TYPES", r["FK_EDUCATION_TYPE"]),
                 r["BIRTH_DATE"].isoformat() if r["BIRTH_DATE"] else None,
                 m("MID_DISABILITY_TYPES", r["FK_DISABILITY_TYPE"]),
                 s(r["IC_PIN"]), s(r["IC_NUMBER"]), s(r["DSMF_NUMBER"]),
                 s(r["NOTE"]) or None, 1 if r["STATE"] == "A" else 0))
        report["inserted"]["employees"] = len(by["MI_EMPLOYEES"])

        # 4) Əmrlər (Oracle ID saxlanılır)
        for r in sorted(by["MI_ORDERS"], key=lambda r: r["ID"]):
            cur.execute(
                "INSERT INTO orders (id, number, order_date, order_type_id, note) VALUES (?,?,?,?,?)",
                (r["ID"], s(r["ORDER_NUMBER"]), r["ORDER_DATE"].isoformat(),
                 m("MID_ORDER_TYPES", r["FK_ORDER_TYPE"]), s(r["NOTE"]) or None))
        report["inserted"]["orders"] = len(by["MI_ORDERS"])

        # 5) Yoxlama
        bad = cur.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"FK pozuntusu: {bad[:5]}")

        if a.dry_run:
            con.rollback(); print("DRY-RUN: heç nə yazılmadı (rollback).")
        else:
            con.commit()
            json.dump({"note": "Oracle cədvəl -> {köhnə ID: yeni dictionary_items.id}. employees və orders üçün ID-lər dəyişmir.",
                       "dictionaries": {tb: {str(k): v for k, v in d.items()} for tb, d in idmap.items()}},
                      open(a.map_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("Xəritə:", a.map_out)
    except Exception:
        con.rollback()
        raise

    print(json.dumps(report, ensure_ascii=False, indent=1))
    con.close()


if __name__ == "__main__":
    main()
