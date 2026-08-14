from app import db
from app.models.dictionaries.dictionary import DictionaryItem
from datetime import datetime
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import validates
from sqlalchemy.ext.hybrid import hybrid_property


class SalaryCard(db.Model):
    """'Maaş kartları' tab. valid_until powers the dashboard 'expired /
    expiring within a month' notifications."""

    __tablename__ = "salary_cards"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    bank_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    account_number = db.Column(db.String(50))
    valid_until = db.Column(db.Date)
    card_holder_name = db.Column(db.String(150))
    note = db.Column(db.Text)

    employee = db.relationship(
        "Employee",
        backref=db.backref(
            "salary_cards", cascade="all, delete-orphan", lazy="dynamic"
        ),
    )
    bank = db.relationship("DictionaryItem", foreign_keys=[bank_id])
