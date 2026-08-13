from functools import wraps
from flask import abort, request
from flask_login import current_user

from app.utils.logger import write_log


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def permission_required(module_code, field):
    """
    Ensures current_user has the given permission flag (e.g. 'can_add',
    'can_edit', 'can_delete', 'can_view', 'can_report', 'dict_add', ...)
    on the given module (HR / TABEL / SALARY). Admins always pass.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if not current_user.has_perm(module_code, field):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def log_action(module_code, action):
    """Writes an activity-log entry (only if the user's log_flag is on)."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            result = view(*args, **kwargs)
            try:
                write_log(
                    current_user if current_user.is_authenticated else None,
                    module_code,
                    action,
                    description=f"{request.method} {request.path}",
                )
            except Exception:
                pass
            return result
        return wrapped
    return decorator
