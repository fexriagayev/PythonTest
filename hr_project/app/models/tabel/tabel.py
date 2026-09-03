from app import db
from datetime import datetime


class TabelPeriod(db.Model):
    """Bir ay üçün 'Tabel' (dövr) — 'Tabellər' siyahısındakı hər sətir.

    Matris (əməkdaş × gün) generasiya olunana qədər bu sətrin heç bir
    TabelEmployeeRow-u olmur; "Tabeli generasiya et" düyməsi
    app.services.tabel_service.generate_period()-i çağırıb onları yaradır.
    """

    __tablename__ = "tabel_periods"
    __table_args__ = (
        db.UniqueConstraint("year", "month", name="uq_tabel_period_year_month"),
    )

    MONTH_NAMES_AZ = [
        "Yanvar", "Fevral", "Mart", "Aprel", "May", "İyun",
        "İyul", "Avqust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr",
    ]

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12

    is_generated = db.Column(db.Boolean, default=False, nullable=False)
    generated_at = db.Column(db.DateTime)

    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    approved_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rows = db.relationship(
        "TabelEmployeeRow",
        back_populates="period",
        cascade="all, delete-orphan",
        order_by="TabelEmployeeRow.row_no",
    )

    @property
    def label(self):
        """'Dövr' sütununda göstərilən mətn, məs. 'Avqust 2026'."""
        if 1 <= self.month <= 12:
            name = self.MONTH_NAMES_AZ[self.month - 1]
        else:
            name = str(self.month)
        return f"{name} {self.year}"


class TabelEmployeeRow(db.Model):
    """Bir əməkdaşın bir dövr (ay) üçün tabel sətri.

    Gündəlik işarələr `day_marks` JSON sahəsində saxlanılır:
    {"1": "İ", "2": "İ", "3": "NM", "4": "+", "5": "-", ...}

    Açarların (gün nömrələrinin) mənası:
      - Açar YOXDURSA  -> əməkdaş həmin gün AKTİV DEYİL (boz göstərilir,
        redaktə OLUNMUR).
      - Açar var, dəyər "+" / "-"  -> ADİ İŞ GÜNÜ, əl ilə redaktə oluna
        bilər (default "+" = işdə). Klik: "+" <-> "-".
      - Açar var, dəyər başqa hər hansı kod (İ, B, M, X, NM, ÖM, ...) ->
        AVTOMATİK yaranıb, KİLİDLİDİR, redaktə olunmur.
    """

    __tablename__ = "tabel_employee_rows"
    __table_args__ = (
        db.UniqueConstraint(
            "period_id", "employee_id", name="uq_tabel_period_employee"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(
        db.Integer, db.ForeignKey("tabel_periods.id"), nullable=False
    )
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    # Sıra (№) sütunu — generasiya zamanı əməkdaşın adına görə təyin olunur.
    row_no = db.Column(db.Integer, default=0)

    # --- Generasiya anında "şəkli çəkilən" (snapshot) sahələr ---------------
    # Sonradan əməkdaşın vəzifəsi/müqaviləsi dəyişsə belə, artıq
    # generasiya olunmuş keçmiş tabel dəyişməməlidir.
    full_name_snapshot = db.Column(db.String(200))
    position_snapshot = db.Column(db.String(120))
    contract_number_snapshot = db.Column(db.String(50))  # "M/n"

    day_marks = db.Column(db.JSON, default=dict)

    period = db.relationship("TabelPeriod", back_populates="rows")
    employee = db.relationship("Employee")

    def work_days_count(self):
        """'İş günlərinin sayı' — '+' (işdə olub) işarəli günlərin sayı."""
        marks = self.day_marks or {}
        return sum(1 for v in marks.values() if v == "+")
