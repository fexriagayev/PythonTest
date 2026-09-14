"""
Əməkhaqqı (payroll) hesablama məntiqi.

Hazırkı mərhələdə YALNIZ "gross → net" istiqaməti dəstəklənir
(PayrollSettings.calc_method == "gross_to_net"). Hər əməkdaşın maaşı GROSS
(bruto) qəbul edilir və aşağıdakı tutulmalar bu məbləğdən çıxılaraq NET
tapılır:

    Net = Gross - (Gəlir vergisi + DSMF + İşsizlikdən sığorta + İTS)

Bu tutulmaların (və işəgötürənin ƏLAVƏ ödədiyi, əməkdaşın NET-inə təsir
ETMƏYƏN DSMF/işsizlik/İTS "şirkət payı" haqlarının) DÜSTURLARI burada
sabit Python kodu kimi YOX, "Vergi formulaları" səhifəsindən redaktə
oluna bilən SKRİPT kimi `PayrollTaxFormula` cədvəlində saxlanılır (bax:
app.models.payroll.tax_formula) və `app.services.formula_engine`-in
MƏHDUDLAŞDIRILMIŞ (sandboxed) mühərriki ilə icra olunur.

VACİB: heç bir "gizli default" YOXDUR — hər hansı kod (income_tax, dsmf,
unemployment, medical, employer_dsmf, employer_unemployment,
employer_medical) üçün "Vergi formulaları" səhifəsindən HEÇ OLMASA bir
versiya əlavə edilməyibsə, həmin tutulma/haqq 0 kimi hesablanır — bu,
qəsdəndir (istifadəçi görmədiyi/təsdiqləmədiyi bir rəqəmin SƏSSİZCƏ
tətbiq olunmasının qarşısını almaq üçün).

Gəlir vergisi üçün YALNIZ 1 formula var (sektor-əsaslı ayrım YOXDUR —
şirkət daxilində eyni əməkhaqqı siyahısında 2 fərqli gəlir vergisi
hesablanması olmur).

XƏSTƏLİK PULU — XÜSUSİ VERGİ REJİMİ (bax: calculate_gross_to_net,
_vacation_and_sick_pay): xəstəlik pulundan YALNIZ gəlir vergisi tutulur —
DSMF/işsizlik/İTS (nə əməkdaş, nə işəgötürən payı) ONA TƏTBİQ OLUNMUR.
Gəlir vergisi isə İKİ addımda hesablanıb CƏMLƏNİR: (1) hər bir xəstəlik
ödənişinin ÖZÜ üzərindən (ayrılıqda, müstəqil), (2) ayın sonunda TAM
gross (xəstəlik pulu daxil) üzərindən YENƏ. Eyni ayda bir neçə xəstəlik
ödənişi olarsa, HƏR BİRİ üçün (1)-ci addım AYRI-AYRI hesablanıb sonda
(2) ilə birlikdə cəmlənir.

"net → gross → net" istiqaməti (PayrollSettings.calc_method ==
"net_to_gross") HƏLƏLİK İMPLEMENTASİYA OLUNMAYIB — istifadəçi ilə
razılaşdırıldığı kimi, əvvəlcə gross→net üzərində dayanılıb.
"""

from app import db
from app.models import (
    EmploymentContractNotification,
    LeaveRequest,
    LeaveReason,
    LeaveRequestMonthlyPayment,
    SalaryAddition,
    PayrollSettings,
    PayrollRun,
    PayrollEntry,
    PayrollTaxFormula,
    TabelEmployeeRow,
)
from app.services.tabel_service import month_bounds, _weekend_days, _holiday_marks
from app.services.formula_engine import evaluate_formula, FormulaError

# ---------------------------------------------------------------------------
# Vergi/tutulma formulaları — bax modul-səviyyəli qeyd yuxarıda
# ---------------------------------------------------------------------------


<<<<<<< HEAD
def _run_tax_formula(code, variables, as_of_date):
    """`code` üçün `as_of_date`-də (adətən hesablanan dövrün son günü)
    QÜVVƏDƏ olan skripti tapıb verilmiş dəyişənlərlə (bax:
    formula_engine.evaluate_formula — `variables` dict, HƏMİŞƏ ən azı
    `gross` və `sick` ehtiva edir) icra edir — bax:
=======
def _run_tax_formula(code, gross, as_of_date):
    """`code` üçün `as_of_date`-də (adətən hesablanan dövrün son günü)
    QÜVVƏDƏ olan skripti tapıb `gross` ilə icra edir — bax:
