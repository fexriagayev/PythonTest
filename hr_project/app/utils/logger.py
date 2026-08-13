import os
from datetime import datetime
from flask import current_app, request
from app import db
from app.models import ActivityLog


def write_log(user, module, action, description=""):
    """
    Always records nothing unless the user's `log_flag` is turned on by the
    admin. When log_flag is True, the action is written BOTH to the
    activity_logs DB table (so the admin panel can query/filter it) and to a
    plain text file per user under LOG_DIR (so it can be downloaded as a raw
    log file). Turning the flag off immediately stops further writes.
    """
    if not user or not getattr(user, "log_flag", False):
        return

    ip = request.remote_addr if request else None

    entry = ActivityLog(
        user_id=user.id,
        username=user.username,
        module=module,
        action=action,
        description=description,
        ip_address=ip,
    )
    db.session.add(entry)
    db.session.commit()

    log_dir = current_app.config["LOG_DIR"]
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"{user.username}.log")
    line = (
        f"[{datetime.utcnow().isoformat(timespec='seconds')}] "
        f"module={module} action={action} ip={ip} :: {description}\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def get_user_log_file_path(username):
    log_dir = current_app.config["LOG_DIR"]
    return os.path.join(log_dir, f"{username}.log")
