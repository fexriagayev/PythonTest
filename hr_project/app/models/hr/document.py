from app import db
from datetime import datetime


class Document(db.Model):
    """'Sənədlər' tab — uploaded files (ID photo, driving licence, etc.)."""

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)  # actual name on disk
    document_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    note = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship(
        "Employee",
        backref=db.backref("documents", cascade="all, delete-orphan", lazy="dynamic"),
    )
    document_type = db.relationship("DictionaryItem", foreign_keys=[document_type_id])