>>>>>>> 21ca2bddeb86717111e643c6503ac4af309eb6c6
    PayrollTaxFormula.get_script_for_date (köhnə dövr üçün YENİDƏN
    hesablama aparılanda O DÖVRÜN öz formulası işləyir, indiki YOX).
    Heç bir versiya konfiqurasiya olunmayıbsa (script=None) — 0 qaytarır
    (görünməz bir default TƏTBİQ OLUNMUR). Skriptdə xəta olsa (məs. kimsə
    "Vergi formulaları" səhifəsindən pozğun bir skript yadda saxlayıbsa),
    hesablamanı SƏSSİZCƏ yanlış davam etdirmək əvəzinə aydın bir istisna
    qaldırırıq — bu, tabel təsdiqi/əməkhaqqı generasiyası zamanı aşkar
    görünən bir xəta mesajına çevrilməlidir, gizli səhv məbləğə yox."""
    script = PayrollTaxFormula.get_script_for_date(code, as_of_date)
    if script is None:
        return 0.0
    try:
<<<<<<< HEAD
        return evaluate_formula(script, variables)
=======
        return evaluate_formula(script, gross)
>>>>>>> 21ca2bddeb86717111e643c6503ac4af309eb6c6
    except FormulaError as e:
        raise FormulaError(f"'{code}' vergi formulası icra edilə bilmədi: {e}")


def calculate_gross_to_net(gross, as_of_date=None, sick_pay_episodes=None):
    """Verilmiş GROSS məbləğdən tutulmaları (əməkdaş payı) VƏ işəgötürənin
    əlavə ödədiyi (şirkət payı, əməkdaşın NET-inə təsir ETMƏYƏN) haqları
    hesablayır. Mənfi əməkhaqqı (və ya 0) üçün hamısı 0 qaytarılır.

    `as_of_date`: HANSI TARİX üçün qüvvədə olan formulalar işləsin —
    adətən hesablanan Tabel dövrünün son günü verilir. Buraxılsa (None),
    BU GÜN üçün qüvvədə olan versiyalar işləyir (məs. sınaq/əl ilə
    hesablama zamanı münasib defolt).

    `sick_pay_episodes`: bu dövrdəki HƏR BİR xəstəlik pulu ödənişinin öz
    məbləği (cəm YOX, siyahı — eyni ayda bir neçə xəstəlik vərəqəsi ola
<<<<<<< HEAD
    bilər).

    VACİB — xəstəlik pulunun tutulmalara necə təsir etdiyini artıq
    SİSTEM YOX, HƏR FORMULANIN ÖZÜ təyin edir: hər formulaya `gross`
    (TAM, xəstəlik pulu daxil) İLƏ YANAŞI `sick` (bu dövrün xəstəlik
    pulu cəmi) DƏ ötürülür (bax: formula_engine.evaluate_formula).
    Formula istəsə `gross - sick` yazıb xəstəlik pulunu bazadan çıxara
    bilər (məs. DSMF/işsizlik/İTS formulaları üçün adətəndir), istəməsə
    sadəcə `gross` istifadə edir (məs. gəlir vergisi TAM gross üzərindən
    hesablanır, `sick`-i işlətmir). GƏLƏCƏKDƏ bənzər istisnalar üçün eyni
    qaydada yeni dəyişənlər əlavə oluna bilər.

    Gəlir vergisi ayrıca İKİ addımda hesablanır və CƏMLƏNİR: (1) HƏR bir
    xəstəlik ödənişinin ÖZÜ (ayrılıqda, müstəqil bir "gross" kimi)
    üzərindən gəlir vergisi düsturu tətbiq olunur; (2) ayın sonunda TAM
    gross (xəstəlik pulu daxil olmaqla) üzərindən YENƏ gəlir vergisi
    düsturu tətbiq olunur. Yekun gəlir vergisi bunların CƏMİDİR (nümunə:
    340.66 AZN xəstəlik pulu + 927.64 AZN tam gross → 4.22 + 21.83 =
    26.05 AZN gəlir vergisi)."""
=======
    bilər). Xəstəlik pulunun vergi rejimi FƏRQLİDİR (əməkdaşın xahişi
    əsasında bu funksionallıq belə təyin edilib):
      - Yalnız GƏLİR VERGİSİ tutulur — DSMF/işsizlik/İTS (nə əməkdaş, nə
        də işəgötürən payı) xəstəlik pulundan TUTULMUR/hesablanmır — bu
        3-ü üçün baza `gross - sick_pay_total`-dır (xəstəlik pulu tam
        çıxılır).
      - Gəlir vergisi İKİ addımda hesablanır və CƏMLƏNİR: (1) HƏR bir
        xəstəlik ödənişinin ÖZÜ (ayrılıqda, müstəqil bir "gross" kimi)
        üzərindən gəlir vergisi düsturu tətbiq olunur; (2) ayın sonunda
        TAM gross (xəstəlik pulu daxil olmaqla) üzərindən YENƏ gəlir
        vergisi düsturu tətbiq olunur. Yekun gəlir vergisi bunların
        CƏMİDİR (nümunə: 340.66 AZN xəstəlik pulu + 927.64 AZN tam gross
        → 4.22 + 21.83 = 26.05 AZN gəlir vergisi)."""
