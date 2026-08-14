from app import db
from datetime import datetime


class GridPreference(db.Model):
    """
    Per-user, per-grid customisation (column order/visibility/titles,
    footer & group-footer aggregate choices, grouping, sorting) stored in
    the database so it follows the user across browsers/devices, instead
    of living only in one browser's localStorage.
    """

    __tablename__ = "grid_preferences"
    __table_args__ = (db.UniqueConstraint("user_id", "grid_key", name="uq_user_grid"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    grid_key = db.Column(db.String(100), nullable=False)
    settings_json = db.Column(db.Text, nullable=False, default="{}")
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
