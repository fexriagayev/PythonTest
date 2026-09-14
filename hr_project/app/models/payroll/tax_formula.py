from app import db
from datetime import date, datetime


# ---------------------------------------------------------------------------
# The 7 statutory payroll deduction/contribution CODES this app knows about.
# `template_script` is ONLY used to prefill the textarea when someone opens
# "+ Yeni versiya" for a code that has NEVER been configured — it is a
# starting point to edit, NOT a silently-applied default: until a real
# PayrollTaxFormula row is saved for a code, that deduction/contribution
# calculates as 0 (see get_script_for_date() below) and the list page shows
# it as "not configured", rather than quietly using built-in numbers nobody
# has reviewed.
#
# Two "sides" (bax: SIDE_BY_CODE / EMPLOYEE_CODES / EMPLOYER_CODES):
#   - employee: ƏMƏKDAŞIN gəlirindən TUTULUR (net əməkhaqqısını azaldır).
#   - employer: ŞİRKƏTİN hesabından ƏLAVƏ ÖDƏNİLİR (əməkdaşın net
#     əməkhaqqısına TƏSİR ETMİR — əməkdaşın gross-u üzərinə şirkətin
#     ƏLAVƏ xərci kimi gəlir; bax: PayrollEntry.employer_cost_total).
#
# QEYD — gəlir vergisi ÜÇÜN YALNIZ 1 formula var (income_tax): şirkət
# daxilində eyni əməkhaqqı siyahısında iki fərqli gəlir vergisi
# hesablanması olmadığından, əvvəlki sektor-əsaslı ("neft-qaz" / "qeyri-
# neft-qaz") ayrım LƏĞV OLUNUB.
#
# QEYD — `sick` dəyişəni: hər formula skriptinə `gross`-la YANAŞI `sick`
# (bu dövrün xəstəlik pulu cəmi) də ötürülür (bax:
# app.services.formula_engine, payroll_service.calculate_gross_to_net).
# Aşağıdakı DSMF/işsizlik/İTS (hər iki tərəf) nümunə skriptləri
# `gross - sick` yazaraq xəstəlik pulunu bazadan çıxarır — bu, ADƏTƏN
# doğrudur (xəstəlik pulundan yalnız gəlir vergisi tutulur), amma SİZİN
# real qanunvericiliyinizə uyğun DEYİŞDİRİLƏ bilər/lazımdır. Gəlir
# vergisi isə `sick`-i İSTİFADƏ ETMİR — TAM gross üzərindən hesablanır
# (xəstəlik pulunun öz ayrıca vergisi ARTIQ sistemin özü tərəfindən
# əlavə olunur, bax: calculate_gross_to_net-dəki izah).
# ---------------------------------------------------------------------------
CODES = [
    ("income_tax", "Gəlir vergisi", "employee",
     "if gross <= 200:\n"
     "    result = 0.0\n"
     "elif gross <= 2500:\n"
     "    result = (gross - 200) * 0.03\n"
     "elif gross <= 8000:\n"
     "    result = 75 + (gross - 2500) * 0.10\n"
     "else:\n"
     "    result = 625 + (gross - 8000) * 0.14\n"),
    ("dsmf", "DSMF (məcburi dövlət sosial sığorta haqqı, işçi payı)", "employee",
     "base = gross - sick\n"
     "if base <= 200:\n"
     "    result = base * 0.03\n"
     "else:\n"
     "    result = 6 + (base - 200) * 0.10\n"),
    ("unemployment", "İşsizlikdən sığorta haqqı (işçi payı)", "employee",
     "result = (gross - sick) * 0.005\n"),
    ("medical", "İTS (icbari tibbi sığorta haqqı, işçi payı)", "employee",
     "base = gross - sick\n"
     "if base <= 2500:\n"
     "    result = base * 0.02\n"
     "else:\n"
     "    result = 50 + (base - 2500) * 0.005\n"),
    ("employer_dsmf", "DSMF — işəgötürən (şirkət) payı", "employer",
     "result = (gross - sick) * 0.22\n"),
    ("employer_unemployment", "İşsizlikdən sığorta haqqı — işəgötürən (şirkət) payı", "employer",
     "result = (gross - sick) * 0.005\n"),
    ("employer_medical", "İTS — işəgötürən (şirkət) payı", "employer",
     "result = (gross - sick) * 0.02\n"),
]