>>>>>>> 21ca2bddeb86717111e643c6503ac4af309eb6c6
    if as_of_date is None:
        from datetime import date
        as_of_date = date.today()
    gross = max(float(gross or 0), 0.0)
    sick_pay_episodes = [max(float(x or 0), 0.0) for x in (sick_pay_episodes or [])]
    sick_pay_total = round(sum(sick_pay_episodes), 2)

    if gross == 0:
        return {
            "income_tax": 0.0, "dsmf": 0.0, "unemployment": 0.0,
            "medical": 0.0, "net": 0.0,
            "employer_dsmf": 0.0, "employer_unemployment": 0.0,
            "employer_medical": 0.0, "employer_cost_total": 0.0,
        }

<<<<<<< HEAD
    main_vars = {"gross": gross, "sick": sick_pay_total}

    income_tax_on_full_gross = _run_tax_formula("income_tax", main_vars, as_of_date)
    income_tax_on_sick_episodes = sum(
        # Hər epizodun ÖZ məbləği üzərində müstəqil hesablama — burada
        # `sick`-i sıfır veririk (bu, "bu məbləğdən xəstəlik payını çıx"
        # demək deyil, artıq elə TAM özü xəstəlik pulu olan bir hesablamadır).
        _run_tax_formula("income_tax", {"gross": amt, "sick": 0.0}, as_of_date)
        for amt in sick_pay_episodes
    )
    income_tax = round(income_tax_on_full_gross + income_tax_on_sick_episodes, 2)

    dsmf = round(_run_tax_formula("dsmf", main_vars, as_of_date), 2)
    unemployment = round(_run_tax_formula("unemployment", main_vars, as_of_date), 2)
    medical = round(_run_tax_formula("medical", main_vars, as_of_date), 2)
    net = round(gross - income_tax - dsmf - unemployment - medical, 2)

    employer_dsmf = round(_run_tax_formula("employer_dsmf", main_vars, as_of_date), 2)
    employer_unemployment = round(_run_tax_formula("employer_unemployment", main_vars, as_of_date), 2)
    employer_medical = round(_run_tax_formula("employer_medical", main_vars, as_of_date), 2)
=======
    # DSMF/işsizlik/İTS (həm əməkdaş, həm işəgötürən payı) xəstəlik
    # pulunu ÜMUMİYYƏTLƏ nəzərə ALMIR — baza tam gross-dan xəstəlik pulu
    # çıxılaraq tapılır.
    non_sick_base = max(gross - sick_pay_total, 0.0)

    income_tax_on_full_gross = _run_tax_formula("income_tax", gross, as_of_date)
    income_tax_on_sick_episodes = sum(
        _run_tax_formula("income_tax", amt, as_of_date) for amt in sick_pay_episodes
    )
    income_tax = round(income_tax_on_full_gross + income_tax_on_sick_episodes, 2)

    dsmf = round(_run_tax_formula("dsmf", non_sick_base, as_of_date), 2)
    unemployment = round(_run_tax_formula("unemployment", non_sick_base, as_of_date), 2)
    medical = round(_run_tax_formula("medical", non_sick_base, as_of_date), 2)
    net = round(gross - income_tax - dsmf - unemployment - medical, 2)

    employer_dsmf = round(_run_tax_formula("employer_dsmf", non_sick_base, as_of_date), 2)
    employer_unemployment = round(_run_tax_formula("employer_unemployment", non_sick_base, as_of_date), 2)
    employer_medical = round(_run_tax_formula("employer_medical", non_sick_base, as_of_date), 2)
