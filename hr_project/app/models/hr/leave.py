from app import db
from datetime import datetime


class LeaveReason(db.Model):
    """
    'İş buraxma səbəbi' (İş buraxmaları → dictionary) — a structured
    dictionary because each reason needs a day-counting rule for computing
    the end date automatically:
      - calendar:              end = start + day_count - 1 (all days count)
      - workdays:               weekends don't count towards day_count
      - workdays_no_holidays:    weekends AND Holiday-table dates don't count
    """

    __tablename__ = "leave_reasons"

    COUNTING_METHODS = [
        ("calendar", "Təqvim günləri (hamısı)"),
        ("workdays", "İş günləri (həftə sonu xaric)"),
        ("workdays_no_holidays", "İş günləri (həftə sonu + bayram/matəm xaric)"),
    ]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    counting_method = db.Column(db.String(30), nullable=False, default="calendar")
    # Marks the reason that represents ordinary paid leave, i.e. the one
    # that draws down the Məzuniyyət günləri balance and needs the
    # available-days check before it can be submitted.
    is_annual_leave = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def counting_method_label(self):
        return dict(self.COUNTING_METHODS).get(
            self.counting_method, self.counting_method
        )


class LeaveCategory(db.Model):
    """
    'Kateqoriya' (Bildirişlər → Part 5) — a structured HR dictionary that
    drives vacation-day calculations, not just a plain name/value. Example:
    'Dövlət qulluqçusu': 30 base days, +2 extra days every 5 years of
    seniority, capped at 6 extra days total.
    """

    __tablename__ = "leave_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    base_vacation_days = db.Column(db.Integer, nullable=False, default=30)

    # Seniority bonus rule: +bonus_days_per_interval every
    # seniority_years_per_bonus years of service, capped at max_bonus_days.
    seniority_years_per_bonus = db.Column(db.Integer, default=0)  # e.g. 5 (years)
    bonus_days_per_interval = db.Column(db.Integer, default=0)  # e.g. 2 (days)
    max_bonus_days = db.Column(db.Integer, default=0)  # e.g. 6 (days)

    is_active = db.Column(db.Boolean, default=True)

    def extra_days_for_years(self, years_of_service):
        """How many bonus vacation days someone with this category and this
        much seniority is entitled to (capped at max_bonus_days)."""
        if not self.seniority_years_per_bonus or not self.bonus_days_per_interval:
            return 0
        intervals = int(years_of_service) // self.seniority_years_per_bonus
        earned = intervals * self.bonus_days_per_interval
        return min(earned, self.max_bonus_days or earned)

    def total_days_for_years(self, years_of_service):
        return (self.base_vacation_days or 0) + self.extra_days_for_years(
            years_of_service
        )


class LeaveRequest(db.Model):
    """'İş buraxmaları' — a single absence record (sick leave, annual
    leave, etc.). end_date is always derived from start_date + day_count
    using the linked LeaveReason's counting method."""

    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    leave_reason_id = db.Column(
        db.Integer, db.ForeignKey("leave_reasons.id"), nullable=False
    )
    start_date = db.Column(db.Date, nullable=False)
    day_count = db.Column(db.Integer, nullable=False)
    end_date = db.Column(
        db.Date, nullable=False
    )  # computed, stored for fast querying/overlap checks
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship(
        "Employee",
        backref=db.backref(
            "leave_requests", cascade="all, delete-orphan", lazy="dynamic"
        ),
    )
    leave_reason = db.relationship("LeaveReason")
    order = db.relationship("Order")


class VacationCompensation(db.Model):
    """
    Manual entry recording how many unused base/bonus vacation days were
    paid out (compensated) for a given computed leave period. Leave
    periods themselves are computed on the fly (see
    app/services/leave_service.py), so this is matched back to a period by
    (employee_id, period_start) rather than a foreign key to a stored row.
    """

    __tablename__ = "vacation_compensations"
    __table_args__ = (
        db.UniqueConstraint("employee_id", "period_start", name="uq_employee_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    compensated_base_days = db.Column(db.Integer, default=0)
    note = db.Column(db.Text)

    employee = db.relationship(
        "Employee",
        backref=db.backref(
            "vacation_compensations", cascade="all, delete-orphan", lazy="dynamic"
        ),
    )
