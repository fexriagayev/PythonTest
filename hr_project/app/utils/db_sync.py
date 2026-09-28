"""
Yüngül "poor man's migration" — Alembic/flask-migrate əvəzinə YOX, ona
ƏLAVƏ olaraq. Bu layihədə DB sxemi əsasən `db.create_all()` (bax:
app/seed.py) ilə qurulur, bu isə YALNIZ ÇATIŞMAYAN CƏDVƏLLƏRİ yaradır —
artıq mövcud olan bir cədvələ sonradan əlavə olunan sütunları (məs. bu
layihədə `LeaveReason.is_sick_leave`, `PayrollTaxFormula.valid_from`)
ƏLAVƏ ETMİR. Nəticədə inkişaf zamanı modelə yeni sütun əlavə edildikdə,
əvvəlcədən yaradılmış (developer-in öz komputerindəki) verilənlər bazası
"no such column" xətası ilə qırılır.

`sync_missing_columns()` bunun qarşısını alır: mövcud hər cədvəl üçün
modeldə olub DB-də olmayan sütunları tapıb `ALTER TABLE ... ADD COLUMN`
ilə əlavə edir. Yalnız YENİ sütun əlavəsini dəstəkləyir (silinmə/tip
dəyişikliyi YOX — bunlar üçün əsl miqrasiya alətlərinə keçmək lazımdır),
amma bu layihənin indiyədək etdiyi bütün dəyişikliklər (yeni sütun əlavəsi)
üçün kifayətdir.
"""

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable


def _column_ddl_type(column, dialect):
    return column.type.compile(dialect=dialect)


def _default_clause(column, dialect):
    """Sadə (callable/sequence olmayan) sabit default dəyərləri üçün
    'DEFAULT ...' DDL parçası — mövcud sətirlərin yeni sütunu NULL yox,
    modeldəki default dəyərlə almasını təmin edir."""
    default = column.default
    if default is None or getattr(default, "is_callable", False) or getattr(default, "is_sequence", False):
        return ""
    value = getattr(default, "arg", None)
    if isinstance(value, bool):
        return " DEFAULT " + ("1" if value else "0")
    if isinstance(value, (int, float)):
        return f" DEFAULT {value}"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def sync_missing_columns(db):
    """Mövcud (artıq DB-də olan) cədvəllərə modeldə olub DB-də olmayan
    sütunları əlavə edir. Yeni cədvəllər `db.create_all()` tərəfindən
    artıq yaradılıb — bu funksiya YALNIZ mövcud cədvəllərə toxunur."""
    engine = db.engine
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in db.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # yeni cədvəl — create_all() artıq yaradıb

        existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            ddl_type = _column_ddl_type(column, engine.dialect)
            default_clause = _default_clause(column, engine.dialect)
            nullable_clause = "" if column.nullable else " NOT NULL" if default_clause else ""
            ddl = (
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{ddl_type}{default_clause}{nullable_clause}"
            )
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                print(f"[db_sync] Sütun əlavə olundu: {table.name}.{column.name}")
            except Exception as exc:  # pragma: no cover — dev-time convenience only
                print(f"[db_sync] {table.name}.{column.name} əlavə edilmədi: {exc}")


def rename_column_if_exists(db, table_name, old_name, new_name):
    """BİR DƏFƏLİK, idempotent: modeldə sütunun adı dəyişdirilibsə (məs.
    `payroll_entries.additions_total` -> `bonus_total`), köhnə adlı sütunu
    MƏLUMATI İTİRMƏDƏN yenisinə çevirir. `sync_missing_columns()` yalnız
    çatışan sütun əlavə edir — ondan ƏVVƏL çağırılmasa, yeni ad boş sütun
    kimi yaranar, köhnə sütundakı məlumat isə kənarda qalar. Cədvəl/köhnə
    sütun yoxdursa (təzə DB) və ya yeni sütun artıq varsa — heç nə etmir."""
    engine = db.engine
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns(table_name)}
    if old_name not in columns:
        return
    if new_name in columns:
        print(f"[db_sync] {table_name}: həm '{old_name}', həm '{new_name}' var — əl ilə yoxlayın.")
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(
                f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"'
            ))
        print(f"[db_sync] Sütun adı dəyişdirildi: {table_name}.{old_name} -> {new_name}")
    except Exception as exc:  # pragma: no cover — dev-time convenience only
        print(f"[db_sync] {table_name}.{old_name} adı dəyişdirilmədi: {exc}")


