from app import db
from datetime import datetime


class Holiday(db.Model):
    """A single bayram/matəm (public holiday) date, excluded from day
    counts for leave reasons using the 'workdays_no_holidays' method."""

    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    name = db.Column(db.String(150))
