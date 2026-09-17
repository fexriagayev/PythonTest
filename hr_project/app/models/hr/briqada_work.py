from app import db
from datetime import datetime

AZ_MONTH_NAMES = [
    "", "Yanvar", "Fevral", "Mart", "Aprel", "May", "İyun",
    "İyul", "Avqust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr",
]

RUN_TYPES = [
    ("avans", "Avans"),
    ("yekun", "Yekun maaş"),
]


class BriqadaWorkPeriod(db.Model):
    """Bir "Obyektlər üzrə görülən işlər" matrisinin DÖVRÜ — ay ərzində
    İKİ DƏFƏ doldurulur (avans: adətən ayın 15-i, yekun maaş: ayın son
    günü), hər biri AYRI bir dövr (sətir) və AYRI-AYRI təsdiqlənir."""

    __tablename__ = "briqada_work_periods"
    __table_args__ = (
        db.UniqueConstraint("year", "month", "run_type", name="uq_briqada_work_period"),
    )

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    run_type = db.Column(db.String(10), nullable=False)  # 'avans' | 'yekun'
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    approved_by = db.relationship("User")
    entries = db.relationship(
        "BriqadaWorkEntry", cascade="all, delete-orphan", back_populates="period"
    )

    @property
    def label(self):
        run_label = dict(RUN_TYPES).get(self.run_type, self.run_type)
        return f"{AZ_MONTH_NAMES[self.month]} {self.year} — {run_label}"


class BriqadaWorkEntry(db.Model):
    """Matrisin BİR XANASI: bu dövrdə, bu briqada üzvünün (bax:
    Briqada.id — flat cədvəldə HƏR ÜZV öz sətridir), bu OBYEKTDƏ
    gördüyü işə görə aldığı məbləğ."""

    __tablename__ = "briqada_work_entries"
    __table_args__ = (
        db.UniqueConstraint(
            "period_id", "briqada_id", "obyekt_id", name="uq_briqada_work_entry"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("briqada_work_periods.id"), nullable=False)
    briqada_id = db.Column(db.Integer, db.ForeignKey("briqadalar.id"), nullable=False)
    obyekt_id = db.Column(db.Integer, db.ForeignKey("obyekts.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    period = db.relationship("BriqadaWorkPeriod", back_populates="entries")
    briqada_row = db.relationship("Briqada")
    obyekt = db.relationship("Obyekt")