def relax_column_nullable(db, table_name, column_name):
    """BİR DƏFƏLİK, idempotent düzəliş: `column_name` DB-də hələ də
    NOT NULL-dursa (amma modeldə artıq `nullable=True`-dursa), onu
    NULL qəbul edən sütuna çevirir. `sync_missing_columns()` yalnız
    ÇATIŞMAYAN sütunları əlavə edir — MÖVCUD bir sütunun
    NULL/NOT NULL statusunu DƏYİŞMİR, buna görə bu, ayrıca funksiyadır
    (bax: BriqadaWorkEntry.briqada_id — indi `employee_id` ilə
    ALTERNATİV sahib ola bilər, deməli artıq MƏCBURİ deyil).

    Postgres-də sadə `ALTER COLUMN ... DROP NOT NULL`. SQLite bunu
    dəstəkləmir — standart \"cədvəli yenidən qur\" resepti işlədilir:
    modeldəki (artıq düzəldilmiş) tərifə görə YENİ table yaradılır,
    məlumat köçürülür, köhnə table silinir, yenisi adlandırılır."""
    engine = db.engine
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    columns = {c["name"]: c for c in inspector.get_columns(table_name)}
    col = columns.get(column_name)
    if col is None or col["nullable"]:
        return  # sütun yoxdur, ya da artıq NULL qəbul edir — ediləcək iş yoxdur

    if engine.dialect.name != "sqlite":
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP NOT NULL')
                )
            print(f"[db_sync] {table_name}.{column_name} artıq NULL qəbul edir.")
        except Exception as exc:  # pragma: no cover — dev-time convenience only
            print(f"[db_sync] {table_name}.{column_name} NULL edilmədi: {exc}")
        return

    table = db.metadata.tables.get(table_name)
    if table is None:
        return
    existing_cols = list(columns.keys())
    tmp_name = table_name + "__relax_tmp"
    try:
        create_sql = str(CreateTable(table).compile(engine)).strip()
        create_sql = create_sql.replace(f'"{table_name}"', f'"{tmp_name}"', 1)
        if tmp_name not in create_sql:
            create_sql = create_sql.replace(table_name, tmp_name, 1)
        cols_csv = ", ".join(f'"{c}"' for c in existing_cols)
        with engine.begin() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text(create_sql))
            conn.execute(
                text(f'INSERT INTO "{tmp_name}" ({cols_csv}) SELECT {cols_csv} FROM "{table_name}"')
            )
            conn.execute(text(f'DROP TABLE "{table_name}"'))
            conn.execute(text(f'ALTER TABLE "{tmp_name}" RENAME TO "{table_name}"'))
            conn.execute(text("PRAGMA foreign_keys=ON"))
        print(f"[db_sync] {table_name} cədvəli yenidən quruldu ({column_name} artıq NULL qəbul edir).")
    except Exception as exc:  # pragma: no cover — dev-time convenience only
        print(f"[db_sync] {table_name}.{column_name} NULL edilmədi: {exc}")


def migrate_legacy_leave_payments(db):
    """BİR DƏFƏLİK, idempotent köçürmə: `LeaveRequest.payment_amount`
    sütunu modeldən TAMAMİLƏ silinib (bax: LeaveRequestMonthlyPayment —
    hər ay üçün ayrıca ödəniş məbləği), amma bu sütun ƏVVƏLKİ bir
    inkişaf mərhələsində DB-də fiziki olaraq yaradılmış ola bilər (bax
    yuxarı qeyd: sync_missing_columns() sütunları YALNIZ ƏLAVƏ edir,
    SİLMİR — köhnə sütun DB-də hələ də qala bilər, sadəcə model artıq
    onu tanımır).

    Belə bir sütun VARSA və içində məlumat varsa, hər sətrin köhnə
    `payment_amount`-unu, əgər həmin İş buraxması üçün HƏLƏ heç bir
    LeaveRequestMonthlyPayment yoxdursa, YENİ cədvələ (başlama tarixinin
    ilinə/ayına aid tək bir sətir kimi) köçürür — beləliklə əvvəllər
    daxil edilmiş xəstəlik/məzuniyyət ödənişləri "yoxa çıxmır". Ay
    sərhədini keçən köhnə qeydlər üçün bu, YALNIZ TƏXMİNİ bir bərpadır
    (bütün məbləğ başlama ayına yazılır) — belə qeydləri "İş
    buraxmaları" pəncərəsindən açıb aylar üzrə düzgün bölmək tövsiyə
    olunur."""
    engine = db.engine
    inspector = inspect(engine)
    if "leave_requests" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("leave_requests")}
    if "payment_amount" not in columns:
        return  # təzə DB — bu köhnə sütun heç yaranmayıb, ediləcək iş yoxdur

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, start_date, payment_amount FROM leave_requests "
            "WHERE payment_amount IS NOT NULL AND payment_amount != 0"
        )).fetchall()
        migrated = 0
        for row in rows:
            existing = conn.execute(text(
                "SELECT COUNT(*) FROM leave_request_monthly_payments WHERE leave_request_id = :id"
            ), {"id": row.id}).scalar()
            if existing:
                continue  # bu qeyd üçün artıq (yeni formadan) aylıq bölgü var — toxunma
            start = row.start_date
            if not start:
                continue
            year, month = int(str(start)[:4]), int(str(start)[5:7])
            conn.execute(text(
                "INSERT INTO leave_request_monthly_payments (leave_request_id, year, month, amount) "
                "VALUES (:lr_id, :year, :month, :amount)"
            ), {"lr_id": row.id, "year": year, "month": month, "amount": row.payment_amount})
            migrated += 1
        if migrated:
            print(f"[db_sync] {migrated} köhnə xəstəlik/məzuniyyət ödənişi yeni (ay üzrə) cədvələ köçürüldü.")