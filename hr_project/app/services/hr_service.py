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


def _record_days(record, end_date, employee_is_active, employee_termination_date):
    """Number of days a single employment record covers (open-ended
    current-company records count up to today, or up to the employee's
    computed termination date if that record itself isn't the terminating
    one but the employee has since left). `end_date` is this record's
    computed chain end (see compute_chain_end_dates) — date_to is no longer
    a stored column, so it's always passed in rather than read off the
    record."""
    if not record.date_from:
        return 0

    end = end_date
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


def get_last_current_company_record(
    employee_id, exclude_id=None, before_date=None, is_current=True
):
    """Returns the most recent (by date_from) EmploymentRecord of the given
    type (CURRENT-COMPANY by default, or KƏNAR/external when
    `is_current=False`) for this employee, or None if there isn't one yet.
    The "cari şirkət" and "kənar şirkət" chains are tracked independently —
    each has its own hire/transfer/termination sequence (see
    _allowed_movement_types in app.modules.hr.routes).

    `before_date`, when given, restricts the search to records that start
    STRICTLY BEFORE that date — i.e. it finds the record that immediately
    PRECEDES a given position in the chain, rather than whatever is latest
    overall. This matters when editing a record that sits in the MIDDLE of
    the chain: without `before_date`, "last record excluding this one" could
    wrongly resolve to a record that comes AFTER it chronologically (e.g.
    editing a 'transfer' that has a 'termination' after it would otherwise
    see that later termination as its "predecessor"). Always pass the
    record's own (new) date_from here when validating/auto-filling an edit.

    Used both to validate the allowed "Hərəkət növü" for a new/edited record
    (see _validate_work_history_form) and to auto-fill the struktur/vəzifə
    (or, for kənar records, the şirkət/struktur/vəzifə) shown for a
    "İşdən çıxma" record (which has no struktur/vəzifə of its own)."""
    query = EmploymentRecord.query.filter_by(
        employee_id=employee_id, is_current_company=is_current
    )
    if exclude_id is not None:
        query = query.filter(EmploymentRecord.id != exclude_id)
    if before_date is not None:
        query = query.filter(EmploymentRecord.date_from < before_date)
    return query.order_by(
        EmploymentRecord.date_from.desc(), EmploymentRecord.id.desc()
    ).first()


def compute_chain_end_dates(employee_id, records=None):
    """
    Returns `{record_id: end_date_or_None}` for EVERY EmploymentRecord of
    this employee — cari şirkət and kənar iş yeri together, in one single
    chronological timeline ordered by `date_from`. There is no stored
    `date_to` column any more — every record's end is always computed on
    the fly, purely from what comes next in the timeline:

      - A "İşdən çıxma" record is a point-in-time event: its own end is
        always its own date_from, regardless of what follows (this is what
        allows a later "İşə qəbul" to start after a gap, instead of being
        forced to begin the very next day). This applies to BOTH cari
        şirkət and kənar şirkət terminations — each type's chain closes
        independently on its own "İşdən çıxma".
      - Any other record (hire, transfer, kənar iş yeri) ends the day before
        the NEXT record (by date_from) starts — i.e. it automatically
        "closes" as soon as the next one begins.
      - The last record overall, if it isn't itself a termination, is
        open-ended (end = None -> hazırda davam edir).

    Because every end date is derived this way, two records can never
    overlap — the old "paralel iş qadağandır" overlap check
    (app/utils/date_overlap.py) is no longer needed for EmploymentRecord.

    Pass `records` (already loaded for this employee) to avoid a second
    query when the caller already has them.
    """
    if records is None:
        records = (
            EmploymentRecord.query.filter_by(employee_id=employee_id)
            .order_by(EmploymentRecord.date_from.asc(), EmploymentRecord.id.asc())
            .all()
        )
    else:
        records = sorted(records, key=lambda r: (r.date_from, r.id))

    ends = {}
    for i, record in enumerate(records):
        if record.movement_type == "termination":
            ends[record.id] = record.date_from
        elif i + 1 < len(records):
            ends[record.id] = records[i + 1].date_from - timedelta(days=1)
        else:
            ends[record.id] = None
    return ends


def recompute_employee_from_history(employee):
    """Recomputes and assigns (but does not commit) the derived fields on
    `employee` based on its EmploymentRecord rows."""

    all_records = (
        EmploymentRecord.query.filter_by(employee_id=employee.id)
        .order_by(EmploymentRecord.date_from.asc())
        .all()
    )
    end_dates = compute_chain_end_dates(employee.id, records=all_records)

    current_records = [r for r in all_records if r.is_current_company]

    if current_records:
        # Şirkətə qəbul olduğu ilk tarix = ən erkən "cari şirkət" qeydinin tarixi
        employee.hire_date = current_records[0].date_from

        latest = current_records[-1]
        latest_end = end_dates.get(latest.id)

        # Əməkdaş passivdir, əgər:
        #   (a) son qeydin "Hərəkət növü" sahəsi açıq şəkildə "İşdən çıxma"
        #       seçilibsə (istifadəçinin bilərəkdən verdiyi siqnal), VƏ YA
        #   (b) son qeydin (hesablanmış) bitmə tarixi keçmişdədirsə (məs.
        #       ondan sonra başlayan kənar iş yeri qeydi əlavə olunubsa) —
        #       iş yerinin fəaliyyəti artıq bitmiş deməkdir; "Hərəkət növü"
        #       nü açıq şəkildə "İşdən çıxma"ya dəyişmək tələb olunmur.
        # Əks halda (bitmə tarixi boşdur = davam edir, YA DA gələcəkdədir)
        # əməkdaş aktivdir.
        ended_by_movement_type = latest.movement_type == "termination"
        ended_by_past_end = latest_end is not None and latest_end < date.today()

        if ended_by_movement_type or ended_by_past_end:
            employee.is_active = False
            employee.termination_date = latest_end or latest.date_from
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
        _record_days(r, end_dates.get(r.id), employee.is_active, employee.termination_date)
        for r in all_records
        if r.is_current_company
    )
    other_days = sum(
        _record_days(r, end_dates.get(r.id), employee.is_active, employee.termination_date)
        for r in all_records
        if not r.is_current_company
    )

    employee.company_experience = _format_experience(company_days)
    employee.other_experience = _format_experience(other_days)
    employee.total_experience = _format_experience(company_days + other_days)

    # Qalan məzuniyyət günləri artıq əl ilə redaktə edilmir — "Məzuniyyət
    # günləri" hesablamasından (əsas + əlavə qalıq) avtomatik götürülür.
    # Local import to avoid a module-load-order cycle with leave_service,
    # which itself imports from app.models.
    from app.services.leave_service import get_leave_balance

    if current_records:
        balance = get_leave_balance(employee)
        employee.remaining_vacation_days = balance["total"]
    else:
        employee.remaining_vacation_days = None


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