>>>>>>> 21ca2bddeb86717111e643c6503ac4af309eb6c6
    employer_cost_total = round(gross + employer_dsmf + employer_unemployment + employer_medical, 2)

    return {
        "income_tax": income_tax, "dsmf": dsmf, "unemployment": unemployment,
        "medical": medical, "net": net,
        "employer_dsmf": employer_dsmf, "employer_unemployment": employer_unemployment,
        "employer_medical": employer_medical, "employer_cost_total": employer_cost_total,
    }


# ---------------------------------------------------------------------------
# Əməkdaşın dövr üçün aylıq maaşı — Bildirişlərdən (EmploymentContractNotification)
# ---------------------------------------------------------------------------


def get_monthly_salary_at(employee, as_of_date):
    """Əməkdaşın `as_of_date`-ə aid ən son Bildirişindəki (Hissə 6: Maaş)
    məbləği — tabel_service._contract_number_at ilə EYNİ məntiq."""
    latest = (
        EmploymentContractNotification.query.filter(
            EmploymentContractNotification.employee_id == employee.id,
            EmploymentContractNotification.start_date <= as_of_date,
        )
        .order_by(
            EmploymentContractNotification.start_date.desc(),
            EmploymentContractNotification.created_at.desc(),
        )
        .first()
    )
    return float(latest.salary) if latest and latest.salary else 0.0


# ---------------------------------------------------------------------------
# Məzuniyyət / xəstəlik pulu
# ---------------------------------------------------------------------------


def _leave_requests_overlapping(employee_id, period_start, period_end, is_annual=None, is_sick=None):
    q = LeaveRequest.query.join(LeaveReason).filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.start_date <= period_end,
        LeaveRequest.end_date >= period_start,
    )
    if is_annual is not None:
        q = q.filter(LeaveReason.is_annual_leave == is_annual)
    if is_sick is not None:
        q = q.filter(LeaveReason.is_sick_leave == is_sick)
    return q.all()


def _auto_vacation_pay(employee, leave_request, period_start, period_end, monthly_salary):
    """TƏXMİNİ orta gündəlik qazanc üsulu: son 12 ayın PayrollEntry
    gross_total-larının ortalaması / 30.4 (orta təqvim ayı günü) x bu
    dövrə düşən məzuniyyət günü sayı. Tarixi PayrollEntry məlumatı
    yoxdursa (ilk hesablama), cari aylıq maaş əsas götürülür.

    QEYD: bu, sadələşdirilmiş yaxınlaşmadır — Əmək Məcəlləsinin dəqiq
    "orta əməkhaqqının hesablanması qaydası"na uyğun dəqiqləşdirmə tələb
    edir (son 12 təqvim ayı üzrə faktiki qazanc və faktiki iş günləri
    əsasında). Hazırda yalnız `vacation_pay_mode == "auto"` seçildikdə
    işə düşür — default rejim manual-dır.
    """
    entries = (
        PayrollEntry.query.join(PayrollRun)
        .filter(PayrollEntry.employee_id == employee.id)
        .order_by(PayrollRun.created_at.desc())
        .limit(12)
        .all()
    )
    if entries:
        avg_gross = sum(float(e.gross_total or 0) for e in entries) / len(entries)
    else:
        avg_gross = monthly_salary

    daily_rate = avg_gross / 30.4 if avg_gross else 0.0
    ov_start = max(leave_request.start_date, period_start)
    ov_end = min(leave_request.end_date, period_end)
    days = max((ov_end - ov_start).days + 1, 0)
    return round(daily_rate * days, 2)


