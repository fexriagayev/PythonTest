from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user

from app import db
from app.utils.logger import write_log

tools_bp = Blueprint("tools", __name__)


@tools_bp.route("/")
@login_required
def index():
    return render_template("tools/index.html")


@tools_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """'İstifadəçini dəyişmək' - edit the current user's own profile info."""
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.email = request.form.get("email", "").strip()
        db.session.commit()
        write_log(current_user, "TOOLS", "UPDATE_PROFILE", "Profil məlumatları yeniləndi")
        flash("Profil yeniləndi.", "success")
        return redirect(url_for("tools.profile"))
    return render_template("tools/profile.html")


@tools_bp.route("/style", methods=["GET", "POST"])
@login_required
def style():
    themes = current_app.config["AVAILABLE_THEMES"]
    if request.method == "POST":
        theme = request.form.get("theme")
        valid_codes = [c for c, _ in themes]
        if theme in valid_codes:
            current_user.theme = theme
            db.session.commit()
            write_log(current_user, "TOOLS", "CHANGE_STYLE", theme)
            flash("Proqramın stili dəyişdirildi.", "success")
        return redirect(url_for("tools.style"))
    return render_template("tools/style.html", themes=themes)


@tools_bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not current_user.check_password(current_pw):
            flash("Cari parol yanlışdır.", "danger")
        elif len(new_pw) < 4:
            flash("Yeni parol ən azı 4 simvol olmalıdır.", "danger")
        elif new_pw != confirm_pw:
            flash("Yeni parollar uyğun gəlmir.", "danger")
        else:
            current_user.set_password(new_pw)
            current_user.must_change_password = False
            db.session.commit()
            write_log(current_user, "TOOLS", "CHANGE_PASSWORD", "Parol dəyişdirildi")
            flash("Parolunuz uğurla dəyişdirildi.", "success")
            return redirect(url_for("tools.change_password"))
    return render_template("tools/password.html")


@tools_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        font_size = request.form.get("font_size", type=int)
        language = request.form.get("language")
        if font_size and 10 <= font_size <= 24:
            current_user.font_size = font_size
        if language in current_app.config["LANGUAGES"]:
            current_user.language = language
            session["language"] = language
        db.session.commit()
        write_log(current_user, "TOOLS", "CHANGE_SETTINGS",
                  f"font={font_size} lang={language}")
        flash("Tənzimləmələr yadda saxlanıldı.", "success")
        return redirect(url_for("tools.settings"))
    return render_template("tools/settings.html", languages=current_app.config["LANGUAGES"])
