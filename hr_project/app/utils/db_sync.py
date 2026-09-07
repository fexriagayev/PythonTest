"""
Yüngül "poor man's migration" — Alembic/flask-migrate əvəzinə YOX, ona
ƏLAVƏ olaraq. Bu layihədə DB sxemi əsasən `db.create_all()` (bax:
app/seed.py) ilə qurulur, bu isə YALNIZ ÇATIŞMAYAN CƏDVƏLLƏRİ yaradır —
artıq mövcud olan bir cədvələ sonradan əlavə olunan sütunları (məs. bu
layihədə `LeaveReason.is_sick_leave`, `LeaveRequest.payment_amount`)
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