def _monthly_payments_for(employee_id, year, month, is_annual=None, is_sick=None):
    """Bu (year, month) üçün AYRICA daxil edilmiş məzuniyyət/xəstəlik
    ödənişlərini qaytarır (bax: LeaveRequestMonthlyPayment,
    leave_request_form.html-dəki "hər ay üçün ödəniş" sahələri). Ay
    sərhədini keçən (məs. 20.07 — 02.08) bir iş buraxması üçün BU
    funksiya YALNIZ sorğulanan aya aid məbləği qaytarır — digər ayın
    məbləği bu ayın hesablamasına HEÇ QARIŞMIR (hər ayın öz PayrollEntry-i
    yalnız özünə aid hissəni görür)."""
    q = (
        LeaveRequestMonthlyPayment.query
        .join(LeaveRequest, LeaveRequestMonthlyPayment.leave_request_id == LeaveRequest.id)
        .join(LeaveReason, LeaveRequest.leave_reason_id == LeaveReason.id)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequestMonthlyPayment.year == year,
            LeaveRequestMonthlyPayment.month == month,
        )
    )
    if is_annual is not None:
        q = q.filter(LeaveReason.is_annual_leave == is_annual)
    if is_sick is not None:
        q = q.filter(LeaveReason.is_sick_leave == is_sick)
    return q.all()


def _vacation_and_sick_pay(employee, period_start, period_end, monthly_salary, settings):
    target_year, target_month = period_start.year, period_start.month

    vacation_total = 0.0
    if settings.vacation_pay_mode == "auto":
        # Avtomatik rejim AYRI-AY bölgüsü tələb etmir — hər dövr üçün öz
        # düsturu ilə (orta gündəlik qazanc x bu dövrə düşən gün sayı)
        # birbaşa hesablanır, ona görə hələ də köhnə (tarix aralığı
        # üst-üstə düşməsinə əsaslanan) yoxlamadan istifadə edir.
        for lr in _leave_requests_overlapping(employee.id, period_start, period_end, is_annual=True):
            vacation_total += _auto_vacation_pay(
                employee, lr, period_start, period_end, monthly_salary
            )
    else:
        vacation_total = sum(
            float(p.amount or 0)
            for p in _monthly_payments_for(employee.id, target_year, target_month, is_annual=True)
        )

    # `sick_episodes`: HƏR bir xəstəlik ödənişinin (bu AYA aid hissəsi) öz
    # məbləği AYRI-AYRI saxlanılır (cəm YOX) — çünki gəlir vergisi
    # baxımından hər biri MÜSTƏQİL şəkildə vergiyə cəlb olunur (bax:
    # calculate_gross_to_net-dəki `sick_pay_episodes` izahı). Ay sərhədini
    # keçən bir xəstəlik vərəqəsi üçün BU ayın məbləği ilə DİGƏR ayın
    # məbləği ayrı-ayrı LeaveRequestMonthlyPayment sətirləridir — hər biri
    # YALNIZ öz ayının PayrollEntry-də görünür.
    sick_episodes = [
        round(float(p.amount or 0), 2)
        for p in _monthly_payments_for(employee.id, target_year, target_month, is_sick=True)
    ]

    sick_total = round(sum(sick_episodes), 2)
    return round(vacation_total, 2), sick_total, sick_episodes


# ---------------------------------------------------------------------------
# Əlavələr (SalaryAddition)
# ---------------------------------------------------------------------------


def validate_addition_dates(valid_from, valid_to):
    """Əlavə/tutulma tarix aralığı üçün validasiya: `valid_from` ayın 1-i
    olmalıdır; `valid_to` (verilibsə) öz ayının SON günü olmalıdır — heç
    biri ayın ortasından başlaya/bitə bilməz (əməkhaqqı dövrləri tam ay
    olduğu üçün). `valid_to=None` — müddətsiz (cari dövrədək) qüvvədədir.
    Xəta varsa mətn, yoxdursa None qaytarır."""
    import calendar as _calendar

    if valid_from and valid_from.day != 1:
        return "Qüvvəyə minmə tarixi ayın 1-i olmalıdır."
    if valid_to:
        last_day = _calendar.monthrange(valid_to.year, valid_to.month)[1]
        if valid_to.day != last_day:
            return "Qüvvədən düşmə tarixi öz ayının son günü olmalıdır."
    if valid_to and valid_from and valid_to < valid_from:
        return "Qüvvədən düşmə tarixi qüvvəyə minmə tarixindən əvvəl ola bilməz."
    return None


