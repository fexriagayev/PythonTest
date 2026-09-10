from flask import Blueprint, render_template, Response
from flask_login import login_required, current_user
import csv
import io

from app.models import Employee, TabelEmployeeRow, PayrollEntry
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
        header = ["ID", "Ad Soyad Ata adı", "Şöbə", "Vəzifə", "İşə qəbul tarixi", "Aktiv"]
        rows = [[e.id, e.full_name, e.department, e.position,
                  e.hire_date, e.is_active] for e in Employee.query.all()]
    elif module_code == "TABEL":
        header = ["ID", "Dövr", "Əməkdaş", "M/n", "Vəzifə", "İş günlərinin sayı"]
        rows = [[r.id, r.period.label if r.period else "", r.full_name_snapshot,
                  r.contract_number_snapshot, r.position_snapshot, r.work_days_count()]
                 for r in TabelEmployeeRow.query.all()]
    elif module_code == "SALARY":
        header = ["ID", "Dövr", "Əməkdaş", "Baza", "Əlavələr", "Tutulmalar", "Gross", "Net"]
        rows = [[e.id, e.payroll_run.period.label if e.payroll_run and e.payroll_run.period else "",
                  e.full_name_snapshot, e.base_amount, e.additions_total, e.deductions_total,
                  e.gross_total, e.net_total] for e in PayrollEntry.query.all()]
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
