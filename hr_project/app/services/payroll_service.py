"""
Əməkhaqqı (payroll) hesablama məntiqi.

Hazırkı mərhələdə YALNIZ "gross → net" istiqaməti dəstəklənir
(PayrollSettings.calc_method == "gross_to_net"). Hər əməkdaşın maaşı GROSS
(bruto) qəbul edilir və aşağıdakı 4 tutulma bu məbləğdən çıxılaraq NET
tapılır:

    Net = Gross - (Gəlir vergisi + DSMF + İşsizlikdən sığorta + İTS)

Dərəcələr 2026-cı il üçün Azərbaycan qanunvericiliyinə uyğundur (mənbə:
Vergi Məcəlləsi 101-ci maddə, "Sosial sığorta haqqında" və "Tibbi sığorta
haqqında" qanunlar — bax TAX_TABLES aşağıda). Qanunvericilik hər il dəyişə
bildiyi üçün bu ədədlər BURADA, tək yerdə saxlanılır ki, növbəti il üçün
yenilənməsi asan olsun.

"net → gross → net" istiqaməti (PayrollSettings.calc_method ==
"net_to_gross") HƏLƏLİK İMPLEMENTASİYA OLUNMAYIB — istifadəçi ilə
razılaşdırıldığı kimi, əvvəlcə gross→net üzərində dayanılıb.
"""

from app import db
from app.models import (
    EmploymentContractNotification,
    LeaveRequest,
    LeaveReason,
    SalaryAddition,
    PayrollSettings,
    PayrollRun,
    PayrollEntry,
    TabelEmployeeRow,
)
from app.services.tabel_service import month_bounds

# ---------------------------------------------------------------------------
# Vergi/tutulma cədvəlləri (2026)
# ---------------------------------------------------------------------------


def _income_tax_private_non_oil(gross):
    """Neft-qaz sahəsində fəaliyyəti olmayan və qeyri-dövlət sektoru (2026)."""
    if gross <= 200:
        return 0.0
    if gross <= 2500:
        return (gross - 200) * 0.03
    if gross <= 8000:
        return 75 + (gross - 2500) * 0.10
    return 625 + (gross - 8000) * 0.14


def _income_tax_state_oil_gas(gross):
    """Neft-qaz sahəsi / dövlət sektoru — güzəştsiz, Vergi Məcəlləsi 101.1."""
    if gross <= 2500:
        return gross * 0.14
    return 350 + (gross - 2500) * 0.25


def _dsmf(gross):
    """Məcburi dövlət sosial sığorta haqqı — işçi payı (hər iki sektor
    üçün eynidir; dəyişməyib)."""
    if gross <= 200:
        return gross * 0.03
    return 6 + (gross - 200) * 0.10


def _unemployment(gross):
    """İşsizlikdən sığorta haqqı — 0.5% (dəyişməyib)."""
    return gross * 0.005


def _medical(gross):
    """İcbari tibbi sığorta haqqı — 2500 manatadək 2%, yuxarısı 0.5%."""
    if gross <= 2500:
        return gross * 0.02
    return 50 + (gross - 2500) * 0.005


TAX_TABLES = {
    "private_non_oil": _income_tax_private_non_oil,
    "state_oil_gas": _income_tax_state_oil_gas,
}


