"""
Generic, project-agnostic endpoints meant to be copy-paste reusable in future
projects built on this same skeleton:

  - Grid preferences (column order/visibility/titles/aggregates/grouping/
    sorting) persisted per user, per grid, in the database.
  - A generic "quick add" endpoint for any DictionaryItem category, used by
    the small "+" button next to every dictionary-backed dropdown.
  - Error reporting: captures a screenshot + context and emails/logs it for
    the developer.

None of this file's logic is specific to HR/Tabel/Salary — it only knows
about `current_user`, `DictionaryItem`, `GridPreference`, and `ErrorReport`.
"""

import base64
import json
import os
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app import db
from app.models import GridPreference, DictionaryItem, ErrorReport

core_bp = Blueprint("core", __name__)


# ---------------------------------------------------------------------------
# Grid preferences (database-backed, replaces localStorage)
# ---------------------------------------------------------------------------

@core_bp.route("/grid-prefs/<grid_key>", methods=["GET"])
@login_required
def get_grid_prefs(grid_key):
    pref = GridPreference.query.filter_by(user_id=current_user.id, grid_key=grid_key).first()
    settings = json.loads(pref.settings_json) if pref else {}
    return jsonify({"settings": settings})


@core_bp.route("/grid-prefs/<grid_key>", methods=["POST"])
@login_required
def save_grid_prefs(grid_key):
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings", {})
    pref = GridPreference.query.filter_by(user_id=current_user.id, grid_key=grid_key).first()
    if not pref:
        pref = GridPreference(user_id=current_user.id, grid_key=grid_key)
        db.session.add(pref)
    pref.settings_json = json.dumps(settings)
    pref.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Generic dictionary "quick add" — used by the "+" button next to any
# dictionary-backed <select> so the person never has to leave the form.
# ---------------------------------------------------------------------------

@core_bp.route("/dictionary-quick-add", methods=["POST"])
@login_required
def dictionary_quick_add():
    payload = request.get_json(silent=True) or {}
    module_code = (payload.get("module_code") or "").upper().strip()
    category = (payload.get("category") or "").strip()
    name = (payload.get("name") or "").strip()
    value = (payload.get("value") or "").strip()

    if not module_code or not category or not name:
        return jsonify({"success": False, "error": "module_code, category və name mütləqdir."}), 400

    if not current_user.has_perm(module_code, "dict_add"):
        return jsonify({"success": False, "error": "Bu kitabçaya əlavə etmək icazəniz yoxdur."}), 403

    existing = DictionaryItem.query.filter_by(
        module_code=module_code, category=category, name=name
    ).first()
    if existing:
        return jsonify({"success": True, "item": {"id": existing.id, "name": existing.name}})

    item = DictionaryItem(module_code=module_code, category=category, name=name,
                           value=value, is_active=True)
    db.session.add(item)
    db.session.commit()
    return jsonify({"success": True, "item": {"id": item.id, "name": item.name}})


# ---------------------------------------------------------------------------
# Error reporting: screenshot + full context, emailed to the developer
# ---------------------------------------------------------------------------

def _send_email_with_screenshot(subject, body_text, screenshot_path):
    cfg = current_app.config
    if not cfg.get("MAIL_SERVER") or not cfg.get("DEVELOPER_EMAIL"):
        return False  # not configured — the report is still saved to the DB/disk

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = cfg.get("MAIL_FROM", cfg.get("MAIL_USERNAME", "noreply@localhost"))
    msg["To"] = cfg["DEVELOPER_EMAIL"]
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    if screenshot_path and os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(screenshot_path))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(screenshot_path)}"'
        msg.attach(part)

    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg.get("MAIL_PORT", 587)) as server:
            if cfg.get("MAIL_USE_TLS", True):
                server.starttls()
            if cfg.get("MAIL_USERNAME"):
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.sendmail(msg["From"], [msg["To"]], msg.as_string())
        return True
    except Exception:
        current_app.logger.exception("Failed to send error-report email")
        return False


@core_bp.route("/report-error", methods=["POST"])
@login_required
def report_error():
    payload = request.get_json(silent=True) or {}
    message = payload.get("message", "")
    stack = payload.get("stack", "")
    url = payload.get("url", "")
    last_action = payload.get("lastAction", "")
    screenshot_b64 = payload.get("screenshot", "")

    screenshot_dir = os.path.join(current_app.config["LOG_DIR"], "error_screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    screenshot_path = None
    if screenshot_b64 and screenshot_b64.startswith("data:image"):
        try:
            header, b64data = screenshot_b64.split(",", 1)
            filename = f"error_{current_user.username}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
            screenshot_path = os.path.join(screenshot_dir, filename)
            with open(screenshot_path, "wb") as f:
                f.write(base64.b64decode(b64data))
        except Exception:
            current_app.logger.exception("Failed to save error screenshot")
            screenshot_path = None

    report = ErrorReport(
        user_id=current_user.id,
        username=current_user.username,
        url=url,
        message=message,
        stack=stack,
        last_action=last_action,
        screenshot_path=screenshot_path,
    )
    db.session.add(report)
    db.session.commit()

    body = (
        f"Tarix: {datetime.utcnow().isoformat(timespec='seconds')} UTC\n"
        f"İstifadəçi: {current_user.username} ({current_user.full_name})\n"
        f"Səhifə: {url}\n"
        f"Son əməliyyat: {last_action}\n\n"
        f"Xəta mesajı:\n{message}\n\n"
        f"Stack trace:\n{stack}\n"
    )
    sent = _send_email_with_screenshot(
        subject=f"[HR System] Xəta hesabatı — {current_user.username}",
        body_text=body,
        screenshot_path=screenshot_path,
    )
    report.email_sent = sent
    db.session.commit()

    return jsonify({"success": True, "email_sent": sent})
