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
_leave_payment_lines): xəstəlik pulundan YALNIZ gəlir vergisi tutulur —
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
    PayrollPayment,
    PayrollTaxFormula,
    TabelEmployeeRow,
    BriqadaWorkPeriod,
    BriqadaWorkEntry,
    Briqada,
    Employee,
    TabelPeriod,
)
from app.services.tabel_service import month_bounds, _weekend_days, _holiday_marks
from app.services.formula_engine import evaluate_formula, FormulaError

# ---------------------------------------------------------------------------
# Vergi/tutulma formulaları — bax modul-səviyyəli qeyd yuxarıda
# ---------------------------------------------------------------------------


def _run_tax_formula(code, variables, as_of_date):
    """`code` üçün `as_of_date`-də (adətən hesablanan dövrün son günü)
    QÜVVƏDƏ olan skripti tapıb verilmiş dəyişənlərlə (bax:
    formula_engine.evaluate_formula — `variables` dict, HƏMİŞƏ ən azı
    `gross` və `sick` ehtiva edir) icra edir — bax:
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
        return evaluate_formula(script, variables)
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


def _leave_label(leave_request):
    reason = leave_request.leave_reason.name if leave_request.leave_reason else "İş buraxması"
    return (
        f"{reason} ({leave_request.start_date.strftime('%d.%m.%Y')}"
        f"–{leave_request.end_date.strftime('%d.%m.%Y')})"
    )


def _leave_payment_date(leave_request, period_start):
    """Məzuniyyət/xəstəlik pulunun ödəniş tarixi = iş buraxmasının başlama
    günü (məs. 03.09-da məzuniyyətə çıxırsa, pul 03.09-da ödənilir). İş
    buraxması əvvəlki aydan başlayıbsa (ay sərhədini keçirsə), bu ayın
    hissəsi ayın 1-i ödənilir."""
    return max(leave_request.start_date, period_start)


def _leave_payment_lines(employee, period_start, period_end, monthly_salary, settings):
    """Bu dövrdə əməkdaşa ödəniləcək BÜTÜN məzuniyyət və xəstəlik
    ödənişlərini AYRI-AYRI sətirlər kimi qaytarır (cəm YOX): hər biri
    öz məbləği, tarixi və mənbəyi ilə. Bir ayda bir neçə məzuniyyət/xəstəlik
    ola bilər — hər biri ayrıca ödənişdir (bax: PayrollPayment).

    Qaytarır: `(vacation_lines, sick_lines)`; hər sətir dict:
    {kind, label, pay_date, amount, source_type, source_id}.

    Xəstəlik pulu: hər ödənişin (bu AYA aid hissəsinin) öz məbləği ayrıca
    qalır — gəlir vergisi baxımından hər biri MÜSTƏQİL vergiyə cəlb olunur
    (bax: allocate_payments). Ay sərhədini keçən bir iş buraxması üçün BU
    ayın məbləği ilə DİGƏR ayın məbləği ayrı-ayrı LeaveRequestMonthlyPayment
    sətirləridir — hər biri YALNIZ öz ayının hesablamasında görünür."""
    target_year, target_month = period_start.year, period_start.month

    vacation_lines = []
    if settings.vacation_pay_mode == "auto":
        # Avtomatik rejim AYRI-AY bölgüsü tələb etmir — hər dövr üçün öz
        # düsturu ilə (orta gündəlik qazanc x bu dövrə düşən gün sayı)
        # birbaşa hesablanır, ona görə hələ də köhnə (tarix aralığı
        # üst-üstə düşməsinə əsaslanan) yoxlamadan istifadə edir.
        for lr in _leave_requests_overlapping(employee.id, period_start, period_end, is_annual=True):
            vacation_lines.append({
                "kind": PayrollPayment.KIND_VACATION,
                "label": _leave_label(lr),
                "pay_date": _leave_payment_date(lr, period_start),
                "amount": _auto_vacation_pay(employee, lr, period_start, period_end, monthly_salary),
                "source_type": "leave_request",
                "source_id": lr.id,
            })
    else:
        for p in _monthly_payments_for(employee.id, target_year, target_month, is_annual=True):
            lr = p.leave_request
            vacation_lines.append({
                "kind": PayrollPayment.KIND_VACATION,
                "label": _leave_label(lr),
                "pay_date": _leave_payment_date(lr, period_start),
                "amount": float(p.amount or 0),
                "source_type": "leave_payment",
                "source_id": p.id,
            })

    sick_lines = []
    for p in _monthly_payments_for(employee.id, target_year, target_month, is_sick=True):
        lr = p.leave_request
        sick_lines.append({
            "kind": PayrollPayment.KIND_SICK,
            "label": _leave_label(lr),
            "pay_date": _leave_payment_date(lr, period_start),
            "amount": round(float(p.amount or 0), 2),
            "source_type": "leave_payment",
            "source_id": p.id,
        })
    return vacation_lines, sick_lines


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
# Obyektlər üzrə görülən işlər — TƏSDİQLƏNMİŞ NET məbləğlər (avans / yekun)
# ---------------------------------------------------------------------------

# Avans ayın bu günündə (bax: BriqadaWorkPeriod — "adətən ayın 15-i"),
# yekun maaş isə ayın SON günündə ödənilir.
WORK_AVANS_DAY = 15
_WORK_KIND_BY_RUN_TYPE = {
    "avans": PayrollPayment.KIND_WORK_AVANS,
    "yekun": PayrollPayment.KIND_WORK_FINAL,
}


def object_work_net_amounts(year, month):
    """`{employee_id: {"avans": (net, period_id), "yekun": (net, period_id)}}`
    — bu ayın TƏSDİQLƏNMİŞ (is_approved) "Obyektlər üzrə görülən işlər"
    dövrlərindəki məbləğlərin, hər əməkdaş üzrə bütün obyektlər cəmi. Bu
    məbləğlər NET-dir (əməkdaşın əlinə keçəcək). Təsdiqlənməmiş dövr nəzərə
    alınmır.

    Komanda üzvü sətri (Briqada.id) sistemdəki əməkdaşa bağlıdırsa
    (`member_id`), məbləğ O əməkdaşa yazılır; sərbəst mətnlə yazılmış
    (sistemdə əməkdaşı olmayan) üzvlər əməkhaqqı siyahısında olmadığı üçün
    burada YOXDUR — bax: object_work_unallocated."""
    periods = BriqadaWorkPeriod.query.filter_by(
        year=year, month=month, is_approved=True
    ).all()
    member_to_employee = {
        b.id: b.member_id for b in Briqada.query.filter(Briqada.member_id.isnot(None)).all()
    }
    result = {}
    for period in periods:
        if period.run_type not in _WORK_KIND_BY_RUN_TYPE:
            continue
        for e in BriqadaWorkEntry.query.filter_by(period_id=period.id).all():
            emp_id = e.employee_id if e.employee_id is not None else member_to_employee.get(e.briqada_id)
            if emp_id is None:
                continue
            amt = float(e.amount or 0)
            if amt <= 0:
                continue
            slot = result.setdefault(emp_id, {})
            prev_amt = slot.get(period.run_type, (0.0, period.id))[0]
            slot[period.run_type] = (round(prev_amt + amt, 2), period.id)
    return result


def object_work_unallocated(year, month, payroll_employee_ids):
    """Təsdiqlənmiş obyekt işi məbləği olub, amma əməkhaqqıya DÜŞMƏYƏN
    sətirlər: (a) sistemdə əməkdaşı olmayan (sərbəst adlı) briqada üzvləri,
    (b) bu ayın tabelində/əməkhaqqı siyahısında olmayan əməkdaşlar. Qaytarır:
    `[(ad, run_type, məbləğ), ...]` — istifadəçiyə xəbərdarlıq üçün."""
    periods = BriqadaWorkPeriod.query.filter_by(
        year=year, month=month, is_approved=True
    ).all()
    briqada_by_id = {b.id: b for b in Briqada.query.all()}
    payroll_employee_ids = set(payroll_employee_ids)
    totals = {}
    for period in periods:
        for e in BriqadaWorkEntry.query.filter_by(period_id=period.id).all():
            amt = float(e.amount or 0)
            if amt <= 0:
                continue
            name, emp_id = None, e.employee_id
            if emp_id is None and e.briqada_id is not None:
                b = briqada_by_id.get(e.briqada_id)
                emp_id = b.member_id if b else None
                name = b.member_name if b and emp_id is None else None
            if emp_id is not None and emp_id in payroll_employee_ids:
                continue
            if emp_id is not None:
                emp = db.session.get(Employee, emp_id)
                name = emp.full_name if emp else f"#{emp_id}"
            key = (name or "?", period.run_type)
            totals[key] = round(totals.get(key, 0.0) + amt, 2)
    return [(n, rt, a) for (n, rt), a in sorted(totals.items())]


def _work_payment_lines(employee_id, period_start, period_end, work_amounts):
    """Bu əməkdaşın bu ayki obyekt işi ödənişləri — NET hədəfli sətirlər
    (bax: allocate_payments `net_target`)."""
    import calendar as _calendar
    lines = []
    slots = work_amounts.get(employee_id) or {}
    avans_day = min(WORK_AVANS_DAY, _calendar.monthrange(period_start.year, period_start.month)[1])
    for run_type, (net, period_id) in slots.items():
        kind = _WORK_KIND_BY_RUN_TYPE[run_type]
        pay_date = period_start.replace(day=avans_day) if run_type == "avans" else period_end
        lines.append({
            "kind": kind,
            "label": "Obyekt işi — " + ("avans" if run_type == "avans" else "yekun maaş"),
            "pay_date": pay_date,
            "net_target": net,
            "source_type": "work_period",
            "source_id": period_id,
        })
    return lines


def refresh_unfinalized_payroll(year, month):
    """Bu ayın əməkhaqqısı artıq hesablanıb, amma hələ TƏSDİQLƏNMƏYİBSƏ
    yenidən hesablayır (məs. obyekt işi dövrü təsdiqlənəndə/ləğv olunanda).
    Təsdiqlənmiş əməkhaqqıya və təsdiqlənməmiş tabelə TOXUNMUR. Commit
    etmir. Hesablanıbsa True qaytarır."""
    period = TabelPeriod.query.filter_by(year=year, month=month).first()
    if not period or not period.is_approved:
        return False
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if not run or run.is_finalized:
        return False
    generate_or_refresh_payroll(period)
    return True


# ---------------------------------------------------------------------------
# Ödənişlər üzrə (tarixlə, növlə) AYRI hesablama
# ---------------------------------------------------------------------------

_EMPLOYEE_TAX_CODES = ("income_tax", "dsmf", "unemployment", "medical")
_EMPLOYER_TAX_CODES = ("employer_dsmf", "employer_unemployment", "employer_medical")

# Eyni tarixdə bir neçə ödəniş olarsa, kümülativ vergi bu sıra ilə bölünür
# (əsas əməkhaqqı ən SONA qalır — ay sonunda ödənilir).
_KIND_ORDER = {
    PayrollPayment.KIND_VACATION: 0,
    PayrollPayment.KIND_SICK: 1,
    PayrollPayment.KIND_ADDITION: 2,
    PayrollPayment.KIND_WORK_AVANS: 2,
    PayrollPayment.KIND_WORK_FINAL: 2,
    PayrollPayment.KIND_SALARY: 3,
}


def _tax_runner(as_of_date):
    """`code, variables -> float` — `as_of_date`-də qüvvədə olan skriptləri
    BİR DƏFƏ yükləyib (hər çağırışda DB-yə getməmək üçün) icra edir.
    Konfiqurasiya olunmayan kod üçün 0 (bax: _run_tax_formula)."""
    scripts = {}

    def run(code, variables):
        if code not in scripts:
            scripts[code] = PayrollTaxFormula.get_script_for_date(code, as_of_date)
        script = scripts[code]
        if script is None:
            return 0.0
        try:
            return evaluate_formula(script, variables)
        except FormulaError as e:
            raise FormulaError(f"'{code}' vergi formulası icra edilə bilmədi: {e}")

    return run


def allocate_payments(lines, as_of_date, deductions_total=0.0):
    """Ödəniş sətirlərinin (məzuniyyət, xəstəlik, əlavə/mükafat, obyekt işi,
    əsas maaş) HƏR BİRİ üçün gross, vergi/tutulmalar və NET hesablayır.

    Sətirlər `pay_date`-ə görə (eyni tarixdə: _KIND_ORDER) düzülür və vergilər
    KÜMÜLATİV bölünür: hər ödənişin vergisi = düsturun (bu ödənişə qədərki
    ÜMUMİ gross, ÜMUMİ xəstəlik pulu) üzərindən nəticəsi MİNUS əvvəlki ödənişə
    qədərki nəticəsi. Vergilər aylıq gross artdıqca dərəcəli (progressive)
    olduğu üçün bu, cəmin TAM AYIN gross-u üzərindən hesablanan vergiyə DƏQİQ
    bərabər olmasını (yuvarlaqlaşdırma daxil) təmin edir.

    NET → GROSS (obyekt işi): sətirdə `net_target` verilibsə (məs. \"avans\" /
    \"yekun\" — modulda NET kimi daxil edilir), `amount` (gross) əvvəlcədən
    məlum DEYİL: həmin ödənişə qədərki kümülativ vəziyyət nəzərə alınmaqla,
    gross-u elə tapırıq ki, GROSS → NET (yuxarıdakı eyni kümülativ qayda ilə)
    nəticəsi məhz `net_target`-ə bərabər çıxsın (bax: _solve_gross_for_net).
    Ödənişlər tarix sırası ilə həll olunur, ona görə sonrakı ödənişlərin
    (məs. ay sonu əsas maaşın) vergisi bu gross-u artıq nəzərə alır.

    Gəlir vergisi üçün xəstəlik pulunun XÜSUSİ rejimi saxlanılır (bax:
    calculate_gross_to_net): hər xəstəlik ödənişinin ÖZ məbləği üzərindən
    MÜSTƏQİL gəlir vergisi də həmin ödənişin vergisinə əlavə olunur.

    `deductions_total` (aliment və s.) əsas əməkhaqqı (kind=salary) sətrinin
    NET-indən çıxılır.

    `lines`: dict-lər (kind, label, pay_date, amount | net_target, ...) —
    DƏYİŞDİRİLMƏDƏN nüsxələnir. Qaytarır: hər biri əlavə olaraq gross_amount,
    income_tax, dsmf_amount, unemployment_amount, medical_amount,
    deductions_amount, net_amount, employer_* (və net_target olanlarda
    target_net) sahələri olan sıralanmış YENİ dict siyahısı. Məbləği 0 (və ya
    mənfi) olan sətirlər (əsas əməkhaqqı istisna, əgər tutulma varsa) atılır."""
    run = _tax_runner(as_of_date)
    deductions_total = round(float(deductions_total or 0), 2)

    ordered = []
    for ln in lines:
        target = ln.get("net_target")
        if target is not None:
            target = round(float(target or 0), 2)
            if target <= 0:
                continue
            ordered.append(dict(ln, net_target=target, amount=0.0))
            continue
        amt = max(float(ln.get("amount") or 0), 0.0)
        is_salary = ln["kind"] == PayrollPayment.KIND_SALARY
        if amt <= 0 and not (is_salary and deductions_total):
            continue
        ordered.append(dict(ln, amount=round(amt, 2)))
    ordered.sort(key=lambda x: (x["pay_date"], _KIND_ORDER.get(x["kind"], 9), x.get("source_id") or 0))

    all_codes = _EMPLOYEE_TAX_CODES + _EMPLOYER_TAX_CODES
    state = {
        "prev": {c: 0.0 for c in all_codes},
        "cum_gross": 0.0,
        "cum_sick": 0.0,
        "sick_tax_raw": 0.0,
    }

    def cum_taxes(cum_gross, codes):
        """`cum_gross`-a qədər KÜMÜLATİV (yuvarlaqlaşdırılmış) vergilər."""
        variables = {"gross": round(cum_gross, 2), "sick": round(state["cum_sick"], 2)}
        out = {}
        for code in codes:
            raw = run(code, variables) if cum_gross > 0 else 0.0
            if code == "income_tax":
                raw += state["sick_tax_raw"]
            out[code] = round(raw, 2)
        return out

    def net_if_gross(g):
        taxes = cum_taxes(state["cum_gross"] + g, _EMPLOYEE_TAX_CODES)
        withheld = sum(taxes[c] - state["prev"][c] for c in _EMPLOYEE_TAX_CODES)
        return round(g - withheld, 2)

    result = []
    for i, ln in enumerate(ordered, start=1):
        target = ln.get("net_target")
        if target is not None:
            amt = _solve_gross_for_net(target, net_if_gross)
        else:
            amt = ln["amount"]

        state["cum_gross"] += amt
        if ln["kind"] == PayrollPayment.KIND_SICK:
            state["cum_sick"] += amt
            # Bu xəstəlik ödənişinin ÖZ məbləği üzərindən müstəqil gəlir vergisi.
            state["sick_tax_raw"] += run("income_tax", {"gross": amt, "sick": 0.0})

        taxes = cum_taxes(state["cum_gross"], all_codes)
        row = dict(ln, sort_no=i, amount=amt)
        for code in all_codes:
            row[code] = round(taxes[code] - state["prev"][code], 2)
            state["prev"][code] = taxes[code]

        row["gross_amount"] = amt
        row["dsmf_amount"] = row.pop("dsmf")
        row["unemployment_amount"] = row.pop("unemployment")
        row["medical_amount"] = row.pop("medical")
        row["deductions_amount"] = 0.0
        if target is not None:
            row["target_net"] = target
        result.append(row)

    if deductions_total:
        salary_rows = [r for r in result if r["kind"] == PayrollPayment.KIND_SALARY]
        target_row = salary_rows[-1] if salary_rows else result[-1]
        target_row["deductions_amount"] = deductions_total

    for r in result:
        r["net_amount"] = round(
            r["gross_amount"] - r["income_tax"] - r["dsmf_amount"]
            - r["unemployment_amount"] - r["medical_amount"] - r["deductions_amount"],
            2,
        )
    return result


def _solve_gross_for_net(target_net, net_if_gross):
    """NET → GROSS: `net_if_gross(g)` (g → net, dərəcəli/kümülativ vergilərlə)
    funksiyasının `target_net`-ə bərabər olduğu ən KİÇİK gross-u (qəpik
    dəqiqliyi ilə) tapır. Əvvəlcə tam qəpiklər üzərində ikili axtarış (net
    gross-la artan funksiyadır), sonra yuvarlaqlaşdırmadan yaranan kiçik
    \"pilləkən\"lərə görə ətrafında ±10 qəpik yoxlanılır. Dəqiq bərabərlik
    mümkün olmasa (istifadəçi qeyri-adi/kəsilən bir formula yazıbsa) —
    hədəfə ƏN YAXIN net verən gross qaytarılır; fərq `target_net` ilə
    `net_amount` arasında görünür."""
    target_c = int(round(target_net * 100))
    lo = target_c  # gross >= net (tutulmalar mənfi deyil)
    hi = max(target_c * 2, target_c + 1000)
    guard = 0
    while net_if_gross(hi / 100.0) < target_net and guard < 40:
        hi *= 2
        guard += 1
    while lo < hi:
        mid = (lo + hi) // 2
        if net_if_gross(mid / 100.0) >= target_net:
            hi = mid
        else:
            lo = mid + 1
    best_c, best_diff = lo, abs(net_if_gross(lo / 100.0) - target_net)
    for c in range(max(lo - 10, target_c), lo + 11):
        diff = abs(net_if_gross(c / 100.0) - target_net)
        if diff < best_diff - 1e-9:
            best_c, best_diff = c, diff
    return round(best_c / 100.0, 2)


# ---------------------------------------------------------------------------
# Bir əməkdaş üçün tam hesablama
# ---------------------------------------------------------------------------


def recalculate_entry(entry, work_amounts=None):
    """`entry` (PayrollEntry, employee/payroll_run əlaqələri yüklənmiş)
    üzərində bütün hesablanan sahələri yeniləyir. `vacation_pay`/`sick_pay`
    mənbəyi LeaveRequest olan TÖRƏMƏ sahələrdir (manual rejimdə belə —
    məbləğ əməkdaşın İcazələri pəncərəsindəki qeydə daxil edilir,
    PayrollEntry-ə deyil) — ona görə hər çağırışda yenidən mənbədən
    oxunub üzərinə yazılır. Mükafat/əlavə əməkhaqqı/tutulma (aliment və s.)
    da eynilə TÖRƏMƏdir — "Əməkhaqqı əlavələri" pəncərəsindəki
    (SalaryAddition) sətirlərdən yenidən hesablanır.

    `work_amounts`: object_work_net_amounts(...) nəticəsi (toplu hesablamada
    hər əməkdaş üçün təkrar sorğu olmasın deyə); verilməsə özü oxuyur.

    Əməkdaşın yekun NET-i artıq tək rəqəm kimi yox, ödənişlərin (PayrollPayment:
    hər növ üzrə, öz tarixi ilə ayrıca NET) CƏMİ kimi tapılır — bax:
    allocate_payments.
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

    vacation_lines, sick_lines = _leave_payment_lines(
        employee, period_start, period_end, monthly_salary, settings
    )
    vacation_pay = round(sum(float(l["amount"] or 0) for l in vacation_lines), 2)
    sick_pay = round(sum(float(l["amount"] or 0) for l in sick_lines), 2)

    additions_detail = []
    deductions_detail = []
    additions_total = 0.0
    deductions_total = 0.0
    addition_lines = []
    for a in applicable_additions(employee.id, period_start, period_end):
        amt = round(a.amount_for(monthly_salary), 2)
        if a.is_deduction():
            deductions_detail.append({"name": a.type_name(), "amount": amt})
            deductions_total += amt
        else:
            # Ödəniş tarixi olan əlavə YALNIZ o tarixin ayında ödənilir
            # (başqa aya düşən tarix bu dövrə aid deyil).
            if a.pay_date and not (period_start <= a.pay_date <= period_end):
                continue
            additions_detail.append({"name": a.type_name(), "amount": amt})
            additions_total += amt
            addition_lines.append({
                "kind": PayrollPayment.KIND_ADDITION,
                "label": a.type_name() + (f" — {a.note}" if a.note else ""),
                "pay_date": a.pay_date or period_end,
                "amount": amt,
                "source_type": "addition",
                "source_id": a.id,
            })

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
    # NET-dən çıxılır (əsas əməkhaqqı ödənişinin NET-indən), gross-dan yox.
    # Obyekt işinin gross-u isə NET-dən tərs hesablanır (aşağıda) və
    # gross_total-a ondan SONRA əlavə olunur.
    if work_amounts is None:
        work_amounts = object_work_net_amounts(period.year, period.month)
    work_lines = _work_payment_lines(employee.id, period_start, period_end, work_amounts)

    # HƏR ÖDƏNİŞ AYRICA: əsas əməkhaqqı ayın SON günü, məzuniyyət/xəstəlik
    # iş buraxmasının başlama günü, mükafat/əlavə öz tarixində (tarixi
    # yoxdursa ayın son günü). Bax: allocate_payments.
    lines = [{
        "kind": PayrollPayment.KIND_SALARY,
        "label": "Əsas əməkhaqqı",
        "pay_date": period_end,
        "amount": float(entry.base_amount or 0),
        "source_type": None,
        "source_id": None,
    }] + vacation_lines + sick_lines + addition_lines + work_lines

    # `as_of_date=period_end`: bu dövr üçün YENİDƏN hesablama aparılanda
    # (məs. il sonra bir tabel düzəldilib təsdiqlənəndə) O DÖVRDƏ qüvvədə
    # olmuş vergi formulaları işləsin, BU GÜNKÜ (sonradan dəyişmiş)
    # formulalar YOX — bax: PayrollTaxFormula.get_script_for_date.
    allocated = allocate_payments(lines, period_end, deductions_total=entry.deductions_total)

    # Obyekt işinin tərs hesablanmış gross-u (net -> gross) + yekun gross.
    entry.work_gross = round(
        sum(r["gross_amount"] for r in allocated if r["kind"] in PayrollPayment.WORK_KINDS), 2
    )
    entry.gross_total = round(
        float(entry.base_amount or 0) + float(entry.vacation_pay or 0)
        + float(entry.sick_pay or 0) + float(entry.additions_total or 0)
        + float(entry.work_gross or 0),
        2,
    )

    entry.payments = [
        PayrollPayment(
            sort_no=r["sort_no"], kind=r["kind"], label=r["label"], pay_date=r["pay_date"],
            source_type=r["source_type"], source_id=r["source_id"],
            gross_amount=r["gross_amount"], income_tax=r["income_tax"],
            dsmf_amount=r["dsmf_amount"], unemployment_amount=r["unemployment_amount"],
            medical_amount=r["medical_amount"], deductions_amount=r["deductions_amount"],
            net_amount=r["net_amount"], target_net=r.get("target_net"),
            employer_dsmf=r["employer_dsmf"], employer_unemployment=r["employer_unemployment"],
            employer_medical=r["employer_medical"],
        )
        for r in allocated
    ]

    # Yekun (aylıq) rəqəmlər = ödənişlərin cəmi.
    def _sum(field):
        return round(sum(r[field] for r in allocated), 2)

    entry.income_tax = _sum("income_tax")
    entry.dsmf_amount = _sum("dsmf_amount")
    entry.unemployment_amount = _sum("unemployment_amount")
    entry.medical_amount = _sum("medical_amount")
    entry.net_total = _sum("net_amount")

    entry.employer_dsmf = _sum("employer_dsmf")
    entry.employer_unemployment = _sum("employer_unemployment")
    entry.employer_medical = _sum("employer_medical")
    entry.employer_cost_total = round(
        entry.gross_total + entry.employer_dsmf + entry.employer_unemployment + entry.employer_medical, 2
    )
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
    work_amounts = object_work_net_amounts(period.year, period.month)
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
        recalculate_entry(entry, work_amounts=work_amounts)

    return run
