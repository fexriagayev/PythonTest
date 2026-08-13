from flask import Blueprint, render_template, Response
from flask_login import login_required, current_user
import csv
import io

from app.models import Employee, TabelEntry, SalaryEntry
from app.utils.decorators import log_action

reports_bp = Blueprint("reports", __name__)

VALID_MODULES = ["HR", "TABEL", "SALARY"]


@reports_bp.route("/")
@login_required
def index():
    visible = [m for m in VALID_MODULES if current_user.has_perm(m, "can_report")]
    return render_template("reports/index.html", visible_modules=visible)


def _rows_for(module_code):
    if module_code == "HR":
        header = ["ID", "Ad", "Soyad", "Şöbə", "Vəzifə", "İşə qəbul tarixi", "Aktiv"]
        rows = [[e.id, e.first_name, e.last_name, e.department, e.position,
                  e.hire_date, e.is_active] for e in Employee.query.all()]
    elif module_code == "TABEL":
        header = ["ID", "Əməkdaş", "Tarix", "Saat", "Status", "Qeyd"]
        rows = [[t.id, t.employee.full_name() if t.employee else "", t.work_date,
                  t.hours_worked, t.status, t.note] for t in TabelEntry.query.all()]
    elif module_code == "SALARY":
        header = ["ID", "Əməkdaş", "Dövr", "Baza", "Bonus", "Tutulma", "Cəmi"]
        rows = [[s.id, s.employee.full_name() if s.employee else "", s.period,
                  s.base_salary, s.bonus, s.deductions, s.total] for s in SalaryEntry.query.all()]
    else:
        header, rows = [], []
    return header, rows


@reports_bp.route("/<module_code>")
@login_required
@log_action("REPORTS", "VIEW_REPORT")
def view_report(module_code):
    module_code = module_code.upper()
    if not current_user.has_perm(module_code, "can_report"):
        return "İcazə yoxdur", 403
    header, rows = _rows_for(module_code)
    return render_template("reports/report.html", module_code=module_code, header=header, rows=rows)


@reports_bp.route("/<module_code>/export.csv")
@login_required
@log_action("REPORTS", "EXPORT_REPORT")
def export_csv(module_code):
    module_code = module_code.upper()
    if not current_user.has_perm(module_code, "can_report"):
        return "İcazə yoxdur", 403
    header, rows = _rows_for(module_code)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={module_code.lower()}_report.csv"},
    )
