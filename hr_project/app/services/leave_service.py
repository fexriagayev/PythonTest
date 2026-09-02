"""
Business logic for:
  - "Məzuniyyət günləri" — automatically computed vacation-day periods
    (one row per employment year, split at rehire / category-change / at
    termination), each showing entitled base+bonus days, used days (from
    İş buraxmaları), compensated days (manual), and remaining days.
  - "İş buraxmaları" — leave/absence requests: automatic end-date
    calculation (calendar / workdays / workdays-excluding-holidays) and
    overlap validation.

IMPORTANT — simplifying assumptions (documented so they can be adjusted):
  * A "year" is a fixed 365-day span from the stint's hire date, not a
    calendar year. The final segment of a stint (or of the whole history,
    if still employed) is prorated by its actual length / 365.
  * Seniority for the bonus-day formula is total "current company" days
    of service up to the start of the segment, converted to whole years.
  * When a leave period is used, days are drawn from the "əsas" (base)
    bucket first, then "əlavə" (bonus) — a FIFO allocation, since actual
    leave requests don't themselves specify which bucket they draw from.
  * Overlap validation checks ANY two İş buraxmaları rows for the same
    employee, regardless of reason (an employee can't be both on leave
    and sick on the same day).
"""

from datetime import date, timedelta

from app.models import (
    EmploymentRecord,
    EmploymentContractNotification,
    LeaveRequest,
    LeaveReason,
    Holiday,
    VacationCompensation,
)

# ---------------------------------------------------------------------------
# İş buraxmaları — end-date calculation + overlap validation
# ---------------------------------------------------------------------------


def compute_end_date(start_date, day_count, counting_method):
    """First date reached after counting `day_count` qualifying days,
    starting from (and including) start_date."""
    if not start_date or not day_count or day_count <= 0:
        return start_date

    if counting_method == "calendar":
        return start_date + timedelta(days=day_count - 1)

    holidays = set()
    if counting_method == "workdays_no_holidays":
        holidays = {h.date for h in Holiday.query.all()}

    cur = start_date
    counted = 0
    while True:
        is_weekend = cur.weekday() >= 5  # 5=Saturday, 6=Sunday
        is_holiday = cur in holidays
        if not is_weekend and not is_holiday:
            counted += 1
            if counted == day_count:
                return cur
        cur += timedelta(days=1)


def validate_leave_request(employee, start_date, end_date, exclude_id=None):
    """Returns an error string if this date range overlaps any other İş
    buraxması of the same employee, else None."""
    query = LeaveRequest.query.filter(
        LeaveRequest.employee_id == employee.id,
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )
    if exclude_id:
        query = query.filter(LeaveRequest.id != exclude_id)
    conflict = query.first()
    if conflict:
        return (
            f"Bu tarix aralığı artıq mövcud qeydlə kəsişir: "
            f"{conflict.leave_reason.name} ({conflict.start_date} — {conflict.end_date})."
        )
    return None


# ---------------------------------------------------------------------------
# Məzuniyyət günləri — automatic period computation
# ---------------------------------------------------------------------------


def _add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + years)  # Feb 29 safety


def get_employment_stints(employee):
    """List of (start_date, end_date_or_None) spans of continuous
    employment at the current company, derived from 'hire'/'termination'
    EmploymentRecord rows. end_date=None means the stint is still ongoing."""
    records = (
        EmploymentRecord.query.filter_by(
            employee_id=employee.id, is_current_company=True
        )
        .order_by(EmploymentRecord.date_from.asc())
        .all()
    )
    stints = []
    current_start = None
    for r in records:
        if r.movement_type == "hire":
            if current_start is not None:
                stints.append(
                    (current_start, r.date_from)
                )  # defensive: unterminated previous stint
            current_start = r.date_from
        elif r.movement_type == "termination":
            if current_start is not None:
                stints.append((current_start, r.date_from))
                current_start = None
    if current_start is not None:
        stints.append((current_start, None))
    return stints


def get_category_timeline(employee):
    """List of (start_date, end_date_or_None, LeaveCategory) — which
    category was in effect over which date range, from Bildiriş history."""
    records = (
        EmploymentContractNotification.query.filter_by(employee_id=employee.id)
        .filter(EmploymentContractNotification.leave_category_id.isnot(None))
        .order_by(EmploymentContractNotification.start_date.asc())
        .all()
    )
    timeline = []
    for i, r in enumerate(records):
        end = records[i + 1].start_date if i + 1 < len(records) else None
        timeline.append((r.start_date, end, r.leave_category))
    return timeline


def _category_at(timeline, d):
    for start, end, cat in timeline:
        if start <= d and (end is None or d < end):
            return cat
    return None


def _generate_year_segments(stint_start, stint_limit):
    """Raw 1-year segments [start, end) from stint_start to stint_limit,
    the last one prorated if shorter than a year."""
    segments = []
    cur = stint_start
    n = 1
    while True:
        nxt = _add_years(stint_start, n)
        if nxt >= stint_limit:
            if cur < stint_limit:
                segments.append((cur, stint_limit))
            break
        segments.append((cur, nxt))
        cur = nxt
        n += 1
        if n > 80:  # safety cap
            break
    return segments


def _split_by_category_changes(seg_start, seg_end, timeline):
    change_points = sorted({cp for (cp, _, _) in timeline if seg_start < cp < seg_end})
    points = [seg_start] + change_points + [seg_end]
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]


