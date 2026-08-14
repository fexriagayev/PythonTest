from app import db
from datetime import datetime


class InsurancePolicy(db.Model):
    """'Sığorta məlumatları' tab. Start/end dates power the dashboard
    'expired / expiring within a month' notifications."""

    __tablename__ = "insurance_policies"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    insurance_company_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    insurance_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    policy_number = db.Column(db.String(50))
    amount = db.Column(db.Numeric(12, 2))
    note = db.Column(db.Text)

    employee = db.relationship(
        "Employee",
        backref=db.backref(
            "insurance_policies", cascade="all, delete-orphan", lazy="dynamic"
        ),
    )
    insurance_company = db.relationship(
        "DictionaryItem", foreign_keys=[insurance_company_id]
    )
    insurance_type = db.relationship("DictionaryItem", foreign_keys=[insurance_type_id])
