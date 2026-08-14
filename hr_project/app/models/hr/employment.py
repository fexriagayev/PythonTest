from app import db
from datetime import datetime
from .order import Order


class EmploymentRecord(db.Model):
    """
    A single 'əmək kitabçası' (labour book) line for an employee — the
    'İş yerləri' tab. The `is_current_company` flag is the "ticket" that
    decides whether this record is about the current company (dictionary-
    driven struktur/vəzifə + a linked Order) or an external / previous
    workplace (free-text struktur/vəzifə, start+end dates required, no order).
    """

    __tablename__ = "employment_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    is_current_company = db.Column(db.Boolean, default=True, nullable=False)

    # movement_type only applies when is_current_company=True:
    #   hire        -> İşə qəbul
    #   transfer    -> Daxili keçid (struktur/vəzifə dəyişikliyi)
    #   termination -> İşdən çıxma
    movement_type = db.Column(db.String(20))

    # --- Cari şirkət daxilində olduqda (dictionary-driven) ------------------
    department_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    position_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))

    # --- Cari şirkətdən kənar (əvvəlki iş yerləri) olduqda (sərbəst mətn) ---
    external_company_name = db.Column(db.String(200))
    external_department = db.Column(db.String(200))
    external_position = db.Column(db.String(200))

    # --- Ümumi (hər iki halda) -----------------------------------------------
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(
        db.Date
    )  # boş = hazırda davam edir (yalnız cari şirkət üçün mümkündür)
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship(
        "Employee",
        backref=db.backref(
            "employment_records", cascade="all, delete-orphan", lazy="dynamic"
        ),
    )
    department = db.relationship("DictionaryItem", foreign_keys=[department_id])
    position = db.relationship("DictionaryItem", foreign_keys=[position_id])
    order = db.relationship("Order")

    def workplace_label(self):
        if self.is_current_company:
            return self.department.name if self.department else "Cari şirkət"
        return self.external_company_name or "Kənar iş yeri"

    def position_label(self):
        if self.is_current_company:
            return self.position.name if self.position else ""
        return self.external_position or ""
