"""employment_contract_notifications.work_type_id sütununu silir (work_type soraqçısı ləğv olunub).
SQLite FK-lı sütunu birbaşa silməyə icazə vermir -> cədvəl yenidən qurulur, data saxlanılır. Təkrar işlətmək təhlükəsizdir.
İstifadə: python scripts/migrate_drop_work_type.py app.db"""
import sqlite3, sys

db = sys.argv[1] if len(sys.argv) > 1 else "app.db"
con = sqlite3.connect(db)
cols = [r[1] for r in con.execute("PRAGMA table_info(employment_contract_notifications)")]
if "work_type_id" not in cols:
    print("work_type_id artıq yoxdur — dəyişiklik lazım deyil."); sys.exit(0)
keep = [c for c in cols if c != "work_type_id"]
con.execute("PRAGMA foreign_keys=OFF")
con.execute("BEGIN")
con.execute("""CREATE TABLE employment_contract_notifications_new (
    id INTEGER NOT NULL, employee_id INTEGER NOT NULL, number VARCHAR(50) NOT NULL, start_date DATE NOT NULL,
    order_id INTEGER, employment_classification_id INTEGER, employment_position_id INTEGER, contract_number VARCHAR(50),
    contract_type_id INTEGER, contract_start_date DATE, contract_end_date DATE, labor_type_id INTEGER,
    leave_category_id INTEGER, salary NUMERIC(12, 2), note TEXT, created_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(employee_id) REFERENCES employees (id), FOREIGN KEY(order_id) REFERENCES orders (id),
    FOREIGN KEY(employment_classification_id) REFERENCES dictionary_items (id),
    FOREIGN KEY(employment_position_id) REFERENCES dictionary_items (id),
    FOREIGN KEY(contract_type_id) REFERENCES dictionary_items (id),
    FOREIGN KEY(labor_type_id) REFERENCES dictionary_items (id),
    FOREIGN KEY(leave_category_id) REFERENCES leave_categories (id))""")
con.execute(f"INSERT INTO employment_contract_notifications_new ({','.join(keep)}) SELECT {','.join(keep)} FROM employment_contract_notifications")
con.execute("DROP TABLE employment_contract_notifications")
con.execute("ALTER TABLE employment_contract_notifications_new RENAME TO employment_contract_notifications")
con.commit()
bad = con.execute("PRAGMA foreign_key_check").fetchall()
print("Tamam. FK pozuntusu:", bad)
