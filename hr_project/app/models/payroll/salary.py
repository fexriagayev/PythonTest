from app import db
from datetime import datetime


class PayrollSettings(db.Model):
    """Tək sətirlik (singleton, id=1) əməkhaqqı hesablama tənzimləmələri.

    `calc_method`:
      - gross_to_net: hər əməkdaşın maaşı GROSS (bruto) kimi daxil edilir,
        vergi/tutulmalar bu məbləğdən çıxılıb NET tapılır.
      - net_to_gross: (HƏLƏLİK TƏTBİQ OLUNMUR — gələcək mərhələ) əməkdaşın
        maaşı NET kimi daxil ediləcək, əvvəlcə GROSS-a "yuxarı" hesablanacaq,
        sonra normal qaydada həmin GROSS-dan yenidən NET tapılacaq.

    `vacation_pay_mode` / `sick_pay_mode`:
      - manual: məbləğ əməkdaşın "İcazələri" pəncərəsində həmin İş
        buraxması qeydinə birbaşa daxil edilir (LeaveRequest.payment_amount)
        və əməkhaqqı hesablanarkən oradan olduğu kimi götürülür.
      - auto: sistemin özü hesablayır (bax: payroll_service.py
        `_auto_vacation_pay` — orta gündəlik qazanc əsasında, TƏXMİNİ
        düstur; qanunvericiliyə uyğun dəqiqləşdirmə tələb edir).

    `sector`: gəlir vergisi/DSMF/İTS düsturunun hansı sektor üçün
      tətbiq olunacağını təyin edir (bax: payroll_service.py TAX_TABLES).
    """

    __tablename__ = "payroll_settings"

    CALC_METHODS = [
        ("gross_to_net", "Gross → Net"),
        ("net_to_gross", "Net → Gross → Net (hələlik mövcud deyil)"),
    ]
    PAY_MODES = [
        ("manual", "Manual (İcazələr pəncərəsindən)"),
        ("auto", "Avtomatik hesablanır"),
    ]
    SECTORS = [
        ("private_non_oil", "Qeyri-neft-qaz / qeyri-dövlət sektoru"),
        ("state_oil_gas", "Neft-qaz sahəsi / dövlət sektoru"),
    ]

    id = db.Column(db.Integer, primary_key=True)
    calc_method = db.Column(db.String(20), nullable=False, default="gross_to_net")
    vacation_pay_mode = db.Column(db.String(10), nullable=False, default="manual")
    sick_pay_mode = db.Column(db.String(10), nullable=False, default="manual")
    sector = db.Column(db.String(20), nullable=False, default="private_non_oil")

    @classmethod
    def get(cls):
        settings = cls.query.get(1)
        if not settings:
            settings = cls(id=1)
            db.session.add(settings)
            db.session.commit()
        return settings


class SalaryAddition(db.Model):
    """'Əlavə' — hamıya və ya seçilmiş əməkdaşlara aid edilə bilən, tarix
    aralığı və əsas əmr ilə təsdiqlənən əməkhaqqı əlavəsi (məs. "Ştat üzrə
    əlavə", "Səmərəlilik əlavəsi" və s.). Əməkhaqqı hesablanarkən qüvvədə
    olan bütün uyğun əlavələr avtomatik toplanır (bax: payroll_service.py
    `applicable_additions`).
    """

    __tablename__ = "salary_additions"

    AMOUNT_TYPES = [
        ("fixed", "Sabit məbləğ"),
        ("percent", "Maaşın faizi"),
    ]
    SCOPES = [
        ("all", "Bütün əməkdaşlar"),
        ("individual", "Seçilmiş əməkdaşlar"),
    ]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    amount_type = db.Column(db.String(10), nullable=False, default="fixed")
    amount = db.Column(db.Numeric(12, 2))  # amount_type == "fixed" olduqda
    percent = db.Column(db.Numeric(5, 2))  # amount_type == "percent" olduqda

    scope = db.Column(db.String(15), nullable=False, default="all")

    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date)  # NULL = müddətsiz (hələ qüvvədən düşməyib)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    note = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order")
    employees = db.relationship(
        "Employee",
        secondary="salary_addition_employees",
        backref=db.backref("salary_additions", lazy="dynamic"),
    )

    def amount_type_label(self):
        return dict(self.AMOUNT_TYPES).get(self.amount_type, self.amount_type)

    def scope_label(self):
        return dict(self.SCOPES).get(self.scope, self.scope)

    def applies_on(self, d):
        """`d` (date) əlavənin qüvvədə olduğu tarix aralığına düşürmü?"""
        if not self.is_active:
            return False
        if self.valid_from and d < self.valid_from:
            return False
        if self.valid_to and d > self.valid_to:
            return False
        return True

    def overlaps_period(self, period_start, period_end):
        if not self.is_active:
            return False
        if self.valid_to and self.valid_to < period_start:
            return False
        if self.valid_from and self.valid_from > period_end:
            return False
        return True

    def amount_for(self, base_salary):
        """Bu əlavənin bir əməkdaş üçün məbləği (`base_salary` — həmin
        əməkdaşın aylıq maaşı, faiz əsası kimi istifadə olunur)."""
        if self.amount_type == "percent":
            return float(base_salary or 0) * float(self.percent or 0) / 100.0
        return float(self.amount or 0)


