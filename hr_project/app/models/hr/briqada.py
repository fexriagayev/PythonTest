from app import db
from datetime import datetime


class Briqada(db.Model):
    """Bir BRİQADA (iş komandası) — TƏK CƏDVƏLDƏ saxlanılır (ayrıca
    "üzvlər" cədvəli YOXDUR): bir briqadanın HƏR ÜZVÜ öz SƏTRİDİR, eyni
    `group_no`-nu (və eyni header_id/tarix/status/prioritet dəyərlərini)
    paylaşır. Yəni 3 üzvlü bir briqada = eyni group_no-lu 3 sətir.

    `group_no` — DB-nin öz `id`-sindən (hər sətrin öz unikal sətir
    nömrəsi) FƏRQLİ olaraq, "bu sətirlər EYNİ briqadaya aiddir" əlaqəsini
    daşıyır (bax: app.modules.sites.routes — siyahı/redaktə/silmə bu
    dəyərə görə QRUPLAŞDIRIR). Sərkərdə (header) MƏCBURİ, ÜZV isə YA
    `member_id` (mövcud əməkdaş), YA `member_name` (sərbəst mətn,
    sistemdə qeydiyyatı olmayan işçi üçün) — heç vaxt hər ikisi.
    """

    __tablename__ = "briqadalar"

    id = db.Column(db.Integer, primary_key=True)
    group_no = db.Column(db.Integer, nullable=False, index=True)
    header_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    priority = db.Column(db.Integer, default=0)
    member_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    member_name = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    header = db.relationship("Employee", foreign_keys=[header_id])
    member = db.relationship("Employee", foreign_keys=[member_id])

    def member_display_name(self):
        return self.member.full_name if self.member else self.member_name
