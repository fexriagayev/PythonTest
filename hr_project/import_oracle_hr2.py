"""
2-ci Oracle idxalı: MID_FIRE_REASONS, MI_STRUCTURES, MID_POSITIONS, MI_STAFF_POSITIONS, MI_WORK_PLACES.

İstifadə:
    python scripts/import_oracle_hr2.py --sql scripts.txt --db app.db --dry-run   # surət üzərində tam sınaq
    python scripts/import_oracle_hr2.py --sql scripts.txt --db app.db             # icra (ehtiyat surət alır)

Qaydalar:
  * MI_STRUCTURES -> dictionary_items(department), MID_POSITIONS -> dictionary_items(position),
    MID_FIRE_REASONS -> dictionary_items(fire_reason). Təkrarlar (böyük/kiçik hərf fərqi daxil) birləşdirilir.
  * MI_STAFF_POSITIONS import EDİLMİR — yalnız FK_STAFF_POSITION -> (struktur, vəzifə) axtarışı üçün oxunur.
  * MI_WORK_PLACES -> employment_records (Oracle ID saxlanılır). IS_HIRING və FK_FIRE_REASON nəzərə alınmır.
      END_DATE dolu olduqda əlavə "İşdən çıxma" qeydi yaranır (ID = 10000 + Oracle ID, tarix = END_DATE).
      Əmr: FK_FIRE_ORDER yalnız --fire-order verilərsə yazılır, əks halda NULL.
      FK_STAFF_POSITION dolu  -> is_current_company=1, department_id/position_id ştat vahidindən, order_id=FK_HIRE_ORDER
      FK_STAFF_POSITION boş   -> is_current_company=0, order_id=NULL, mətn sahələri STRUCTURE/POSITION-dan
      Hərəkət növü: zəncirdə ilk qeyd və hər "İşdən çıxma"dan sonrakı qeyd 'hire', bağlanmamış qeydin ardınca gələn 'transfer'.
  * STATE='C' iş yerləri buraxılır. Employee.is_active/termination_date app-in zəncir məntiqi ilə hesablanır.
"""
import argparse, collections, datetime, json, os, shutil, sqlite3, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_parse import parse_inserts

PLACEHOLDERS = {"", "0", "yoxdur"}
CLEAN_CATEGORIES = [("HR", "department"), ("HR", "position"), ("HR", "fire_reason")]


def clean_text(v):
    if v is None:
        return None
    v = v.strip()
    return None if v.casefold() in PLACEHOLDERS else v


def dedupe_dictionary(rows, name_key="VALUE"):
    """Eyni adlı (casefold) qeydləri birləşdirir. Qalan: STATE='A' > baş hərfi böyük > kiçik ID.
    Qaytarır: (survivors[list], remap{köhnə_id: survivor_id})"""
    groups = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: r["ID"]):
        groups.setdefault(r[name_key].strip().casefold(), []).append(r)
    survivors, remap = [], {}
    for g in groups.values():
        best = sorted(g, key=lambda r: (r["STATE"] != "A", not r[name_key].strip()[:1].isupper(), r["ID"]))[0]
        survivors.append(best)
        for r in g:
            remap[r["ID"]] = best["ID"]
    return survivors, remap


