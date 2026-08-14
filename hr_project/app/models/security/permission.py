from app import db


class Permission(db.Model):
    """One row per (user, module) holding the granular access flags."""

    __tablename__ = "permissions"
    __table_args__ = (
        db.UniqueConstraint("user_id", "module_id", name="uq_user_module"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)

    module = db.relationship("Module")

    # Main data permissions
    can_add = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_view = db.Column(db.Boolean, default=False)
    can_report = db.Column(db.Boolean, default=False)

    # Dictionary (reference book) permissions for this module
    dict_add = db.Column(db.Boolean, default=False)
    dict_edit = db.Column(db.Boolean, default=False)
    dict_delete = db.Column(db.Boolean, default=False)
    dict_view = db.Column(db.Boolean, default=False)