def applicable_additions(employee_id, period_start, period_end):
    """Bu əməkdaşa və bu dövrə tətbiq olunan bütün aktiv SalaryAddition
    sətirləri (həm 'all', həm də bu əməkdaşı əhatə edən 'individual')."""
    candidates = SalaryAddition.query.filter(SalaryAddition.is_active.is_(True)).all()
    result = []
    for a in candidates:
        if not a.overlaps_period(period_start, period_end):
            continue
        if a.scope == "all":
            result.append(a)
        else:
            if any(e.id == employee_id for e in a.employees):
                result.append(a)
    return result

# ---------------------------------------------------------------------------
# Tabel-dən iş günü norması / faktiki işlənmiş gün
# ---------------------------------------------------------------------------


def _calendar_norm_days(period_start, period_end):
    """Ayın TƏQVİM üzrə iş günü norması — həftə sonu və bayram/matəm
    günləri çıxılmaqla ayın ÜMUMİ gün sayı. Bu, KONKRET əməkdaşın həmin
    ay aktiv olduğu günlərdən ASILI DEYİL (məs. əməkdaş ayın 3-də işdən
    çıxsa belə, norma bütün ay üçün nə qədərdirsə odur — tabel_service.py
    ilə eyni "həftə sonu/bayram" tərifindən istifadə edir ki, tabeldəki
    xanalarla üst-üstə düşsün)."""
    days_in_month = (period_end - period_start).days + 1
    weekend_days = _weekend_days(period_start, period_end)
    holiday_days = set(_holiday_marks(period_start, period_end).keys())
    non_work_days = weekend_days | holiday_days
    return days_in_month - len(non_work_days)


def _worked_days(tabel_row):
    """Əməkdaşın bu dövrdə faktiki İŞLƏDİYİ ('+') gün sayı (bax:
    _calendar_norm_days — norma ilə qarışdırılmasın)."""
    marks = (tabel_row.day_marks or {}) if tabel_row else {}
    return sum(1 for v in marks.values() if v == "+")


# ---------------------------------------------------------------------------
# Bir əməkdaş üçün tam hesablama
# ---------------------------------------------------------------------------


