from app import db
from app.models.dictionaries.dictionary import DictionaryItem


class Order(db.Model):
    """
    'Əmr' (kadr əmri) — a structured HR dictionary entity (not a plain
    name/value DictionaryItem, since it needs several real fields). Used to
    justify hiring, internal transfer, or termination records in an
    employee's əmək kitabçası (EmploymentRecord).
    """

    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), nullable=False)  # Əmrin nömrəsi
    order_date = db.Column(db.Date, nullable=False)  # Əmrin tarixi
    effective_date = db.Column(db.Date)  # Qüvvəyə minmə tarixi
    order_type_id = db.Column(
        db.Integer, db.ForeignKey("dictionary_items.id")
    )  # Əmrin növü
    note = db.Column(db.Text)  # Qeyd

    order_type = db.relationship("DictionaryItem", foreign_keys=[order_type_id])

    def label(self):
        type_name = self.order_type.name if self.order_type else ""
        return f"№{self.number} / {self.order_date} — {type_name}"
