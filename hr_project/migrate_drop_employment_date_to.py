# -*- coding: utf-8 -*-
"""
Bir dəfəlik miqrasiya: `employment_records` cədvəlindən artıq istifadə
olunmayan `date_to` sütununu silir.

Səbəb: iş yeri qeydlərinin bitmə tarixi artıq heç vaxt saxlanmır — hər
qeydin bitmə tarixi employee-nin bütün "İş yerləri" qeydlərinin xronoloji
zəncirindən lazım olduğu anda hesablanır (bax:
app/services/hr_service.py -> compute_chain_end_dates).

İSTİFADƏ:
    (venv aktiv ikən, layihə kök qovluğunda)
    python migrate_drop_employment_date_to.py

Nə edir:
    `employment_records.date_to` sütununu silməyə çalışır (SQLite 3.35+ /
    PostgreSQL dəstəkləyir). Silinmə mümkün olmasa, sütun sadəcə istifadə
    olunmadan qalır — bu, məlumat itkisi demək deyil, sonra əl ilə silə
    bilərsiniz.

Qeyd: işə salmazdan əvvəl `app.db` faylının (və ya real DB-nin) ehtiyat
nüsxəsini götürün.
"""
from sqlalchemy import text

from app import create_app, db


def column_exists(table, column):
    insp = db.inspect(db.engine)
    return column in [c["name"] for c in insp.get_columns(table)]


def main():
    app = create_app()
    with app.app_context():
        if not column_exists("employment_records", "date_to"):
            print("date_to sütunu artıq mövcud deyil — silməyə ehtiyac yoxdur.")
            return

        try:
            print("date_to sütunu silinir...")
            db.session.execute(
                text("ALTER TABLE employment_records DROP COLUMN date_to")
            )
            db.session.commit()
            print("date_to sütunu silindi.")
        except Exception as exc:
            db.session.rollback()
            print(
                "date_to sütununu silmək mümkün olmadı (DB versiyanız dəstəkləmir ola bilər): "
                f"{exc}\n"
                "Bu təhlükəli deyil — sütun sadəcə istifadə olunmadan qalacaq "
                "(kod artıq ona toxunmur). İstəsəniz DB alətinizlə əl ilə silə bilərsiniz."
            )

        print("Bitdi.")


if __name__ == "__main__":
    main()
