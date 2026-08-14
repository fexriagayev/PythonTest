from app import db


class DictionaryItem(db.Model):
    """Generic reference-book (dictionary) entry, scoped per module + category."""

    __tablename__ = "dictionary_items"

    id = db.Column(db.Integer, primary_key=True)
    module_code = db.Column(db.String(20), nullable=False)  # HR / TABEL / SALARY
    category = db.Column(
        db.String(60), nullable=False
    )  # e.g. department, position, status
    name = db.Column(db.String(150), nullable=False)
    value = db.Column(db.String(150))
    is_active = db.Column(db.Boolean, default=True)