def recalculate_entry(entry):
    """`entry` (PayrollEntry, employee/payroll_run əlaqələri yüklənmiş)
    üzərində bütün hesablanan sahələri yeniləyir. `vacation_pay`/`sick_pay`
    mənbəyi LeaveRequest olan TÖRƏMƏ sahələrdir (manual rejimdə belə —
    məbləğ əməkdaşın İcazələri pəncərəsindəki qeydə daxil edilir,
    PayrollEntry-ə deyil) — ona görə hər çağırışda yenidən mənbədən
    oxunub üzərinə yazılır. Mükafat/əlavə əməkhaqqı/tutulma (aliment və s.)
    da eynilə TÖRƏMƏdir — "Əməkhaqqı əlavələri" pəncərəsindəki
    (SalaryAddition) sətirlərdən yenidən hesablanır.
    """
    settings = PayrollSettings.get()
    period = entry.payroll_run.period
    period_start, period_end, _ = month_bounds(period.year, period.month)
    employee = entry.employee

    tabel_row = TabelEmployeeRow.query.filter_by(
        period_id=period.id, employee_id=employee.id
    ).first()
    norm_days = _calendar_norm_days(period_start, period_end)
    worked_days = _worked_days(tabel_row)

    monthly_salary = get_monthly_salary_at(employee, period_end)
    base_amount = (
        monthly_salary * (worked_days / norm_days) if norm_days else 0.0
    )

    vacation_pay, sick_pay, sick_episodes = _vacation_and_sick_pay(
        employee, period_start, period_end, monthly_salary, settings
    )

    additions_detail = []
    deductions_detail = []
    additions_total = 0.0
    deductions_total = 0.0
    for a in applicable_additions(employee.id, period_start, period_end):
        amt = round(a.amount_for(monthly_salary), 2)
        if a.is_deduction():
            deductions_detail.append({"name": a.type_name(), "amount": amt})
            deductions_total += amt
        else:
            additions_detail.append({"name": a.type_name(), "amount": amt})
            additions_total += amt

    entry.full_name_snapshot = employee.full_name
    entry.position_snapshot = employee.position
    entry.monthly_salary = round(monthly_salary, 2)
    entry.norm_days = norm_days
    entry.worked_days = worked_days
    entry.base_amount = round(base_amount, 2)

    entry.vacation_pay = vacation_pay
    entry.sick_pay = sick_pay

    entry.additions_total = round(additions_total, 2)
    entry.additions_detail = additions_detail
    entry.deductions_total = round(deductions_total, 2)
    entry.deductions_detail = deductions_detail

    # GROSS: yalnız "əlavə" növləri daxildir. "Tutulma" növləri (aliment
    # və s.) VERGİYƏ CƏLB OLUNAN gross-u azaltmır — real həyatda bu cür
    # tutulmalar əməkdaşın artıq vergi/DSMF ödənmiş NET məbləğindən
    # (icra sənədi, məhkəmə qərarı və s. əsasında) çıxılır, ona görə
    # aşağıda net-dən çıxılır, gross-dan yox.
    gross_total = (
        float(entry.base_amount or 0)
        + float(entry.vacation_pay or 0)
        + float(entry.sick_pay or 0)
        + float(entry.additions_total or 0)
    )
    entry.gross_total = round(gross_total, 2)

    # `as_of_date=period_end`: bu dövr üçün YENİDƏN hesablama aparılanda
    # (məs. il sonra bir tabel düzəldilib təsdiqlənəndə) O DÖVRDƏ qüvvədə
    # olmuş vergi formulaları işləsin, BU GÜNKÜ (sonradan dəyişmiş)
    # formulalar YOX — bax: PayrollTaxFormula.get_script_for_date.
    result = calculate_gross_to_net(gross_total, as_of_date=period_end, sick_pay_episodes=sick_episodes)
    entry.income_tax = result["income_tax"]
    entry.dsmf_amount = result["dsmf"]
    entry.unemployment_amount = result["unemployment"]
    entry.medical_amount = result["medical"]
    entry.net_total = round(result["net"] - float(entry.deductions_total or 0), 2)

    entry.employer_dsmf = result["employer_dsmf"]
    entry.employer_unemployment = result["employer_unemployment"]
    entry.employer_medical = result["employer_medical"]
    entry.employer_cost_total = result["employer_cost_total"]
    return entry


def generate_or_refresh_payroll(period):
    """Bir TƏSDİQ OLUNMUŞ Tabel dövrü üçün PayrollRun-u yaradır (yoxdursa)
    və bütün əməkdaşlar üçün PayrollEntry sətirlərini hesablayır/yeniləyir.
    Bütün sahələr (o cümlədən mükafat/əlavə/tutulma) mənbələrindən
    (SalaryAddition, LeaveRequest, Bildirişlər) yenidən oxunur — manual
    "sahə" YOXDUR, hər şey "Əməkhaqqı əlavələri" pəncərəsindən idarə olunur.
    Commit etmir — çağıran tərəf commit edir."""
    if not period.is_approved:
        raise ValueError("Əməkhaqqı yalnız TƏSDİQ OLUNMUŞ dövr üçün hesablana bilər.")

    settings = PayrollSettings.get()

    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if not run:
        run = PayrollRun(period_id=period.id, calc_method=settings.calc_method)
        db.session.add(run)
        db.session.flush()

    existing = {e.employee_id: e for e in run.entries}
    rows = (
        TabelEmployeeRow.query.filter_by(period_id=period.id)
        .order_by(TabelEmployeeRow.row_no)
        .all()
    )

    row_no = 0
    for row in rows:
        row_no += 1
        entry = existing.get(row.employee_id)
        if entry is None:
            entry = PayrollEntry(
                payroll_run_id=run.id,
                employee_id=row.employee_id,
            )
            db.session.add(entry)
        entry.row_no = row_no
        entry.payroll_run = run
        entry.employee = row.employee
        recalculate_entry(entry)

    return run
