from app import db


class SalaryEntry(db.Model):
    __tablename__ = "salary_entries"
    __table_args__ = (
        db.UniqueConstraint("employee_id", "period", name="uq_salary_employee_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    period = db.Column(db.String(7), nullable=False)  # "YYYY-MM"
    base_salary = db.Column(db.Numeric(12, 2), default=0)
    bonus = db.Column(db.Numeric(12, 2), default=0)
    deductions = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    note = db.Column(db.String(255))

    employee = db.relationship("Employee")
