from app import db
from datetime import datetime


class ErrorReport(db.Model):
    """Stores a copy of every error report sent to the developer (even if
    the outgoing email itself fails), so nothing is lost."""

    __tablename__ = "error_reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(64))
    url = db.Column(db.String(500))
    message = db.Column(db.Text)
    stack = db.Column(db.Text)
    last_action = db.Column(db.Text)
    screenshot_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_sent = db.Column(db.Boolean, default=False)
