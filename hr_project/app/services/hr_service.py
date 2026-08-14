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

from datetime import date
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
        if latest.movement_type == "termination":
            employee.is_active = False
            employee.termination_date = latest.date_from
            # Son bilinən vəzifə/struktur — çıxışdan əvvəlki qeyd
            prior = current_records[-2] if len(current_records) >= 2 else None
            employee.department = (
                prior.department.name if (prior and prior.department) else None
            )
            employee.position = (
                prior.position.name if (prior and prior.position) else None
            )
        else:
            employee.is_active = True
            employee.termination_date = None
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
