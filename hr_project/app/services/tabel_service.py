"""
Business logic for the Tabel (timesheet) module.

Generation flow (see generate_period()):
  1. Find every employee who has at least one active current-company
     stint overlapping the period.
  2. For each calendar day of the month, decide the automatic mark:
       - A Holiday-table date -> "B" (bayram) or "M" (matəm).
       - Otherwise, Saturday/Sunday -> REST_DAY_CODE ("İ").
       - Otherwise, an İş buraxması (LeaveRequest) covering that day ->
         that reason's `tabel_code`.
       - Otherwise (an ordinary work day) -> DEFAULT_WORK_MARK ("+"),
         i.e. the employee is assumed present by default.
     A day the employee wasn't active on at all (before hire / after
     termination within the month) has NO key in day_marks -> always
     blank/grey, never editable.
  3. The user can then click any ordinary work-day cell to toggle
     "+" <-> "-" (see cycle_cell()) if they need to correct it.
"""

from datetime import date, datetime, timedelta
import calendar

from app import db
from app.models import (
    Employee,
    EmploymentRecord,
    EmploymentContractNotification,
    Holiday,
    LeaveRequest,
    TabelEmployeeRow,
)
from app.services.leave_service import get_employment_stints

REST_DAY_CODE = "İ"
HOLIDAY_CODES = {"bayram": "B", "matam": "M"}
LOCKED_NON_WORKING_CODES = {REST_DAY_CODE, "B", "M"}
DEFAULT_WORK_MARK = "+"  # generasiya zamanı adi iş günləri default olaraq "+" (işdə) qəbul olunur
EDITABLE_VALUES = ("+", "-")
CYCLE_NEXT = {"+": "-", "-": "+"}


def month_bounds(year, month):
    """(first_date, last_date, days_in_month) for the given Ay/İl."""
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days_in_month), days_in_month


def _employees_with_current_stint():
    employee_ids = (
        db.session.query(EmploymentRecord.employee_id)
        .filter_by(is_current_company=True)
        .distinct()
    )
    return Employee.query.filter(Employee.id.in_(employee_ids)).all()


def _active_days(employee, period_start, period_end):
    """Set of day-of-month ints where `employee` has an active
    current-company stint on that calendar date."""
    active = set()
    for stint_start, stint_end in get_employment_stints(employee):
        s = max(stint_start, period_start)
        e = min(stint_end, period_end) if stint_end else period_end
        if e < s:
            continue
        cur = s
        while cur <= e:
            active.add(cur.day)
            cur += timedelta(days=1)
    return active


def _weekend_days(period_start, period_end):
    """Set of day-of-month ints that are Şənbə (Saturday) or Bazar
    (Sunday)."""
    weekend = set()
    cur = period_start
    while cur <= period_end:
        if cur.weekday() in (5, 6):  # 5 == Saturday, 6 == Sunday
            weekend.add(cur.day)
        cur += timedelta(days=1)
    return weekend


def _holiday_marks(period_start, period_end):
    """{day_of_month: 'B'|'M'} for Holiday-table dates within the period
    (bayram -> 'B', matəm -> 'M')."""
    marks = {}
    for h in Holiday.query.filter(
        Holiday.date >= period_start, Holiday.date <= period_end
    ).all():
        marks[h.date.day] = HOLIDAY_CODES.get(h.holiday_type, "B")
    return marks


def _leave_marks_for_employee(employee, period_start, period_end):
    """{day_of_month: tabel_code} for every day in the period covered by
    an İş buraxması (LeaveRequest)."""
    marks = {}
    requests = LeaveRequest.query.filter(
        LeaveRequest.employee_id == employee.id,
        LeaveRequest.start_date <= period_end,
        LeaveRequest.end_date >= period_start,
    ).all()
    for r in requests:
        code = r.leave_reason.tabel_code or (r.leave_reason.name or "?")[:3].upper()
        ov_start = max(r.start_date, period_start)
        ov_end = min(r.end_date, period_end)
        cur = ov_start
        while cur <= ov_end:
            marks[cur.day] = code
            cur += timedelta(days=1)
    return marks


def _contract_number_at(employee, as_of_date):
    """'M/n' — the contract_number of the Bildiriş in effect on
    `as_of_date` (the most recent one starting on/before that date)."""
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
    return latest.contract_number if latest else None


def generate_period(period):
    """Populates TabelEmployeeRow rows for `period` (overwrites any
    existing rows for this period — safe to call again). Does not
    commit; caller commits."""
    period_start, period_end, days_in_month = month_bounds(period.year, period.month)

    TabelEmployeeRow.query.filter_by(period_id=period.id).delete()

    employees = sorted(_employees_with_current_stint(), key=lambda e: e.full_name or "")
    weekend_days = _weekend_days(period_start, period_end)
    holiday_marks = _holiday_marks(period_start, period_end)

    row_no = 0
    for employee in employees:
        active_days = _active_days(employee, period_start, period_end)
        if not active_days:
            continue

        row_no += 1
        leave_marks = _leave_marks_for_employee(employee, period_start, period_end)

        day_marks = {}
        for day in range(1, days_in_month + 1):
            if day not in active_days:
                continue  # inactive -> no key -> blank/grey, non-editable
            if day in holiday_marks:
                day_marks[str(day)] = holiday_marks[day]
            elif day in weekend_days:
                day_marks[str(day)] = REST_DAY_CODE
            elif day in leave_marks:
                day_marks[str(day)] = leave_marks[day]
            else:
                day_marks[str(day)] = DEFAULT_WORK_MARK  # adi iş günü -> default "+"

        db.session.add(
            TabelEmployeeRow(
                period_id=period.id,
                employee_id=employee.id,
                row_no=row_no,
                full_name_snapshot=employee.full_name,
                position_snapshot=employee.position,
                contract_number_snapshot=_contract_number_at(employee, period_end),
                day_marks=day_marks,
            )
        )

    period.is_generated = True
    period.generated_at = datetime.utcnow()


def cycle_cell(row, day):
    """Toggles one day cell '+' <-> '-' for an ordinary work day of `row`
    (a TabelEmployeeRow). Returns the new value. Raises ValueError if
    that cell isn't editable (locked auto-generated code, or the
    employee wasn't active that day)."""
    key = str(day)
    marks = dict(row.day_marks or {})
    current = marks.get(key)
    if current is None or current not in EDITABLE_VALUES:
        raise ValueError("Bu xana redaktə oluna bilməz.")
    marks[key] = CYCLE_NEXT[current]
    row.day_marks = marks  # reassign the whole dict so SQLAlchemy detects the change
    return marks[key]
