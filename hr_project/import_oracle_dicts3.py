"""
3-cü Oracle idxalı (soraqçılar): MID_CONTRACT_TYPES, MID_CONTRACT_POSITIONS, MID_WORK_KINDS, MID_WORK_TYPES.
MID_CATEGORIES import EDİLMİR (app-də Kateqoriya = leave_categories cədvəlidir); yalnız xəritə yazılır.

İstifadə:
    python scripts/import_oracle_dicts3.py --sql scripts1.txt --db app.db --dry-run
    python scripts/import_oracle_dicts3.py --sql scripts1.txt --db app.db

  * Hər soraqçı öz kateqoriyasına yazılır (yeni ID alır).
  * MID_CONTRACT_POSITIONS: CODE unikaldır -> eyni kodlu qeydlər birləşdirilir (STATE='A' > kiçik ID qalır); CODE -> dictionary_items.value.
    Digər soraqçılarda ad üzrə (böyük/kiçik hərf fərqi nəzərə alınmadan) birləşdirilir.
  * MID_CATEGORIES -> leave_categories xəritəsi (Qulluqçu->Dövlət qulluqçusu, Fəhlə->Ümumi qayda, Veteran->Veteran) yalnız JSON xəritəyə yazılır.
"""
import argparse, collections, datetime, json, os, shutil, sqlite3, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_parse import parse_inserts
from import_oracle_hr2 import dedupe_dictionary

# Oracle cədvəli -> (kateqoriya, CODE-u value-ya yaz?)
DICT_MAP = {
    "MID_CONTRACT_TYPES":     ("contract_type", False),
    "MID_CONTRACT_POSITIONS": ("employment_position", True),
    "MID_WORK_KINDS":         ("work_type", False),     # Əsas / Əlavə
    "MID_WORK_TYPES":         ("labor_type", False),    # Fiks / Saat hesabı / KV/M
}


def run(sql_path, db_path, map_out, report):
    by = collections.defaultdict(list)
    for tb, row in parse_inserts(open(sql_path, encoding="utf-8").read()):
        by[tb].append(row)
    unknown = set(by) - set(DICT_MAP) - {"MID_CATEGORIES"}
    if unknown:
        sys.exit(f"Naməlum cədvəllər: {sorted(unknown)}")

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")
    cur = con.cursor()
    idmap, report["deleted"], report["inserted"], report["merged_duplicates"] = {}, {}, {}, {}
    try:
        cur.execute("BEGIN")
        for tb, (cat, use_code) in DICT_MAP.items():
            report["deleted"][cat] = cur.execute(
                "DELETE FROM dictionary_items WHERE module_code='HR' AND category=?", (cat,)).rowcount
            if use_code:
                groups = collections.OrderedDict()
                for r in sorted(by[tb], key=lambda r: r["ID"]):
                    groups.setdefault(str(r["CODE"]).strip(), []).append(r)
                surv, remap = [], {}
                for g in groups.values():
                    best = sorted(g, key=lambda r: (r["STATE"] != "A", r["ID"]))[0]
                    surv.append(best)
                    for r in g:
                        remap[r["ID"]] = best["ID"]
            else:
                surv, remap = dedupe_dictionary(by[tb])
            new = {}
            for r in sorted(surv, key=lambda r: (r.get("PRIORITY") or 0, r["ID"])):
                cur.execute("INSERT INTO dictionary_items (module_code, category, name, value, is_active) VALUES (?,?,?,?,?)",
                            ("HR", cat, r["VALUE"].strip(), (r.get("CODE") if use_code else None), 1 if r["STATE"] == "A" else 0))
                new[r["ID"]] = cur.lastrowid
            idmap[tb] = {old: new[s] for old, s in remap.items()}
            report["inserted"][cat] = len(surv)
            merged = collections.defaultdict(list)
            for old, s in remap.items():
                if old != s:
                    merged[s].append(old)
            src = {r["ID"]: r for r in by[tb]}
            report["merged_duplicates"][cat] = {
                f"{s}<-{','.join(map(str, olds))}": src[s]["VALUE"] + (
                    " | atılan ad: " + "; ".join(src[o]["VALUE"] for o in olds if src[o]["VALUE"] != src[s]["VALUE"])
                    if any(src[o]["VALUE"] != src[s]["VALUE"] for o in olds) else "")
                for s, olds in merged.items()}
            # birləşən qeydlərin kodları fərqlidirsə xəbər ver
            diff = [f"{s}<-{o}" for s, olds in merged.items() for o in olds
                    if use_code and src[o].get("CODE") != src[s].get("CODE")]
            if diff:
                report.setdefault("merged_with_different_code", {})[cat] = diff
        bad = cur.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"FK pozuntusu: {bad[:5]}")
        con.commit()
    except Exception:
        con.rollback(); con.close(); raise
    con.close()
    report["not_imported"] = {"MID_CATEGORIES": len(by.get("MID_CATEGORIES", []))}
    jm = json.load(open(map_out, encoding="utf-8")) if os.path.exists(map_out) else {}
    jm.setdefault("dictionaries", {}).update({tb: {str(k): v for k, v in d.items()} for tb, d in idmap.items()})
    # MID_CATEGORIES (Oracle ID) -> leave_categories.id (təsdiqlənmiş uyğunluq)
    jm["leave_categories"] = {"note": "MID_CATEGORIES Oracle ID -> leave_categories.id: 1 Qulluqçu->1 Dövlət qulluqçusu, 2 Fəhlə->3 Ümumi qayda, 3 Veteran->2 Veteran",
                              "MID_CATEGORIES": {"1": 1, "2": 3, "3": 2}}
    jm["note_dicts3"] = ("MID_CONTRACT_TYPES->contract_type, MID_CONTRACT_POSITIONS->employment_position (CODE=value), "
                         "MID_WORK_KINDS->work_type, MID_WORK_TYPES->labor_type. MID_CATEGORIES -> leave_categories (bax: leave_categories).")
    return jm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True); ap.add_argument("--db", required=True)
    ap.add_argument("--map-out", default="oracle_id_map.json"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    report = {}
    if a.dry_run:
        tmp = os.path.join(tempfile.mkdtemp(), "dry.db"); shutil.copy2(a.db, tmp)
        run(a.sql, tmp, a.map_out, report); print("DRY-RUN (surət üzərində)")
    else:
        bak = f"{a.db}.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"; shutil.copy2(a.db, bak); print("Ehtiyat surət:", bak)
        jm = run(a.sql, a.db, a.map_out, report)
        json.dump(jm, open(a.map_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("Xəritə:", a.map_out)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
