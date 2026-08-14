from datetime import datetime
from app import db


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(64))  # denormalised, survives user deletion
    module = db.Column(db.String(30))
    action = db.Column(db.String(50))  # ADD / EDIT / DELETE / VIEW / REPORT / LOGIN ...
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
