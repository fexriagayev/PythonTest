from datetime import date, timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Employee, TabelEntry, SalaryEntry, ActivityLog, InsurancePolicy, SalaryCard

dashboard_bp = Blueprint("dashboard", __name__)


def get_notifications():
    """
    Dashboard notification list — currently covers:
      - Sığorta müddəti bitmiş / bitməsinə 1 aydan az qalmış sığortalar
      - Etibarlılıq müddəti bitmiş / bitməsinə 1 aydan az qalmış maaş kartları
    Each item is {level: 'danger'|'warning'|'info', message: str}.
    """
    notifications = []
    today = date.today()
    soon = today + timedelta(days=30)

    expired_policies = (InsurancePolicy.query.join(Employee)
                         .filter(InsurancePolicy.end_date < today, Employee.is_active.is_(True)).all())
    for p in expired_policies:
        notifications.append({
            "level": "danger",
            "message": f"{p.employee.full_name} — sığorta müddəti bitib ({p.end_date})",
        })

    expiring_policies = (InsurancePolicy.query.join(Employee)
                          .filter(InsurancePolicy.end_date >= today, InsurancePolicy.end_date <= soon,
                                  Employee.is_active.is_(True)).all())
    for p in expiring_policies:
        notifications.append({
            "level": "warning",
            "message": f"{p.employee.full_name} — sığorta müddəti bitməsinə az qalıb ({p.end_date})",
        })

    expired_cards = (SalaryCard.query.join(Employee)
                      .filter(SalaryCard.valid_until.isnot(None), SalaryCard.valid_until < today,
                              Employee.is_active.is_(True)).all())
    for c in expired_cards:
        notifications.append({
            "level": "danger",
            "message": f"{c.employee.full_name} — maaş kartının etibarlılıq müddəti bitib ({c.valid_until})",
        })

    expiring_cards = (SalaryCard.query.join(Employee)
                       .filter(SalaryCard.valid_until.isnot(None),
                               SalaryCard.valid_until >= today, SalaryCard.valid_until <= soon,
                               Employee.is_active.is_(True)).all())
    for c in expiring_cards:
        notifications.append({
            "level": "warning",
            "message": f"{c.employee.full_name} — maaş kartının etibarlılıq müddəti bitməsinə az qalıb ({c.valid_until})",
        })

    return notifications


@dashboard_bp.route("/")
@login_required
def index():
    stats = {
        "employees": Employee.query.filter_by(is_active=True).count(),
        "tabel_entries": TabelEntry.query.count(),
        "salary_entries": SalaryEntry.query.count(),
    }
    recent_logs = []
    if current_user.is_admin:
        recent_logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(10).all()

    return render_template("dashboard.html", stats=stats, recent_logs=recent_logs,
                            notifications=get_notifications())
