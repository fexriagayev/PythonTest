from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user

from app.models import User
from app.utils.logger import write_log

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("İstifadəçi adı və ya parol yanlışdır.", "danger")
            return render_template("auth/login.html")

        if user.is_blocked:
            flash("Bu hesab bloklanıb. Admin ilə əlaqə saxlayın.", "danger")
            return render_template("auth/login.html")

        login_user(user)
        session["language"] = user.language or "az"
        write_log(user, "AUTH", "LOGIN", "İstifadəçi sistemə daxil oldu")
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    write_log(current_user, "AUTH", "LOGOUT", "İstifadəçi sistemdən çıxdı")
    logout_user()
    return redirect(url_for("auth.login"))
