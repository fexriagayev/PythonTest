from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db

class BildirisRecord(db.Model):
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

    __tablename__ = "bildiris_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    # --- Hissə 1: Bildiriş (always renewed on every change) ----------------
    number = db.Column(db.String(50), nullable=False)          # Bildirişin nömrəsi
    start_date = db.Column(db.Date, nullable=False)              # Başlama tarixi
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))   # Əmrin nömrəsi

    # --- Hissə 2: Məşğulluq --------------------------------------------------
    employment_classification_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
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

    employee = db.relationship("Employee", backref=db.backref(
        "bildiris_records", cascade="all, delete-orphan", lazy="dynamic"))
    order = db.relationship("Order")
    employment_classification = db.relationship("DictionaryItem", foreign_keys=[employment_classification_id])
    employment_position = db.relationship("DictionaryItem", foreign_keys=[employment_position_id])
    contract_type = db.relationship("DictionaryItem", foreign_keys=[contract_type_id])
    work_type = db.relationship("DictionaryItem", foreign_keys=[work_type_id])
    labor_type = db.relationship("DictionaryItem", foreign_keys=[labor_type_id])
    leave_category = db.relationship("LeaveCategory")


class LeaveReason(db.Model):
    """
    'İş buraxma səbəbi' (İş buraxmaları → dictionary) — a structured
    dictionary because each reason needs a day-counting rule for computing
    the end date automatically:
      - calendar:              end = start + day_count - 1 (all days count)
      - workdays:               weekends don't count towards day_count
      - workdays_no_holidays:    weekends AND Holiday-table dates don't count
    """

    __tablename__ = "leave_reasons"

    COUNTING_METHODS = [
        ("calendar", "Təqvim günləri (hamısı)"),
        ("workdays", "İş günləri (həftə sonu xaric)"),
        ("workdays_no_holidays", "İş günləri (həftə sonu + bayram/matəm xaric)"),
    ]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    counting_method = db.Column(db.String(30), nullable=False, default="calendar")
    # Marks the reason that represents ordinary paid leave, i.e. the one
    # that draws down the Məzuniyyət günləri balance and needs the
    # available-days check before it can be submitted.
    is_annual_leave = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def counting_method_label(self):
        return dict(self.COUNTING_METHODS).get(self.counting_method, self.counting_method)


class Holiday(db.Model):
    """A single bayram/matəm (public holiday) date, excluded from day
    counts for leave reasons using the 'workdays_no_holidays' method."""

    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    name = db.Column(db.String(150))





class VacationCompensation(db.Model):
    """
    Manual entry recording how many unused base/bonus vacation days were
    paid out (compensated) for a given computed leave period. Leave
    periods themselves are computed on the fly (see
    app/services/leave_service.py), so this is matched back to a period by
    (employee_id, period_start) rather than a foreign key to a stored row.
    """

    __tablename__ = "vacation_compensations"
    __table_args__ = (db.UniqueConstraint("employee_id", "period_start", name="uq_employee_period"),)

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    compensated_base_days = db.Column(db.Integer, default=0)
    compensated_bonus_days = db.Column(db.Integer, default=0)
    note = db.Column(db.Text)

    employee = db.relationship("Employee", backref=db.backref(
        "vacation_compensations", cascade="all, delete-orphan", lazy="dynamic"))


class InsurancePolicy(db.Model):
    """'Sığorta məlumatları' tab. Start/end dates power the dashboard
    'expired / expiring within a month' notifications."""

    __tablename__ = "insurance_policies"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    insurance_company_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    insurance_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    policy_number = db.Column(db.String(50))
    amount = db.Column(db.Numeric(12, 2))
    note = db.Column(db.Text)

    employee = db.relationship("Employee", backref=db.backref(
        "insurance_policies", cascade="all, delete-orphan", lazy="dynamic"))
    insurance_company = db.relationship("DictionaryItem", foreign_keys=[insurance_company_id])
    insurance_type = db.relationship("DictionaryItem", foreign_keys=[insurance_type_id])


class SalaryCard(db.Model):
    """'Maaş kartları' tab. valid_until powers the dashboard 'expired /
    expiring within a month' notifications."""

    __tablename__ = "salary_cards"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    bank_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    account_number = db.Column(db.String(50))
    valid_until = db.Column(db.Date)
    card_holder_name = db.Column(db.String(150))
    note = db.Column(db.Text)

    employee = db.relationship("Employee", backref=db.backref(
        "salary_cards", cascade="all, delete-orphan", lazy="dynamic"))
    bank = db.relationship("DictionaryItem", foreign_keys=[bank_id])


class Document(db.Model):
    """'Sənədlər' tab — uploaded files (ID photo, driving licence, etc.)."""

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)  # actual name on disk
    document_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    note = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref=db.backref(
        "documents", cascade="all, delete-orphan", lazy="dynamic"))
    document_type = db.relationship("DictionaryItem", foreign_keys=[document_type_id])

