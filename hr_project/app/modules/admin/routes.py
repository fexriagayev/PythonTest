import os
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    send_file, current_app, abort
)
from flask_login import login_required, current_user

from app import db
from app.models import User, Module, Permission, ActivityLog
from app.utils.decorators import admin_required
from app.utils.logger import write_log, get_user_log_file_path

admin_bp = Blueprint("admin", __name__)

PERMISSION_FIELDS = [
    ("can_view", "Baxış"),
    ("can_add", "Əlavə etmək"),
    ("can_edit", "Dəyişmək"),
    ("can_delete", "Silmək"),
    ("can_report", "Hesabatlar"),
    ("dict_view", "Kitabça: Baxış"),
    ("dict_add", "Kitabça: Əlavə"),
    ("dict_edit", "Kitabça: Dəyişmək"),
    ("dict_delete", "Kitabça: Silmək"),
]


@admin_bp.before_request
@login_required
def _guard():
    if not current_user.is_admin:
        abort(403)


@admin_bp.route("/")
def index():
    users = User.query.order_by(User.username).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/users/create", methods=["GET", "POST"])
def create_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        is_admin = bool(request.form.get("is_admin"))

        if not username:
            flash("İstifadəçi adı tələb olunur.", "danger")
            return render_template("admin/user_form.html")

        if User.query.filter_by(username=username).first():
            flash("Bu istifadəçi adı artıq mövcuddur.", "danger")
            return render_template("admin/user_form.html")

        user = User(username=username, full_name=full_name, email=email, is_admin=is_admin)
        user.reset_to_default_password(current_app.config["DEFAULT_PASSWORD"])
        db.session.add(user)
        db.session.flush()

        # create an empty permission row per module so admin panel has
        # something to toggle right away
        for module in Module.query.all():
            db.session.add(Permission(user_id=user.id, module_id=module.id))

        db.session.commit()
        write_log(current_user, "ADMIN", "CREATE_USER", f"Yeni istifadəçi yaradıldı: {username}")
        flash(f"İstifadəçi '{username}' yaradıldı. Standart parol: "
              f"{current_app.config['DEFAULT_PASSWORD']}", "success")
        return redirect(url_for("admin.index"))

    return render_template("admin/user_form.html")


@admin_bp.route("/users/<int:user_id>/reset_password", methods=["POST"])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    user.reset_to_default_password(current_app.config["DEFAULT_PASSWORD"])
    db.session.commit()
    write_log(current_user, "ADMIN", "RESET_PASSWORD", f"Parol sıfırlandı: {user.username}")
    flash(f"'{user.username}' üçün parol standart dəyərə ('test') sıfırlandı.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>/toggle_block", methods=["POST"])
def toggle_block(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Öz hesabınızı bloklaya bilməzsiniz.", "warning")
        return redirect(url_for("admin.index"))
    user.is_blocked = not user.is_blocked
    db.session.commit()
    action = "BLOCK_USER" if user.is_blocked else "UNBLOCK_USER"
    write_log(current_user, "ADMIN", action, f"{user.username}")
    flash(f"'{user.username}' {'bloklandı' if user.is_blocked else 'blokdan çıxarıldı'}.", "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>/toggle_log_flag", methods=["POST"])
def toggle_log_flag(user_id):
    user = User.query.get_or_404(user_id)
    user.log_flag = not user.log_flag
    db.session.commit()
    write_log(current_user, "ADMIN", "TOGGLE_LOG_FLAG",
              f"{user.username} -> {'ON' if user.log_flag else 'OFF'}")
    flash(f"'{user.username}' üçün loglama {'aktivləşdirildi' if user.log_flag else 'söndürüldü'}.",
          "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>/permissions", methods=["GET", "POST"])
def permissions(user_id):
    user = User.query.get_or_404(user_id)
    modules = Module.query.all()

    if request.method == "POST":
        for module in modules:
            perm = Permission.query.filter_by(user_id=user.id, module_id=module.id).first()
            if not perm:
                perm = Permission(user_id=user.id, module_id=module.id)
                db.session.add(perm)
            for field, _ in PERMISSION_FIELDS:
                setattr(perm, field, bool(request.form.get(f"{module.code}__{field}")))
        db.session.commit()
        write_log(current_user, "ADMIN", "UPDATE_PERMISSIONS", f"{user.username}")
        flash("İcazələr yeniləndi.", "success")
        return redirect(url_for("admin.permissions", user_id=user.id))

    perms_by_module = {p.module_id: p for p in user.permissions}
    return render_template(
        "admin/permissions.html",
        user=user, modules=modules, perms_by_module=perms_by_module,
        fields=PERMISSION_FIELDS,
    )


@admin_bp.route("/users/<int:user_id>/logs")
def view_logs(user_id):
    user = User.query.get_or_404(user_id)
    logs = (ActivityLog.query.filter_by(user_id=user.id)
            .order_by(ActivityLog.timestamp.desc()).limit(500).all())
    return render_template("admin/logs.html", user=user, logs=logs)


@admin_bp.route("/users/<int:user_id>/logs/download")
def download_log_file(user_id):
    user = User.query.get_or_404(user_id)
    path = get_user_log_file_path(user.username)
    if not os.path.exists(path):
        flash("Bu istifadəçi üçün hələ log faylı yoxdur.", "warning")
        return redirect(url_for("admin.view_logs", user_id=user.id))
    return send_file(path, as_attachment=True, download_name=f"{user.username}.log")
