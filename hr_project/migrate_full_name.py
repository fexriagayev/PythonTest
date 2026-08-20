# -*- coding: utf-8 -*-
"""
Bir dəfəlik miqrasiya: `employees` cədvəlində first_name/last_name/
father_name sütunlarını tək bir full_name sütununa birləşdirir.

İSTİFADƏ:
    (venv aktiv ikən, layihə kök qovluğunda)
    python migrate_full_name.py

Nə edir:
    1. `full_name` sütunu yoxdursa, əlavə edir.
    2. Mövcud sətirlər üçün full_name = "Soyad Ad Ata_adı" (boş
       hissələr atılır) dəyərini doldurur — YALNIZ full_name hələ
       boş olan sətirlərdə (təkrar işə salsanız məlumat üzərinə
       yazılmır).
    3. Köhnə first_name/last_name/father_name sütunlarını silməyə
       çalışır (SQLite 3.35+ / PostgreSQL dəstəkləyir). Silinmə
       mümkün olmasa, sütunlar sadəcə istifadə olunmadan qalır —
       bu, məlumat itkisi demək deyil, sonra əl ilə silə bilərsiniz.

Qeyd: işə salmazdan əvvəl `app.db` faylının (və ya real DB-nin)
ehtiyat nüsxəsini götürün.
"""
from sqlalchemy import text

from app import create_app, db


def column_exists(table, column):
    insp = db.inspect(db.engine)
    return column in [c["name"] for c in insp.get_columns(table)]


def main():
    app = create_app()
    with app.app_context():
        if not column_exists("employees", "full_name"):
            print("full_name sütunu əlavə olunur...")
            db.session.execute(text("ALTER TABLE employees ADD COLUMN full_name VARCHAR(200)"))
            db.session.commit()
        else:
            print("full_name sütunu artıq mövcuddur, əlavə edilmir.")

        has_old_cols = column_exists("employees", "first_name")
        if has_old_cols:
            print("Mövcud sətirlər üçün full_name doldurulur...")
            rows = db.session.execute(
                text(
                    "SELECT id, first_name, last_name, father_name FROM employees "
                    "WHERE full_name IS NULL OR full_name = ''"
                )
            ).fetchall()
            for r in rows:
                parts = [p for p in [r.last_name, r.first_name, r.father_name] if p]
                full_name = " ".join(parts).strip()
                db.session.execute(
                    text("UPDATE employees SET full_name = :fn WHERE id = :id"),
                    {"fn": full_name, "id": r.id},
                )
            db.session.commit()
            print(f"{len(rows)} sətir yeniləndi.")
        else:
            print("Köhnə sütunlar (first_name və s.) artıq yoxdur — doldurmaya ehtiyac yoxdur.")

        if has_old_cols:
            try:
                print("Köhnə sütunlar silinir (first_name, last_name, father_name)...")
                db.session.execute(text("ALTER TABLE employees DROP COLUMN first_name"))
                db.session.execute(text("ALTER TABLE employees DROP COLUMN last_name"))
                db.session.execute(text("ALTER TABLE employees DROP COLUMN father_name"))
                db.session.commit()
                print("Köhnə sütunlar silindi.")
            except Exception as exc:
                db.session.rollback()
                print(
                    "Köhnə sütunları silmək mümkün olmadı (DB versiyanız dəstəkləmir ola bilər): "
                    f"{exc}\n"
                    "Bu təhlükəli deyil — sütunlar sadəcə istifadə olunmadan qalacaq. "
                    "İstəsəniz DB alətinizlə əl ilə silə bilərsiniz."
                )

        print("Bitdi.")


if __name__ == "__main__":
    main()
