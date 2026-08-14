from app import db
from datetime import datetime


class EmploymentContractNotification(db.Model):
    """
    'Bildirişlər' (DSMF saytına daxil edilmiş məlumatların kopyası).

    Each row is a FULL snapshot of an employee's DSMF notification at a
    point in time. When e.g. only the salary changes, a brand new row is
    still created (Part 1 — number/date/order — is renewed every time),
    carrying over the unchanged parts from the previous row. This preserves
    a complete, auditable history — never edit history in place in normal
    use, just add a new row.

    The employee's Müqavilə (contract) start/end dates and Maaş (salary)
    shown on the main employee card are always read from the most recent
    row here (see app/services/hr_service.py).
    """

    __tablename__ = "employment_contract_notifications"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    # --- Hissə 1: Bildiriş (always renewed on every change) ----------------
    number = db.Column(db.String(50), nullable=False)  # Bildirişin nömrəsi
    start_date = db.Column(db.Date, nullable=False)  # Başlama tarixi
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))  # Əmrin nömrəsi

    # --- Hissə 2: Məşğulluq --------------------------------------------------
    employment_classification_id = db.Column(
        db.Integer, db.ForeignKey("dictionary_items.id")
    )
    employment_position_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    contract_number = db.Column(db.String(50))
    contract_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    contract_start_date = db.Column(db.Date)
    contract_end_date = db.Column(db.Date)

    # --- Hissə 3: İşin tipi ---------------------------------------------------
    work_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))

    # --- Hissə 4: Əməyin növü --------------------------------------------------
    labor_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))

    # --- Hissə 5: Kateqoriya ----------------------------------------------------
    leave_category_id = db.Column(db.Integer, db.ForeignKey("leave_categories.id"))

    # --- Hissə 6: Maaş -------------------------------------------------------
    salary = db.Column(db.Numeric(12, 2))

    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship(
        "Employee",
        backref=db.backref(
            "bildiris_records", cascade="all, delete-orphan", lazy="dynamic"
        ),
    )
    order = db.relationship("Order")
    employment_classification = db.relationship(
        "DictionaryItem", foreign_keys=[employment_classification_id]
    )
    employment_position = db.relationship(
        "DictionaryItem", foreign_keys=[employment_position_id]
    )
    contract_type = db.relationship("DictionaryItem", foreign_keys=[contract_type_id])
    work_type = db.relationship("DictionaryItem", foreign_keys=[work_type_id])
    labor_type = db.relationship("DictionaryItem", foreign_keys=[labor_type_id])
    leave_category = db.relationship("LeaveCategory")
