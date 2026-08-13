import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # PostgreSQL connection. Set DATABASE_URL env var in production, e.g.:
    # postgresql+psycopg2://hr_user:hr_pass@localhost:5432/hr_db
    # Falls back to local SQLite so the project can be test-run without a
    # Postgres server installed.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LOG_DIR = os.path.join(basedir, "logs")
    UPLOAD_DIR = os.path.join(basedir, "uploads")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB per request (photos/documents)

    DEFAULT_PASSWORD = "test"

    # --- Error-report emailing (Tools -> error popup -> "Developerə göndər") ---
    # Leave MAIL_SERVER unset to disable emailing; reports are still saved to
    # the database and to LOG_DIR/error_screenshots either way.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    DEVELOPER_EMAIL = os.environ.get("DEVELOPER_EMAIL", "")

    LANGUAGES = ["az", "en"]
    DEFAULT_LANGUAGE = "az"
    DEFAULT_FONT_SIZE = 14

    # UI is built with Bootstrap + Bootswatch (fully free, MIT licensed,
    # no revenue/team-size restrictions) instead of the commercial
    # DevExpress/DevExtreme suite. Tables use Tabulator.js (also MIT/free)
    # which natively supports column filtering, sorting, global search,
    # grouping with per-group footer totals, and table-wide totals.
    DEFAULT_THEME = "cosmo"

    # Available Bootswatch themes the user can pick from in Tools > Style
    AVAILABLE_THEMES = [
        ("cosmo", "Cosmo (açıq)"),
        ("flatly", "Flatly (açıq)"),
        ("cerulean", "Cerulean (açıq)"),
        ("journal", "Journal (açıq)"),
        ("sandstone", "Sandstone (açıq)"),
        ("darkly", "Darkly (tünd)"),
        ("slate", "Slate (tünd)"),
        ("solar", "Solar (tünd)"),
    ]
