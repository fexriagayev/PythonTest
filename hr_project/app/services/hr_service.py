"""
Business logic that keeps Employee.department / position / hire_date /
termination_date / is_active / total_experience / company_experience /
other_experience in sync with the employee's "İş yerləri" (əmək kitabçası)
records (EmploymentRecord). These Employee fields are no longer edited
directly on the employee form — they are always derived here.

Call `recompute_employee_from_history(employee)` after any
create/update/delete of an EmploymentRecord belonging to that employee, then
commit the session.
"""

from datetime import date, timedelta
from app.models import EmploymentRecord, EmploymentContractNotification


def _format_experience(total_days):
    """Rough 'X il Y ay' formatting (approximate, not calendar-precise)."""
    if total_days <= 0:
        return "0 il 0 ay"
    years = total_days // 365
    remaining_days = total_days % 365
    months = remaining_days // 30
    return f"{years} il {months} ay"


def _record_days(record, employee_is_active, employee_termination_date):
    """Number of days a single employment record covers (open-ended
    current-company records count up to today, or up to the employee's
    computed termination date if that record itself isn't the terminating
    one but the employee has since left)."""
    if not record.date_from:
        return 0

    end = record.date_to
    if end is None:
        if (
            record.is_current_company
            and not employee_is_active
            and employee_termination_date
        ):
            end = employee_termination_date
        else:
            end = date.today()

    delta = (end - record.date_from).days
    return max(delta, 0)


def get_last_current_company_record(employee_id, exclude_id=None):
    """Returns the most recent (by date_from) CURRENT-COMPANY EmploymentRecord
    for this employee, or None if there isn't one yet. Used both to validate
    the allowed "Hərəkət növü" for a new/edited record (see
    _validate_work_history_form) and to auto-fill the struktur/vəzifə shown
    for a "İşdən çıxma" record (which has no struktur/vəzifə of its own)."""
    query = EmploymentRecord.query.filter_by(
        employee_id=employee_id, is_current_company=True
    )
    if exclude_id is not None:
        query = query.filter(EmploymentRecord.id != exclude_id)
    return query.order_by(
        EmploymentRecord.date_from.desc(), EmploymentRecord.id.desc()
    ).first()


def recompute_work_history_dates(employee_id):
    """
    Recomputes (but does not commit) `date_to` for EVERY EmploymentRecord of
    this employee — cari şirkət and kənar iş yeri together, in one single
    chronological timeline ordered by `date_from`. `date_to` is never entered
    by hand any more; it is always derived from what comes next:

      - A "İşdən çıxma" record is a point-in-time event: its own date_to is
        always its own date_from, regardless of what follows (this is what
        allows a later "İşə qəbul" to start after a gap, instead of being
        forced to begin the very next day).
      - Any other record (hire, transfer, kənar iş yeri) ends the day before
        the NEXT record (by date_from) starts — i.e. it automatically
        "closes" as soon as the next one begins.
      - The last record overall, if it isn't itself a termination, is left
        open-ended (date_to = None -> hazırda davam edir).

    Because every date_to is derived this way, two records can never overlap
    — the old "paralel iş qadağandır" overlap check (app/utils/date_overlap.py)
    is no longer needed for EmploymentRecord.

    Call this after any add/edit/delete of an EmploymentRecord (after
    flushing the change), then call recompute_employee_from_history and
    commit.
    """
    records = (
        EmploymentRecord.query.filter_by(employee_id=employee_id)
        .order_by(EmploymentRecord.date_from.asc(), EmploymentRecord.id.asc())
        .all()
    )

    for i, record in enumerate(records):
        if record.is_current_company and record.movement_type == "termination":
            record.date_to = record.date_from
        elif i + 1 < len(records):
            record.date_to = records[i + 1].date_from - timedelta(days=1)
        else:
            record.date_to = None


def recompute_employee_from_history(employee):
    """Recomputes and assigns (but does not commit) the derived fields on
    `employee` based on its EmploymentRecord rows."""

    all_records = (
        EmploymentRecord.query.filter_by(employee_id=employee.id)
        .order_by(EmploymentRecord.date_from.asc())
        .all()
    )

    current_records = [r for r in all_records if r.is_current_company]

    if current_records:
        # Şirkətə qəbul olduğu ilk tarix = ən erkən "cari şirkət" qeydinin tarixi
        employee.hire_date = current_records[0].date_from

        latest = current_records[-1]

        # Əməkdaş passivdir, əgər:
        #   (a) son qeydin "Hərəkət növü" sahəsi açıq şəkildə "İşdən çıxma"
        #       seçilibsə (istifadəçinin bilərəkdən verdiyi siqnal), VƏ YA
        #   (b) son qeydin bitmə tarixi keçmişdədirsə (başlama/bitmə tarixi
        #       daxil edilib və bu tarix artıq ötübsə, iş yerinin fəaliyyəti
        #       artıq bitmiş deməkdir — "Hərəkət növü" nü açıq şəkildə
        #       "İşdən çıxma"ya dəyişmək tələb olunmur).
        # Əks halda (bitmə tarixi boşdur = davam edir, YA DA gələcəkdədir)
        # əməkdaş aktivdir.
        ended_by_movement_type = latest.movement_type == "termination"
        ended_by_past_date_to = (
            latest.date_to is not None and latest.date_to < date.today()
        )

        if ended_by_movement_type or ended_by_past_date_to:
            employee.is_active = False
            employee.termination_date = latest.date_to or latest.date_from
        else:
            employee.is_active = True
            employee.termination_date = None

        # Cari struktur/vəzifə həmişə son "cari şirkət" qeydindən götürülür
        # ("Struktur"/"Vəzifə" bu qeyd üçün mütləqdir — bax:
        # _validate_work_history_form — ona görə "əvvəlki qeyd"ə ehtiyac yoxdur,
        # istər aktiv, istər passiv olsun, son qeyd özü etibarlıdır).
        employee.department = latest.department.name if latest.department else None
        employee.position = latest.position.name if latest.position else None
    else:
        employee.hire_date = None
        employee.termination_date = None
        employee.department = None
        employee.position = None
        # is_active left as-is when there's no employment history yet

    # --- Staj hesablamaları (bütün qeydlər üzrə) ----------------------------
    company_days = sum(
        _record_days(r, employee.is_active, employee.termination_date)
        for r in all_records
        if r.is_current_company
    )
    other_days = sum(
        _record_days(r, employee.is_active, employee.termination_date)
        for r in all_records
        if not r.is_current_company
    )

    employee.company_experience = _format_experience(company_days)
    employee.other_experience = _format_experience(other_days)
    employee.total_experience = _format_experience(company_days + other_days)


def recompute_employee_contract_from_bildiris(employee):
    """
    Müqavilənin başlama/bitmə tarixi and Maaş on the employee's main card
    are always read from the MOST RECENT Bildiriş record (by start_date,
    falling back to created_at for same-day entries) — never edited
    directly. Call this after any Bildiriş add/edit/delete, then commit.
    """
    latest = (
        EmploymentContractNotification.query.filter_by(employee_id=employee.id)
        .order_by(
            EmploymentContractNotification.start_date.desc(),
            EmploymentContractNotification.created_at.desc(),
        )
        .first()
    )
    if latest:
        employee.contract_start_date = latest.contract_start_date
        employee.contract_end_date = latest.contract_end_date
        employee.salary = latest.salary
    else:
        employee.contract_start_date = None
        employee.contract_end_date = None
        employee.salary = None
