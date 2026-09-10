from app import db
from datetime import timedelta


class Holiday(db.Model):
    """A bayram/matəm (public holiday) date RANGE, excluded from day
    counts for leave reasons using the 'workdays_no_holidays' method and
    stamped onto the Tabel matrix (see app.services.tabel_service).

    A holiday can span several days (`start_date`..`end_date`, inclusive
    on both ends — for a single-day holiday they're equal) and can be
    marked `is_recurring` so it doesn't have to be re-entered every year:
    a recurring holiday's MONTH/DAY repeat every year, its stored
    `start_date`/`end_date` YEAR is only used to derive the duration
    (end - start) and is otherwise ignored — see `covers()`/`occurrence_for_year()`.
    """

    __tablename__ = "holidays"

    # "bayram" (B) or "matam" (M — matəm/mourning day). Used by
    # app.services.tabel_service to stamp the Tabel matrix.
    HOLIDAY_CODES = {"bayram": "B", "matam": "M"}

    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    name = db.Column(db.String(150))
    holiday_type = db.Column(db.String(10), nullable=False, default="bayram")
    # True -> təkrarlanır: hər il eyni ay/gündə (müddəti eyni saxlanılmaqla)
    # avtomatik nəzərə alınır, hər il yenidən daxil etməyə ehtiyac qalmır.
    is_recurring = db.Column(db.Boolean, default=False, nullable=False)

    def duration_days(self):
        """Neçə gün davam edir (1 günlük bayram üçün 0)."""
        return (self.end_date - self.start_date).days

    @staticmethod
    def _safe_replace_year(d, year):
        """d.replace(year=year) — 29 Fevral kimi mövcud olmayan tarixlər
        üçün (qeyri-uzun il) 28 Fevrala düşür."""
        try:
            return d.replace(year=year)
        except ValueError:
            return d.replace(year=year, day=28)

    def occurrence_for_year(self, year):
        """Bu bayramın (təkrarlanan olsun-olmasın) `year`-də başlayan
        konkret tarix aralığını qaytarır: (occ_start, occ_end)."""
        if not self.is_recurring:
            return self.start_date, self.end_date
        occ_start = self._safe_replace_year(self.start_date, year)
        occ_end = occ_start + timedelta(days=self.duration_days())
        return occ_start, occ_end

    def covers(self, d):
        """`d` (date) bu bayramın hər hansı təkrarına düşürmü?"""
        if not self.is_recurring:
            return self.start_date <= d <= self.end_date
        # Təkrarlanan bayram üçün, sərhəd (məs. 31 dekabr — 1 yanvar)
        # hallarını tutmaq üçün d-nin ilinə görə yaranan təkrarla YANAŞI,
        # əvvəlki ilin təkrarını da yoxlayırıq (o, yeni ilə "daşa" bilər).
        for year in (d.year, d.year - 1):
            occ_start, occ_end = self.occurrence_for_year(year)
            if occ_start <= d <= occ_end:
                return True
        return False

    @classmethod
    def marks_in_range(cls, range_start, range_end):
        """{date: 'B'|'M'} — [range_start, range_end] aralığına düşən HƏR
        bayram günü üçün (təkrarlanan bayramlar müvafiq ilə genişləndirilir)."""
        marks = {}
        holidays = cls.query.all()
        d = range_start
        while d <= range_end:
            for h in holidays:
                if h.covers(d):
                    marks[d] = cls.HOLIDAY_CODES.get(h.holiday_type, "B")
                    break
            d += timedelta(days=1)
        return marks