TEMPLATE_SCRIPTS = {code: script for code, _name, _side, script in CODES}
CODE_NAMES = {code: name for code, name, _side, _script in CODES}
SIDE_BY_CODE = {code: side for code, _name, side, _script in CODES}
EMPLOYEE_CODES = [code for code, _name, side, _script in CODES if side == "employee"]
EMPLOYER_CODES = [code for code, _name, side, _script in CODES if side == "employer"]


class PayrollTaxFormula(db.Model):
    """One dated VERSION of a statutory tax/deduction/contribution formula.

    Each `code` (bax: CODES yuxarıda) çoxlu sətrə malik ola bilər — bu,
    qəsdən bir tarixçə (history) cədvəlidir, tək bir "cari dəyər" cədvəli
    yox: qanunvericilik illər üzrə dəyişdiyi üçün (məs. DSMF dərəcəsi 2025
    və 2026-cı illərdə fərqli ola bilər), köhnə bir dövr üçün YENİDƏN
    hesablama aparılanda O DÖVR üçün qüvvədə olmuş formula işləməlidir —
    bax: get_script_for_date().

    `valid_from` is always set; `valid_to` is NULL for the currently open
    ("qüvvədədir", still in effect) version. Heç bir kod üçün əvvəlcədən
    "default" sətir YARADILMIR — istifadəçi ("Vergi formulaları"
    səhifəsindən) heç olmasa bir versiya ƏLAVƏ EDƏNƏ qədər, o kod üçün
    HESABLAMA 0 verir (bax: get_script_for_date, payroll_service._run_tax_formula).
    """

    __tablename__ = "payroll_tax_formulas"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    script = db.Column(db.Text, nullable=False)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=True)  # NULL = hələ də qüvvədədir
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])

    @classmethod
    def get_script_for_date(cls, code, as_of_date):
        """`as_of_date`-də (məs. hesablanan Tabel dövrünün son günü) `code`
        üçün QÜVVƏDƏ olan skripti qaytarır. Həmin tarixi əhatə edən HEÇ bir
        versiya tapılmasa — None qaytarır (çağıran bunu "bu tutulma tətbiq
        olunmur, 0" kimi başa düşməlidir — bax: payroll_service.py
        _run_tax_formula). Görünməz, təsdiqlənməmiş bir default
        İSTİFADƏ OLUNMUR."""
        row = (
            cls.query.filter(
                cls.code == code,
                cls.valid_from <= as_of_date,
                db.or_(cls.valid_to.is_(None), cls.valid_to >= as_of_date),
            )
            .order_by(cls.valid_from.desc())
            .first()
        )
        return row.script if row else None

    @classmethod
    def current_version(cls, code):
        """Bu GÜN üçün qüvvədə olan versiyanı (PayrollTaxFormula sətrini,
        skript mətnini yox) qaytarır — siyahı səhifəsində göstərmək üçün.
        Heç bir versiya konfiqurasiya olunmayıbsa None."""
        today = date.today()
        return (
            cls.query.filter(
                cls.code == code,
                cls.valid_from <= today,
                db.or_(cls.valid_to.is_(None), cls.valid_to >= today),
            )
            .order_by(cls.valid_from.desc())
            .first()
        )

    @classmethod
    def history_for_code(cls, code):
        """Bu kod üçün BÜTÜN versiyalar (tarixçə), ən yenisi əvvəldə."""
        return (
            cls.query.filter_by(code=code)
            .order_by(cls.valid_from.desc())
            .all()
        )

    @classmethod
    def heal_legacy_rows(cls):
        """Bu cədvəl "tarixli versiya" formasına keçirilməzdən ƏVVƏL
        yaradılmış "köhnə" sətirləri (valid_from sütunu hələ mövcud
        olmayan bir zamanda əlavə olunub, ona görə yüngül miqrasiya onu
        NULL olaraq əlavə edib) TƏMİR edir — idempotent, "Vergi
        formulaları" səhifəsi hər açılışda çağırır. Bunsuz, DB-nin bu
        keçid anında yaradılmış sətirləri tarixçə/redaktə səhifələrində
        `None.strftime(...)` xətası (500) ilə nəticələnirdi."""
        rows = cls.query.filter(cls.valid_from.is_(None)).all()
        if not rows:
            return
        for row in rows:
            row.valid_from = date(2000, 1, 1)
        db.session.commit()