def calculate_gross_to_net(gross, sector="private_non_oil"):
    """Verilmiş GROSS məbləğdən 4 tutulmanı və NET nəticəni hesablayır.
    Mənfi əməkhaqqı (və ya 0) üçün hamısı 0 qaytarılır."""
    gross = max(float(gross or 0), 0.0)
    if gross == 0:
        return {
            "income_tax": 0.0, "dsmf": 0.0, "unemployment": 0.0,
            "medical": 0.0, "net": 0.0,
        }

    income_tax_fn = TAX_TABLES.get(sector, _income_tax_private_non_oil)
    income_tax = round(income_tax_fn(gross), 2)
    dsmf = round(_dsmf(gross), 2)
    unemployment = round(_unemployment(gross), 2)
    medical = round(_medical(gross), 2)
    net = round(gross - income_tax - dsmf - unemployment - medical, 2)
    return {
        "income_tax": income_tax, "dsmf": dsmf, "unemployment": unemployment,
        "medical": medical, "net": net,
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


def _vacation_and_sick_pay(employee, period_start, period_end, monthly_salary, settings):
    vacation_total = 0.0
    for lr in _leave_requests_overlapping(employee.id, period_start, period_end, is_annual=True):
        if settings.vacation_pay_mode == "auto":
            vacation_total += _auto_vacation_pay(
                employee, lr, period_start, period_end, monthly_salary
            )
        else:
            vacation_total += float(lr.payment_amount or 0)

    sick_total = 0.0
    for lr in _leave_requests_overlapping(employee.id, period_start, period_end, is_sick=True):
        # Xəstəlik pulu hazırda yalnız manual rejimdə dəstəklənir (bax modul qeydi).
        sick_total += float(lr.payment_amount or 0)

    return round(vacation_total, 2), round(sick_total, 2)


# ---------------------------------------------------------------------------
# Əlavələr (SalaryAddition)
# ---------------------------------------------------------------------------


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


def _work_day_counts(tabel_row):
    """(norm_days, worked_days) — norm: adi iş günü xanalarının sayı
    ('+'/'-' — həftə sonu/bayram/icazə xaric), worked: '+' işarəli
    (faktiki işlənmiş) günlərin sayı."""
    marks = (tabel_row.day_marks or {}) if tabel_row else {}
    norm = sum(1 for v in marks.values() if v in ("+", "-"))
    worked = sum(1 for v in marks.values() if v == "+")
    return norm, worked


# ---------------------------------------------------------------------------
# Bir əməkdaş üçün tam hesablama
# ---------------------------------------------------------------------------


def recalculate_entry(entry):
    """`entry` (PayrollEntry, employee/payroll_run əlaqələri yüklənmiş)
    üzərində bütün hesablanan sahələri yeniləyir. `extra_amount` və
    `bonus` bu funksiyaya TOXUNULMUR — onlar həqiqətən manual sahələrdir,
    birbaşa PayrollEntry üzərində istifadəçi tərəfindən daxil edilir (bax
    routes.py). `vacation_pay`/`sick_pay` isə mənbəyi LeaveRequest olan
    TÖRƏMƏ sahələrdir (manual rejimdə belə — məbləğ əməkdaşın İcazələri
    pəncərəsindəki qeydə daxil edilir, PayrollEntry-ə deyil) — ona görə
    hər çağırışda yenidən mənbədən oxunub üzərinə yazılır.
    """
    settings = PayrollSettings.get()
    period = entry.payroll_run.period
    period_start, period_end, _ = month_bounds(period.year, period.month)
    employee = entry.employee

    tabel_row = TabelEmployeeRow.query.filter_by(
        period_id=period.id, employee_id=employee.id
    ).first()
    norm_days, worked_days = _work_day_counts(tabel_row)

    monthly_salary = get_monthly_salary_at(employee, period_end)
    base_amount = (
        monthly_salary * (worked_days / norm_days) if norm_days else 0.0
    )

    vacation_pay, sick_pay = _vacation_and_sick_pay(
        employee, period_start, period_end, monthly_salary, settings
    )

    additions = applicable_additions(employee.id, period_start, period_end)
    additions_detail = []
    additions_total = 0.0
    for a in additions:
        amt = round(a.amount_for(monthly_salary), 2)
        additions_detail.append({"name": a.name, "amount": amt})
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

    gross_total = (
        float(entry.base_amount or 0)
        + float(entry.extra_amount or 0)
        + float(entry.vacation_pay or 0)
        + float(entry.sick_pay or 0)
        + float(entry.bonus or 0)
        + float(entry.additions_total or 0)
    )
    entry.gross_total = round(gross_total, 2)

    result = calculate_gross_to_net(gross_total, sector=settings.sector)
    entry.income_tax = result["income_tax"]
    entry.dsmf_amount = result["dsmf"]
    entry.unemployment_amount = result["unemployment"]
    entry.medical_amount = result["medical"]
    entry.net_total = result["net"]
    return entry


def generate_or_refresh_payroll(period):
    """Bir TƏSDİQ OLUNMUŞ Tabel dövrü üçün PayrollRun-u yaradır (yoxdursa)
    və bütün əməkdaşlar üçün PayrollEntry sətirlərini hesablayır/yeniləyir.
    Mövcud sətirlərin manual sahələri (extra_amount, bonus) TOXUNULMUR.
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
                extra_amount=0,
                bonus=0,
            )
            db.session.add(entry)
        entry.row_no = row_no
        entry.payroll_run = run
        entry.employee = row.employee
        recalculate_entry(entry)

    return run