class SalaryAdditionEmployee(db.Model):
    """M2M: SalaryAddition <-> Employee (yalnız scope == 'individual' olduqda
    istifadə olunur)."""

    __tablename__ = "salary_addition_employees"
    __table_args__ = (
        db.UniqueConstraint(
            "addition_id", "employee_id", name="uq_addition_employee"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    addition_id = db.Column(
        db.Integer, db.ForeignKey("salary_additions.id"), nullable=False
    )
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employees.id"), nullable=False
    )


class PayrollRun(db.Model):
    """Bir TƏSDİQ OLUNMUŞ Tabel dövrü üçün əməkhaqqı hesablaması. Yalnız
    `period.is_approved == True` olan dövrlər üçün yaradıla bilər (bax:
    app/modules/salary/routes.py). "Yenidən hesabla" mövcud sətirləri
    (manual sahələr saxlanılmaqla) yeniləyir — silib-yenidən yaratmır.
    """

    __tablename__ = "payroll_runs"
    __table_args__ = (
        db.UniqueConstraint("period_id", name="uq_payroll_run_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(
        db.Integer, db.ForeignKey("tabel_periods.id"), nullable=False
    )

    calc_method = db.Column(db.String(20), nullable=False, default="gross_to_net")
    is_finalized = db.Column(db.Boolean, default=False, nullable=False)
    finalized_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    period = db.relationship("TabelPeriod")
    entries = db.relationship(
        "PayrollEntry",
        back_populates="payroll_run",
        cascade="all, delete-orphan",
        order_by="PayrollEntry.row_no",
    )


class PayrollEntry(db.Model):
    """Bir əməkdaşın bir PayrollRun (= bir təsdiqlənmiş Tabel dövrü)
    üzrə əməkhaqqı sətri. Manual sahələr (extra_amount, bonus və — manual
    rejimdə olmadıqda — vacation_pay/sick_pay) istifadəçi tərəfindən
    redaktə oluna bilər; qalanları `payroll_service.recalculate_entry()`
    tərəfindən hesablanır.
    """

    __tablename__ = "payroll_entries"
    __table_args__ = (
        db.UniqueConstraint(
            "payroll_run_id", "employee_id", name="uq_payroll_run_employee"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    payroll_run_id = db.Column(
        db.Integer, db.ForeignKey("payroll_runs.id"), nullable=False
    )
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    row_no = db.Column(db.Integer, default=0)

    # --- Generasiya anında "şəkli çəkilən" sahələr --------------------------
    full_name_snapshot = db.Column(db.String(200))
    position_snapshot = db.Column(db.String(120))

    # --- Əsas maaş (bildirişdən avtomatik, iş günlərinə görə proporsional) --
    monthly_salary = db.Column(db.Numeric(12, 2), default=0)  # bildirişdəki tam aylıq maaş
    norm_days = db.Column(db.Integer, default=0)  # ayın iş günü norması (tabel üzrə)
    worked_days = db.Column(db.Integer, default=0)  # faktiki işlənmiş gün ("+")
    base_amount = db.Column(db.Numeric(12, 2), default=0)  # monthly_salary * worked/norm

    # --- Manual/yarı-manual sahələr ------------------------------------------
    extra_amount = db.Column(db.Numeric(12, 2), default=0)  # əlavə əməkhaqqı (manual)
    vacation_pay = db.Column(db.Numeric(12, 2), default=0)  # məzuniyyət pulu
    sick_pay = db.Column(db.Numeric(12, 2), default=0)  # xəstəlik pulu
    bonus = db.Column(db.Numeric(12, 2), default=0)  # mükafat (manual)

    # --- Əlavələr (SalaryAddition) --------------------------------------------
    additions_total = db.Column(db.Numeric(12, 2), default=0)
    additions_detail = db.Column(db.JSON, default=list)  # [{"name":..,"amount":..}]

    # --- Nəticə ----------------------------------------------------------------
    gross_total = db.Column(db.Numeric(12, 2), default=0)
    income_tax = db.Column(db.Numeric(12, 2), default=0)
    dsmf_amount = db.Column(db.Numeric(12, 2), default=0)
    unemployment_amount = db.Column(db.Numeric(12, 2), default=0)
    medical_amount = db.Column(db.Numeric(12, 2), default=0)
    net_total = db.Column(db.Numeric(12, 2), default=0)

    note = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    payroll_run = db.relationship("PayrollRun", back_populates="entries")
    employee = db.relationship("Employee")


class SalaryEntry(db.Model):
    __tablename__ = "salary_entries"
    __table_args__ = (
        db.UniqueConstraint("employee_id", "period", name="uq_salary_employee_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    period = db.Column(db.String(7), nullable=False)  # "YYYY-MM"
    base_salary = db.Column(db.Numeric(12, 2), default=0)
    bonus = db.Column(db.Numeric(12, 2), default=0)
    deductions = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    note = db.Column(db.String(255))

    employee = db.relationship("Employee")