def run(sql_path, db_path, map_out, report, fire_order=False):
    by = collections.defaultdict(list)
    for tb, row in parse_inserts(open(sql_path, encoding="utf-8").read()):
        by[tb].append(row)
    expected = {"MID_FIRE_REASONS", "MI_STRUCTURES", "MID_POSITIONS", "MI_STAFF_POSITIONS", "MI_WORK_PLACES"}
    if set(by) - expected:
        sys.exit(f"Naməlum cədvəllər: {sorted(set(by) - expected)}")

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")
    cur = con.cursor()
    try:
        cur.execute("BEGIN")
        # ---- 1) Təmizləmə
        report["deleted"] = {"employment_records": cur.execute("DELETE FROM employment_records").rowcount}
        for mod, cat in CLEAN_CATEGORIES:
            report["deleted"][f"dictionary_items[{cat}]"] = cur.execute(
                "DELETE FROM dictionary_items WHERE module_code=? AND category=?", (mod, cat)).rowcount

        # ---- 2) Soraqçılar (təkrarlar birləşdirilir)
        idmap = {}
        def load(tb, cat, name_key="VALUE"):
            surv, remap = dedupe_dictionary(by[tb], name_key)
            new = {}
            for r in surv:
                cur.execute("INSERT INTO dictionary_items (module_code, category, name, value, is_active) VALUES (?,?,?,?,?)",
                            ("HR", cat, r[name_key].strip(), None, 1 if r["STATE"] == "A" else 0))
                new[r["ID"]] = cur.lastrowid
            idmap[tb] = {old: new[s] for old, s in remap.items()}
            report["inserted"][f"dictionary_items[{cat}]"] = len(surv)
            merged = collections.defaultdict(list)
            for old, s in remap.items():
                if old != s:
                    merged[s].append(old)
            report["merged_duplicates"][cat] = {f"{s}<-{','.join(map(str, olds))}": next(x['VALUE'] for x in by[tb] if x['ID'] == s)
                                                for s, olds in merged.items()}
        report["inserted"], report["merged_duplicates"] = {}, {}
        load("MI_STRUCTURES", "department")
        load("MID_POSITIONS", "position")
        load("MID_FIRE_REASONS", "fire_reason")

        # ---- 3) Ştat vahidi axtarışı (import edilmir)
        staff = {r["ID"]: (idmap["MI_STRUCTURES"][r["FK_STRUCTURE"]], idmap["MID_POSITIONS"][r["FK_POSITION"]])
                 for r in by["MI_STAFF_POSITIONS"]}

        # ---- 4) İş yerləri -> employment_records
        emp_ids = {r[0] for r in cur.execute("SELECT id FROM employees")}
        order_ids = {r[0] for r in cur.execute("SELECT id FROM orders")}
        skipped = [r["ID"] for r in by["MI_WORK_PLACES"] if r["STATE"] == "C"]
        rows = [r for r in by["MI_WORK_PLACES"] if r["STATE"] != "C"]
        missing_emp = [r["ID"] for r in rows if r["FK_EMPLOYEE"] not in emp_ids]
        if missing_emp:
            raise RuntimeError(f"İşçisi olmayan iş yerləri: {missing_emp}")
        chains = collections.defaultdict(list)
        for r in rows:
            chains[(r["FK_EMPLOYEE"], r["FK_STAFF_POSITION"] is not None)].append(r)
        n_cur = n_ext = n_term_cur = n_term_ext = 0
        dropped_ext_order, missing_order, same_date_clash = [], [], []
        now = datetime.datetime.utcnow().isoformat(sep=" ")
        for (emp, is_cur), lst in chains.items():
            prev_closed, last = True, None   # last = son cari/kənar qeydin (dep,pos,company,ext_pos)
            for r in sorted(lst, key=lambda r: (r["START_DATE"], r["ID"])):
                movement = "hire" if prev_closed else "transfer"
                if is_cur:
                    dep, pos = staff[r["FK_STAFF_POSITION"]]
                    oid = r["FK_HIRE_ORDER"]
                    if oid is not None and oid not in order_ids:
                        missing_order.append(r["ID"]); oid = None
                    cur.execute("""INSERT INTO employment_records (id, employee_id, is_current_company, movement_type,
                                   department_id, position_id, order_id, date_from, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                                (r["ID"], emp, 1, movement, dep, pos, oid, r["START_DATE"].isoformat(), now))
                    n_cur += 1
                    last = (dep, pos)
                else:
                    if r["FK_HIRE_ORDER"] is not None:
                        dropped_ext_order.append(r["ID"])
                    comp, xpos = clean_text(r["STRUCTURE"]), clean_text(r["POSITION"])
                    cur.execute("""INSERT INTO employment_records (id, employee_id, is_current_company, movement_type,
                                   external_company_name, external_position, date_from, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                                (r["ID"], emp, 0, movement, comp, xpos, r["START_DATE"].isoformat(), now))
                    n_ext += 1
                    last = (comp, xpos)
                prev_closed = False
                if r["END_DATE"] is not None:
                    tid = 10000 + r["ID"]
                    if is_cur:
                        toid = r["FK_FIRE_ORDER"] if fire_order and r["FK_FIRE_ORDER"] in order_ids else None
                        cur.execute("""INSERT INTO employment_records (id, employee_id, is_current_company, movement_type,
                                       department_id, position_id, order_id, date_from, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                                    (tid, emp, 1, "termination", last[0], last[1], toid, r["END_DATE"].isoformat(), now))
                        n_term_cur += 1
                    else:
                        cur.execute("""INSERT INTO employment_records (id, employee_id, is_current_company, movement_type,
                                       external_company_name, external_position, date_from, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                                    (tid, emp, 0, "termination", last[0], last[1], r["END_DATE"].isoformat(), now))
                        n_term_ext += 1
                    prev_closed = True
        # eyni işçidə eyni tarixli qeydlər (ID sırası termination-ı hire-dan sonraya salmasın)
        clash = cur.execute("""SELECT a.employee_id, a.id, b.id FROM employment_records a JOIN employment_records b
                               ON a.employee_id=b.employee_id AND a.date_from=b.date_from AND a.id<b.id
                               WHERE a.movement_type!='termination' AND b.movement_type='termination'""").fetchall()
        report["same_date_clash_termination_after_hire"] = clash
        report["inserted"].update({"employment_records[cari]": n_cur, "employment_records[kənar]": n_ext,
                                   "employment_records[cari işdən çıxma]": n_term_cur, "employment_records[kənar işdən çıxma]": n_term_ext})
        report["skipped_work_places_STATE_C"] = skipped
        report["external_order_dropped(FK_HIRE_ORDER kənar qeyddə)"] = dropped_ext_order
        report["hire_order_not_found"] = missing_order

        bad = cur.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"FK pozuntusu: {bad[:5]}")
        con.commit()
    except Exception:
        con.rollback(); con.close(); raise
    con.close()

    # ---- 5) Employee sahələrinin yenidən hesablanması (app-in öz funksiyası; is_active toxunulmaz)
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.abspath(db_path)
    proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, proj)
    from app import create_app
    app = create_app()
    with app.app_context():
        from app import db
        from app.models import Employee
        from app.services.hr_service import recompute_employee_from_history
        n = 0
        before = {e.id: e.is_active for e in Employee.query.all()}
        for e in Employee.query.all():
            recompute_employee_from_history(e)
            n += 1
        db.session.commit()
        after = {e.id: e.is_active for e in Employee.query.all()}
        report["employees_is_active_before(Oracle STATE)"] = dict(collections.Counter(before.values()))
        report["employees_is_active_after(zəncir)"] = dict(collections.Counter(after.values()))
        report["employees_status_changed"] = sum(1 for k in before if before[k] != after[k])
        report["recomputed_employees"] = n

    json_map = {}
    if os.path.exists(map_out):
        json_map = json.load(open(map_out, encoding="utf-8"))
    json_map.setdefault("dictionaries", {}).update({tb: {str(k): v for k, v in d.items()} for tb, d in idmap.items()})
    json_map["note_hr2"] = "MI_STRUCTURES/MID_POSITIONS/MID_FIRE_REASONS: Oracle ID -> dictionary_items.id (təkrarlar birləşdirilib). employment_records ID-ləri = Oracle MI_WORK_PLACES.ID."
    return json_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True); ap.add_argument("--db", required=True)
    ap.add_argument("--map-out", default="oracle_id_map.json"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fire-order", action="store_true", help="İşdən çıxma qeydinə FK_FIRE_ORDER yaz")
    a = ap.parse_args()
    report = {}
    if a.dry_run:
        tmp = os.path.join(tempfile.mkdtemp(), "dry.db"); shutil.copy2(a.db, tmp)
        run(a.sql, tmp, a.map_out, report, a.fire_order)
        print("DRY-RUN (surət üzərində, app.db dəyişmədi)")
    else:
        bak = f"{a.db}.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}"; shutil.copy2(a.db, bak); print("Ehtiyat surət:", bak)
        jm = run(a.sql, a.db, a.map_out, report, a.fire_order)
        json.dump(jm, open(a.map_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("Xəritə:", a.map_out)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
