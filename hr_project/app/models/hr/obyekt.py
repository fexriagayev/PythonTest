from app import db
from datetime import datetime


class Obyekt(db.Model):
    """Tikinti şirkətinin bir OBYEKTİ (sahə/layihə) — briqadalar bu
    obyektlərdə işləyir (bax: Briqada). `owner_id` — özünə-istinad edən
    FK (Obyekt.id) — bir obyektin başqa bir (valideyn) obyektin
    tərkibinə daxil ola bilməsi üçün (məs. böyük bir layihənin
    tərkibindəki alt-sahələr); əlaqəsi yoxdursa NULL."""

    __tablename__ = "obyekts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    priority = db.Column(db.Integer, default=0)
    owner_id = db.Column(db.Integer, db.ForeignKey("obyekts.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("Obyekt", remote_side=[id], backref="sub_obyekts")
