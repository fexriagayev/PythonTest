from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)   # HR / TABEL / SALARY
    name = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100))

    def __repr__(self):
        return f"<Module {self.code}>"


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False, default="")
    email = db.Column(db.String(150))

    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)

    # Admin can flip this flag per-user to start/stop activity logging
    log_flag = db.Column(db.Boolean, default=False, nullable=False)

    # Personal (Tools) preferences
    theme = db.Column(db.String(50), default="cosmo")
    font_size = db.Column(db.Integer, default=14)
    language = db.Column(db.String(5), default="az")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)

    permissions = db.relationship(
        "Permission", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def reset_to_default_password(self, default_password="test"):
        self.set_password(default_password)
        self.must_change_password = True

    def permission_for(self, module_code):
        return (
            self.permissions.join(Module)
            .filter(Module.code == module_code)
            .first()
        )

    def has_perm(self, module_code, field):
        if self.is_admin:
            return True
        perm = self.permission_for(module_code)
        if not perm:
            return False
        return bool(getattr(perm, field, False))

    def is_active_account(self):
        return not self.is_blocked

    def __repr__(self):
        return f"<User {self.username}>"


class Permission(db.Model):
    """One row per (user, module) holding the granular access flags."""

    __tablename__ = "permissions"
    __table_args__ = (db.UniqueConstraint("user_id", "module_id", name="uq_user_module"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)

    module = db.relationship("Module")

    # Main data permissions
    can_add = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_view = db.Column(db.Boolean, default=False)
    can_report = db.Column(db.Boolean, default=False)

    # Dictionary (reference book) permissions for this module
    dict_add = db.Column(db.Boolean, default=False)
    dict_edit = db.Column(db.Boolean, default=False)
    dict_delete = db.Column(db.Boolean, default=False)
    dict_view = db.Column(db.Boolean, default=False)


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(64))          # denormalised, survives user deletion
    module = db.Column(db.String(30))
    action = db.Column(db.String(50))             # ADD / EDIT / DELETE / VIEW / REPORT / LOGIN ...
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Module business data (simple starting versions, to be extended later)
# ---------------------------------------------------------------------------

class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)

    # --- S.A.A. (Soyadı, Adı, Atasının adı) ---------------------------------
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    father_name = db.Column(db.String(80))

    # --- Şəxsi məlumatlar — all combo fields point to DictionaryItem -------
    gender_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    family_status_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    education_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    birth_date = db.Column(db.Date)

    gender = db.relationship("DictionaryItem", foreign_keys=[gender_id])
    family_status = db.relationship("DictionaryItem", foreign_keys=[family_status_id])
    education_type = db.relationship("DictionaryItem", foreign_keys=[education_type_id])

    # Güzəşt — single-select dictionary (one benefit per employee)
    benefit_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    benefit = db.relationship("DictionaryItem", foreign_keys=[benefit_id])

    # --- Sənəd məlumatları ---------------------------------------------------
    fin_code = db.Column(db.String(20))              # S/V FİN nömrəsi
    id_card_number = db.Column(db.String(30))          # S/V seriya və nömrəsi
    social_insurance_number = db.Column(db.String(30))

    # --- İş məlumatları -------------------------------------------------------
    # NOTE: department, position, hire_date, termination_date, is_active,
    # total_experience, company_experience, other_experience are NO LONGER
    # manually edited on the employee form — they are auto-computed from the
    # employee's "İş yerləri" (əmək kitabçası) records. See
    # app/services/hr_service.py:recompute_employee_from_history().
    department = db.Column(db.String(120))
    position = db.Column(db.String(120))
    salary = db.Column(db.Numeric(12, 2))

    hire_date = db.Column(db.Date)                     # İşə başlama tarixi (auto)
    termination_date = db.Column(db.Date)               # İşdən çıxma tarixi (auto)
    contract_start_date = db.Column(db.Date)             # Müqavilənin başlama tarixi
    contract_end_date = db.Column(db.Date)                # Müqavilənin bitmə tarixi

    total_experience = db.Column(db.String(50))            # Ümumi staj (auto)
    company_experience = db.Column(db.String(50))           # Şirkətdə staj (auto)
    other_experience = db.Column(db.String(50))              # Digər iş yerlərində staj (auto)
    remaining_vacation_days = db.Column(db.Integer)            # Qalan məzuniyyət günü

    # --- Əlaqə / digər ------------------------------------------------------
    phone = db.Column(db.String(30))
    email = db.Column(db.String(150))
    note = db.Column(db.Text)                          # Qeyd
    photo_path = db.Column(db.String(255))              # Şəkil (foto)

    is_active = db.Column(db.Boolean, default=True)

    def full_name(self):
        return f"{self.last_name} {self.first_name}"


class TabelEntry(db.Model):
    __tablename__ = "tabel_entries"
    __table_args__ = (db.UniqueConstraint("employee_id","work_date", name="uq_tabel_employee_date"),)

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False)
    hours_worked = db.Column(db.Float, default=8)
    status = db.Column(db.String(30), default="present")  # present/absent/vacation/sick
    note = db.Column(db.String(255))

    employee = db.relationship("Employee")