def _days_of_service_before(employee, as_of_date):
    """Total 'current company' days of service across all stints, up to
    (not including) as_of_date — used for the seniority bonus-day rule."""
    total = 0
    for start, end in get_employment_stints(employee):
        seg_end = min(end, as_of_date) if end else min(date.today(), as_of_date)
        if seg_end > start:
            total += (seg_end - start).days
    return total


def _days_used_in_period(employee, period_start, period_end_exclusive, is_annual):
    """Sum of İş buraxmaları day-overlap with [period_start, period_end)
    for reasons flagged is_annual_leave == is_annual."""
    period_end_inclusive = period_end_exclusive - timedelta(days=1)
    requests = (
        LeaveRequest.query.join(LeaveReason)
        .filter(
            LeaveRequest.employee_id == employee.id,
            LeaveReason.is_annual_leave == is_annual,
            LeaveRequest.start_date <= period_end_inclusive,
            LeaveRequest.end_date >= period_start,
        )
        .all()
    )
    total = 0
    for r in requests:
        ov_start = max(r.start_date, period_start)
        ov_end = min(r.end_date, period_end_inclusive)
        total += max((ov_end - ov_start).days + 1, 0)
    return total


def compute_leave_periods(employee):
    """
    Returns the full list of Məzuniyyət günləri rows for an employee, each:
      period_start, period_end, category (LeaveCategory|None),
      category_days (base_vacation_days of that category),
      entitled_base, entitled_bonus,
      used_base, used_bonus,
      compensated_base, 
      remaining_base, remaining_bonus
    """
    stints = get_employment_stints(employee)
    timeline = get_category_timeline(employee)
    compensations = {
        c.period_start: c
        for c in VacationCompensation.query.filter_by(employee_id=employee.id).all()
    }

    rows = []
    for stint_start, stint_end in stints:
        stint_limit = stint_end or date.today()
        if stint_limit <= stint_start:
            continue
        for seg_start, seg_end in _generate_year_segments(stint_start, stint_limit):
            for sub_start, sub_end in _split_by_category_changes(
                seg_start, seg_end, timeline
            ):
                category = _category_at(timeline, sub_start)
                period_days = (sub_end - sub_start).days
                factor = min(period_days / 365.0, 1.0)

                if category:
                    years_of_service = (
                        _days_of_service_before(employee, sub_start) / 365.0
                    )
                    base_days = category.base_vacation_days or 0
                    bonus_days = category.extra_days_for_years(years_of_service)
                else:
                    base_days = 0
                    bonus_days = 0

                entitled_base = round(base_days * factor)
                entitled_bonus = round(bonus_days * factor)

                used_total = _days_used_in_period(
                    employee, sub_start, sub_end, is_annual=True
                )
                # Bonus days are used up FIRST, then base days. This matters
                # because compensation for unused days is only ever paid for
                # the BASE bucket — so an employee should draw down their
                # bonus allowance before touching the (compensable) base days.
                used_bonus = min(used_total, entitled_bonus)
                used_base = min(max(used_total - used_bonus, 0), entitled_base)

                comp = compensations.get(sub_start)
                compensated_base = comp.compensated_base_days if comp else 0

                remaining_base = max(entitled_base - used_base - compensated_base, 0)
                remaining_bonus = max(
                    entitled_bonus - used_bonus, 0
                )

                rows.append(
                    {
                        "period_start": sub_start,
                        "period_end": sub_end
                        - timedelta(days=1),  # show as inclusive last day
                        "category": (
                            category.name
                            if category
                            else "(kateqoriya təyin edilməyib)"
                        ),
                        "category_days": category.base_vacation_days if category else 0,
                        "entitled_base": entitled_base,
                        "entitled_bonus": entitled_bonus,
                        "used_base": used_base,
                        "used_bonus": used_bonus,
                        "compensated_base": compensated_base,
                        "remaining_base": remaining_base,
                        "remaining_bonus": remaining_bonus,
                    }
                )
    return rows


def get_leave_balance(employee):
    """Total remaining base + bonus vacation days across all periods up to
    today — used to validate new İş buraxmaları (annual leave) requests."""
    periods = compute_leave_periods(employee)
    base = sum(p["remaining_base"] for p in periods)
    bonus = sum(p["remaining_bonus"] for p in periods)
    return {"base": base, "bonus": bonus, "total": base + bonus}


def get_remaining_vacation_days_live(employee):
    """"Qalan məzuniyyət günləri" dəyəri HƏR ÇAĞIRIŞDA "Məzuniyyət günləri"
    cədvəlindən (compute_leave_periods/get_leave_balance) canlı hesablanır —
    saxlanılan (cached) Employee.remaining_vacation_days sütunundan ASILI
    DEYİL. Bu vacibdir, çünki son sətir bugünkü tarixə qədər proqressiv
    hesablanır (məs. cari ilin qalıq günləri) və tarix dəyişdikcə (hər gün)
    nəticə də dəyişə bilər — statik/keşlənmiş dəyər tez köhnəlmiş olardı.

    Əməkdaşın heç bir "cari şirkət" iş yeri qeydi yoxdursa (hələ heç bir
    əmək kitabçası qeydi daxil edilməyibsə), None qaytarılır ('—' göstərilsin
    deyə) — bax: hr_service.recompute_employee_from_history-dəki eyni şərt.
    """
    has_current_history = (
        EmploymentRecord.query.filter_by(
            employee_id=employee.id, is_current_company=True
        ).first()
        is not None
    )
    if not has_current_history:
        return None
    return get_leave_balance(employee)["total"]
