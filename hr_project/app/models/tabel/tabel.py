from app import db


class TabelEntry(db.Model):
    __tablename__ = "tabel_entries"
    __table_args__ = (
        db.UniqueConstraint("employee_id", "work_date", name="uq_tabel_employee_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False)
    hours_worked = db.Column(db.Float, default=8)
    status = db.Column(db.String(30), default="present")  # present/absent/vacation/sick
    note = db.Column(db.String(255))

    employee = db.relationship("Employee")
