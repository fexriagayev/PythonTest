import os
from flask import Flask, session, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """SQLite disables FK enforcement by default; keep it aligned with PostgreSQL."""
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_app(config_class="config.Config"):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)

    os.makedirs(app.config["LOG_DIR"], exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Zəhmət olmasa daxil olun."
    login_manager.login_message_category = "warning"

    @app.before_request
    def enforce_password_change():
        from flask_login import current_user
        if (
            current_user.is_authenticated
            and getattr(current_user, "must_change_password", False)
            and request.endpoint
            and not request.endpoint.startswith("tools.change_password")
            and not request.endpoint.startswith("auth.logout")
            and not request.endpoint.startswith("static")
        ):
            from flask import redirect, url_for
            return redirect(url_for("tools.change_password"))

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error):
        db.session.rollback()
        message = "Əməliyyat verilənlər bazasının bütövlük qaydalarına görə yerinə yetirilə bilmədi."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "error": message}), 409
        from flask import redirect, url_for, flash
        flash(message, "danger")
        return redirect(request.referrer or url_for("dashboard.index"))

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        message = "Təhlükəsizlik yoxlaması uğursuz oldu. Səhifəni yeniləyin və əməliyyatı yenidən göndərin."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "error": message}), 400
        from flask import redirect, url_for, flash
        flash(message, "danger")
        return redirect(request.referrer or url_for("auth.login"))

    @login_manager.unauthorized_handler
    def unauthorized():
        # AJAX/fetch requests (modal forms, grid preferences, quick-add,
        # error reports, etc.) must never be silently redirected to the
        # login page's HTML — the caller expects JSON and would otherwise
        # fail confusingly (e.g. grid settings silently not saving because
        # the session expired and the POST got redirected to an HTML page).
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            from flask import jsonify
            return jsonify({"success": False, "error": "Sessiya bitib. Səhifəni yeniləyin və yenidən daxil olun."}), 401
        from flask import redirect, url_for
        return redirect(url_for("auth.login"))

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints -----------------------------------------------
    from app.modules.auth.routes import auth_bp
    from app.modules.admin.routes import admin_bp
    from app.modules.hr.routes import hr_bp
    from app.modules.tabel.routes import tabel_bp
    from app.modules.salary.routes import salary_bp
    from app.modules.dictionaries.routes import dict_bp
    from app.modules.reports.routes import reports_bp
    from app.modules.tools.routes import tools_bp
    from app.modules.documents.routes import documents_bp
    from app.core.routes import core_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(hr_bp, url_prefix="/hr")
    app.register_blueprint(tabel_bp, url_prefix="/tabel")
    app.register_blueprint(salary_bp, url_prefix="/salary")
    app.register_blueprint(dict_bp, url_prefix="/dictionaries")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(tools_bp, url_prefix="/tools")
    app.register_blueprint(documents_bp, url_prefix="/documents")
    app.register_blueprint(core_bp, url_prefix="/core")

    from app.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    # Make current_user preferences (theme/font/lang) available everywhere
    from app.i18n import translate, TRANSLATIONS

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        theme = app.config["DEFAULT_THEME"]
        font_size = app.config["DEFAULT_FONT_SIZE"]
        lang = session.get("language", app.config["DEFAULT_LANGUAGE"])
        if current_user.is_authenticated:
            theme = current_user.theme or theme
            font_size = current_user.font_size or font_size
            lang = current_user.language or lang
        return dict(
            ui_theme=theme,
            ui_font_size=font_size,
            ui_lang=lang,
            t=lambda key: translate(key, lang),
            # Flat {key: translated_text} for the current language, so
            # client-side JS (modal.js, app.js, ...) can call the same
            # t(key) translations as the server-rendered templates,
            # instead of hardcoding its own copy of the same strings.
            ui_i18n_json={key: translate(key, lang) for key in TRANSLATIONS},
            available_themes=app.config["AVAILABLE_THEMES"],
        )

    @app.before_request
    def check_blocked_user():
        from flask_login import current_user, logout_user
        from flask import redirect, url_for, flash
        if current_user.is_authenticated and current_user.is_blocked:
            logout_user()
            flash("Hesabınız bloklanıb. Admin ilə əlaqə saxlayın.", "danger")
            return redirect(url_for("auth.login"))

    return app