class SalaryEntry(db.Model):
    __tablename__ = "salary_entries"
    __table_args__ = (db.UniqueConstraint("employee_id","period", name="uq_salary_employee_period"),)

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    period = db.Column(db.String(7), nullable=False)  # "YYYY-MM"
    base_salary = db.Column(db.Numeric(12, 2), default=0)
    bonus = db.Column(db.Numeric(12, 2), default=0)
    deductions = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    note = db.Column(db.String(255))

    employee = db.relationship("Employee")


class DictionaryItem(db.Model):
    """Generic reference-book (dictionary) entry, scoped per module + category."""

    __tablename__ = "dictionary_items"

    id = db.Column(db.Integer, primary_key=True)
    module_code = db.Column(db.String(20), nullable=False)   # HR / TABEL / SALARY
    category = db.Column(db.String(60), nullable=False)      # e.g. department, position, status
    name = db.Column(db.String(150), nullable=False)
    value = db.Column(db.String(150))
    is_active = db.Column(db.Boolean, default=True)


class Order(db.Model):
    """
    'Əmr' (kadr əmri) — a structured HR dictionary entity (not a plain
    name/value DictionaryItem, since it needs several real fields). Used to
    justify hiring, internal transfer, or termination records in an
    employee's əmək kitabçası (EmploymentRecord).
    """

    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), nullable=False)            # Əmrin nömrəsi
    order_date = db.Column(db.Date, nullable=False)                # Əmrin tarixi
    effective_date = db.Column(db.Date)                              # Qüvvəyə minmə tarixi
    order_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))  # Əmrin növü
    note = db.Column(db.Text)                                          # Qeyd

    order_type = db.relationship("DictionaryItem")

    def label(self):
        type_name = self.order_type.name if self.order_type else ""
        return f"№{self.number} / {self.order_date} — {type_name}"


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
    date_to = db.Column(db.Date)   # boş = hazırda davam edir (yalnız cari şirkət üçün mümkündür)
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref=db.backref(
        "employment_records", cascade="all, delete-orphan", lazy="dynamic"))
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


class GridPreference(db.Model):
    """
    Per-user, per-grid customisation (column order/visibility/titles,
    footer & group-footer aggregate choices, grouping, sorting) stored in
    the database so it follows the user across browsers/devices, instead
    of living only in one browser's localStorage.
    """

    __tablename__ = "grid_preferences"
    __table_args__ = (db.UniqueConstraint("user_id", "grid_key", name="uq_user_grid"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    grid_key = db.Column(db.String(100), nullable=False)
    settings_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ErrorReport(db.Model):
    """Stores a copy of every error report sent to the developer (even if
    the outgoing email itself fails), so nothing is lost."""

    __tablename__ = "error_reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(64))
    url = db.Column(db.String(500))
    message = db.Column(db.Text)
    stack = db.Column(db.Text)
    last_action = db.Column(db.Text)
    screenshot_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_sent = db.Column(db.Boolean, default=False)


class LeaveCategory(db.Model):
    """
    'Kateqoriya' (Bildirişlər → Part 5) — a structured HR dictionary that
    drives vacation-day calculations, not just a plain name/value. Example:
    'Dövlət qulluqçusu': 30 base days, +2 extra days every 5 years of
    seniority, capped at 6 extra days total.
    """

    __tablename__ = "leave_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    base_vacation_days = db.Column(db.Integer, nullable=False, default=30)

    # Seniority bonus rule: +bonus_days_per_interval every
    # seniority_years_per_bonus years of service, capped at max_bonus_days.
    seniority_years_per_bonus = db.Column(db.Integer, default=0)   # e.g. 5 (years)
    bonus_days_per_interval = db.Column(db.Integer, default=0)      # e.g. 2 (days)
    max_bonus_days = db.Column(db.Integer, default=0)                # e.g. 6 (days)

    is_active = db.Column(db.Boolean, default=True)

    def extra_days_for_years(self, years_of_service):
        """How many bonus vacation days someone with this category and this
        much seniority is entitled to (capped at max_bonus_days)."""
        if not self.seniority_years_per_bonus or not self.bonus_days_per_interval:
            return 0
        intervals = int(years_of_service) // self.seniority_years_per_bonus
        earned = intervals * self.bonus_days_per_interval
        return min(earned, self.max_bonus_days or earned)

    def total_days_for_years(self, years_of_service):
        return (self.base_vacation_days or 0) + self.extra_days_for_years(years_of_service)


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


class LeaveRequest(db.Model):
    """'İş buraxmaları' — a single absence record (sick leave, annual
    leave, etc.). end_date is always derived from start_date + day_count
    using the linked LeaveReason's counting method."""

    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    leave_reason_id = db.Column(db.Integer, db.ForeignKey("leave_reasons.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    day_count = db.Column(db.Integer, nullable=False)
    end_date = db.Column(db.Date, nullable=False)   # computed, stored for fast querying/overlap checks
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref=db.backref(
        "leave_requests", cascade="all, delete-orphan", lazy="dynamic"))
    leave_reason = db.relationship("LeaveReason")
    order = db.relationship("Order")


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

