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
      - manual: məbləğ əməkdaşın "İcazələri" pəncərəsində, HƏR AY üçün
        AYRICA (bax: LeaveRequestMonthlyPayment — ay sərhədini keçən bir
        iş buraxması üçün hər ayın öz sahəsi var) daxil edilir və
        əməkhaqqı hesablanarkən oradan olduğu kimi götürülür.
      - auto: sistemin özü hesablayır (bax: payroll_service.py
        `_auto_vacation_pay` — orta gündəlik qazanc əsasında, TƏXMİNİ
        düstur; qanunvericiliyə uyğun dəqiqləşdirmə tələb edir).
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

    id = db.Column(db.Integer, primary_key=True)
    calc_method = db.Column(db.String(20), nullable=False, default="gross_to_net")
    vacation_pay_mode = db.Column(db.String(10), nullable=False, default="manual")
    sick_pay_mode = db.Column(db.String(10), nullable=False, default="manual")

    @classmethod
    def get(cls):
        settings = cls.query.get(1)
        if not settings:
            settings = cls(id=1)
            db.session.add(settings)
            db.session.commit()
        return settings


class SalaryAddition(db.Model):
    """Bir əməkdaşa (və ya bütün əməkdaşlara) aid, tarix aralığı və əsas
    əmr ilə təsdiqlənən əməkhaqqı əlavəsi/tutulması. NÖVÜ (Mükafat, Aliment
    və s.) sərbəst mətn DEYİL — `addition_type` (DictionaryItem,
    module_code=SALARY, category="salary_addition_type") kitabçasından
    seçilir; həmin kitabça qeydinin `value`-si "addition" (əlavədir, gross-a
    gəlir) və ya "deduction" (tutulmadır, NET-dən çıxılır) olur — bax:
    `is_deduction` və payroll_service.py `recalculate_entry`.

    Əməkhaqqı hesablanarkən qüvvədə olan bütün uyğun əlavə/tutulmalar
    avtomatik toplanır (bax: payroll_service.py `applicable_additions`).
    Bu siyahı "Əməkhaqqı əlavələri" pəncərəsindən (bax: salary/routes.py
    `employee_additions`) — konkret əməkdaşın əməkhaqqı sətrini
    "Dəyiş" edərkən — idarə olunur; ayrıca ümumi "Əlavələr" menyusu YOXDUR.
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
    addition_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))

    amount_type = db.Column(db.String(10), nullable=False, default="fixed")
    amount = db.Column(db.Numeric(12, 2))  # amount_type == "fixed" olduqda
    percent = db.Column(db.Numeric(5, 2))  # amount_type == "percent" olduqda

    scope = db.Column(db.String(15), nullable=False, default="individual")

    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date)  # NULL = müddətsiz (cari dövrədək qüvvədədir)

    # Ödəniş tarixi (ixtiyari). DOLDURULUBSA — bu əlavə (məs. mükafat) BİR
    # DƏFƏLİK, məhz bu tarixdə ayrıca ödənilir (ay ərzində bir neçə mükafat
    # varsa, hər biri öz tarixi ilə ayrı sətir olur) və yalnız bu tarixin
    # ayına aiddir (valid_from/valid_to həmin ayın 1-i/son günü kimi avtomatik
    # təyin olunur — bax: salary/routes.py _apply_addition_form). BOŞDURSA —
    # əvvəlki kimi hər ay tətbiq olunur və ayın SON günü, əməkhaqqı ilə
    # eyni vaxtda ödənilir.
    pay_date = db.Column(db.Date)

    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    note = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order")
    addition_type = db.relationship("DictionaryItem")
    employees = db.relationship(
        "Employee",
        secondary="salary_addition_employees",
        backref=db.backref("salary_additions", lazy="dynamic"),
    )

    def type_name(self):
        return self.addition_type.name if self.addition_type else "—"

    def is_deduction(self):
        return bool(self.addition_type and self.addition_type.value == "deduction")

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
        """Bu əlavənin/tutulmanın bir əməkdaş üçün məbləği (`base_salary`
        — həmin əməkdaşın aylıq maaşı, faiz əsası kimi istifadə olunur).
        İşarə YOXDUR — müsbət ədəd qaytarır, əlavədirmi/tutulmadırmı
        sualı `is_deduction()` ilə ayrıca yoxlanılır."""
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
    üzrə əməkhaqqı sətri. Manual sahə YOXDUR — `vacation_pay`/`sick_pay`
    (LeaveRequest-dən) və `bonus_total`/`deductions_total`
    (SalaryAddition-dan, "Əməkhaqqı əlavələri" pəncərəsi vasitəsilə)
    daxil olmaqla bütün sahələr `payroll_service.recalculate_entry()`
    tərəfindən öz mənbələrindən hesablanır.
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

    # --- Əlavə əməkhaqqı (Obyektlər üzrə görülən işlər — BriqadaWorkEntry) --------
    # Modulda NET kimi daxil edilən (təsdiqlənmiş) avans + yekun məbləğlərdən
    # NET -> GROSS tərs hesablama ilə tapılan ÜMUMİ gross MİNUS baza məbləğ
    # (base_amount = aylıq maaş x işlənmiş gün / norma). Hesablama zamanı
    # yadda saxlanılır (bax: payroll_service.recalculate_entry); ödəniş-ödəniş
    # bölgüsü PayrollPayment.gross_amount / target_net-dədir.
    additional_salary = db.Column(db.Numeric(12, 2), default=0)

    # --- Törəmə sahələr (LeaveRequest-dən) -------------------------------------
    vacation_pay = db.Column(db.Numeric(12, 2), default=0)  # məzuniyyət pulu
    sick_pay = db.Column(db.Numeric(12, 2), default=0)  # xəstəlik pulu

    # --- Mükafat / Tutulmalar (SalaryAddition) --------------------------------
    # bonus_total (MÜKAFAT): GROSS-a daxil edilən "əlavə" növlü sətirlərin cəmi.
    # deductions_total: vergi hesablanmış NET-dən çıxılan "tutulma" növlü
    # sətirlərin cəmi (bax: payroll_service.py — tutulmalar VERGİYƏ CƏLB
    # OLUNAN gross-u azaltmır, yalnız əldə olunan NET-i azaldır, ki gəlir
    # vergisi/DSMF və s. düzgün — tam gross üzərindən hesablansın).
    bonus_total = db.Column(db.Numeric(12, 2), default=0)
    bonus_detail = db.Column(db.JSON, default=list)  # [{"name":..,"amount":..}]
    deductions_total = db.Column(db.Numeric(12, 2), default=0)
    deductions_detail = db.Column(db.JSON, default=list)  # [{"name":..,"amount":..}]

    # --- Nəticə ----------------------------------------------------------------
    gross_total = db.Column(db.Numeric(12, 2), default=0)
    income_tax = db.Column(db.Numeric(12, 2), default=0)
    dsmf_amount = db.Column(db.Numeric(12, 2), default=0)
    unemployment_amount = db.Column(db.Numeric(12, 2), default=0)
    medical_amount = db.Column(db.Numeric(12, 2), default=0)
    net_total = db.Column(db.Numeric(12, 2), default=0)  # tutulmalar çıxıldıqdan sonrakı yekun net

    # --- İşəgötürənin (şirkətin) ƏLAVƏ ödədiyi haqlar -------------------------
    # Bunlar əməkdaşın NET-inə TƏSİR ETMİR — GROSS-un üzərinə şirkətin əlavə
    # xərci kimi gəlir (bax: payroll_service.calculate_gross_to_net,
    # PayrollTaxFormula employer_dsmf/employer_unemployment/employer_medical).
    employer_dsmf = db.Column(db.Numeric(12, 2), default=0)
    employer_unemployment = db.Column(db.Numeric(12, 2), default=0)
    employer_medical = db.Column(db.Numeric(12, 2), default=0)
    employer_cost_total = db.Column(db.Numeric(12, 2), default=0)  # gross_total + yuxarıdakı 3-ü

    note = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    payroll_run = db.relationship("PayrollRun", back_populates="entries")
    employee = db.relationship("Employee")
    payments = db.relationship(
        "PayrollPayment",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="PayrollPayment.pay_date, PayrollPayment.sort_no",
    )


class PayrollPayment(db.Model):
    """Bir əməkdaşın BİR TARİXDƏ, BİR NÖV üzrə ayrıca hesablanmış (və
    ödənilən) məbləği. Bir ay ərzində eyni əməkdaşa bir neçə ödəniş ola
    bilər (məs. 03.09 məzuniyyət, 11.09 yenə məzuniyyət, 15.09 mükafat,
    30.09 əsas əməkhaqqı) — hər biri AYRI sətirdir, öz gross, vergi/tutulma
    və NET məbləği ilə. Banka da məhz bu sətirlər (NET) göndərilir.

    Yekun `PayrollEntry.net_total` (və gross/vergi sahələri) bu sətirlərin
    CƏMİDİR — bax: payroll_service.recalculate_entry. Sətirlər hər
    "Hesabla"-da mənbələrdən (İş buraxmaları, Əlavələr, Tabel) yenidən
    qurulur; təsdiqlənmiş dövrün sətirlərinə toxunulmur.

    Vergilər AY ÜZRƏ KÜMÜLATİV bölünür (bax: payroll_service.
    allocate_payments): hər ödənişin vergisi = (bu ödənişə qədər olan
    gross-a düsturun nəticəsi) - (əvvəlki ödənişə qədər olan gross-a
    düsturun nəticəsi). Beləliklə sətirlərin vergi cəmi TAM ayın gross-u
    üzərindən hesablanan vergiyə (kəsrlərlə) DƏQİQ bərabər olur.
    """

    __tablename__ = "payroll_payments"

    KIND_SALARY = "salary"
    KIND_VACATION = "vacation"
    KIND_SICK = "sick"
    KIND_ADDITION = "addition"
    # ƏLAVƏ ƏMƏKHAQQI — "Obyektlər üzrə görülən işlər" modulundan: orada daxil edilən məbləğ
    # NET-dir (avans ayın 15-i, yekun ayın son günü ödənilir) — bax:
    # payroll_service.allocate_payments (net -> gross tərs hesablama).
    KIND_WORK_AVANS = "work_avans"
    KIND_WORK_FINAL = "work_final"
    WORK_KINDS = (KIND_WORK_AVANS, KIND_WORK_FINAL)
    KINDS = [
        (KIND_SALARY, "Əsas əməkhaqqı"),
        (KIND_VACATION, "Məzuniyyət pulu"),
        (KIND_SICK, "Xəstəlik pulu"),
        (KIND_ADDITION, "Mükafat"),
        (KIND_WORK_AVANS, "Əlavə əməkhaqqı — avans"),
        (KIND_WORK_FINAL, "Əlavə əməkhaqqı — yekun"),
    ]

    id = db.Column(db.Integer, primary_key=True)
    payroll_entry_id = db.Column(
        db.Integer, db.ForeignKey("payroll_entries.id"), nullable=False, index=True
    )
    sort_no = db.Column(db.Integer, default=0)  # eyni tarixdə sıra

    kind = db.Column(db.String(15), nullable=False)
    label = db.Column(db.String(250))  # məs. "Növbəti məzuniyyət (03.09.2026–16.09.2026)"
    pay_date = db.Column(db.Date, nullable=False, index=True)

    # Mənbə (izləmə üçün): "leave_payment" (LeaveRequestMonthlyPayment.id),
    # "leave_request" (auto rejimdə LeaveRequest.id), "addition"
    # (SalaryAddition.id) və ya NULL (əsas əməkhaqqı).
    source_type = db.Column(db.String(20))
    source_id = db.Column(db.Integer)

    gross_amount = db.Column(db.Numeric(12, 2), default=0)
    income_tax = db.Column(db.Numeric(12, 2), default=0)
    dsmf_amount = db.Column(db.Numeric(12, 2), default=0)
    unemployment_amount = db.Column(db.Numeric(12, 2), default=0)
    medical_amount = db.Column(db.Numeric(12, 2), default=0)
    # Aliment və s. "tutulma" növlü əlavələr (NET-dən çıxılır) — bu ayın
    # ƏSAS əməkhaqqı ödənişinə (kind=salary) aid edilir.
    deductions_amount = db.Column(db.Numeric(12, 2), default=0)
    net_amount = db.Column(db.Numeric(12, 2), default=0)  # BANKA gedən məbləğ
    # Yalnız obyekt işi ödənişləri üçün: modulda DAXİL EDİLMİŞ (təsdiqlənmiş)
    # net məbləğ. gross_amount ondan tərs hesablanır, net_amount isə bu
    # məbləğə bərabər çıxmalıdır (fərq olarsa — aydın görünsün deyə ayrıca saxlanılır).
    target_net = db.Column(db.Numeric(12, 2))

    employer_dsmf = db.Column(db.Numeric(12, 2), default=0)
    employer_unemployment = db.Column(db.Numeric(12, 2), default=0)
    employer_medical = db.Column(db.Numeric(12, 2), default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entry = db.relationship("PayrollEntry", back_populates="payments")

    def kind_label(self):
        return dict(self.KINDS).get(self.kind, self.kind)
