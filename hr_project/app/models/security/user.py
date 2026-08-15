from datetime import datetime
from app.models.dictionaries.module import Module
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models.base import TimestampMixin


class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False, default="")
    email = db.Column(db.String(150))

    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)

    # Admin can flip this flag per-user to start/stop activity logging
    log_flag = db.Column(db.Boolean, default=False, nullable=False)

    # Personal (Tools) preferences
    theme = db.Column(db.String(50), default="cosmo")
    font_size = db.Column(db.Integer, default=14)
    language = db.Column(db.String(5), default="az")

    must_change_password = db.Column(db.Boolean, default=True, nullable=False)

    permissions = db.relationship(
        "Permission", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def reset_to_default_password(self, default_password="test"):
        self.set_password(default_password)
        self.must_change_password = True

    def permission_for(self, module_code):
        return self.permissions.join(Module).filter(Module.code == module_code).first()

    def has_perm(self, module_code, field):
        if self.is_admin:
            return True
        perm = self.permission_for(module_code)
        if not perm:
            return False
        return bool(getattr(perm, field, False))

    @property
    def is_active(self):
        # Flask-Login (UserMixin) reads this exact property name to decide
        # whether a session/login is allowed. Blocked users must not count
        # as active, as an extra safety net alongside the login-time check
        # and the check_blocked_user before_request hook.
        return not self.is_blocked

    def __repr__(self):
        return f"<User {self.username}>"
