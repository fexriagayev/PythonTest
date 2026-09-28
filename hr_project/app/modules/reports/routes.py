from flask import Blueprint, render_template, Response
from flask_login import login_required, current_user
import csv
import io

from app.models import Employee, TabelEmployeeRow, PayrollEntry
from app.utils.contract_sort import contract_sort_key, sort_employees_by_contract, contract_numbers_by_employee
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
        header = ["ID", "Müqavilə N", "Ad Soyad Ata adı", "Şöbə", "Vəzifə", "İşə qəbul tarixi", "Aktiv"]
        employees = sort_employees_by_contract(Employee.query.all())
        numbers = contract_numbers_by_employee([e.id for e in employees])
        rows = [[e.id, numbers.get(e.id), e.full_name, e.department, e.position,
                  e.hire_date, e.is_active] for e in employees]
    elif module_code == "TABEL":
        header = ["ID", "Dövr", "Əməkdaş", "M/n", "Vəzifə", "İş günlərinin sayı"]
        # Dövr üzrə qruplaşdırılır (yeni -> köhnə), dövr daxilində Müqavilə N-ə (ƏDƏD kimi) görə.
        tabel_rows = sorted(
            TabelEmployeeRow.query.all(),
            key=lambda r: (
                -(r.period.year * 100 + r.period.month) if r.period else 0,
                contract_sort_key(r.contract_number_snapshot),
                (r.full_name_snapshot or "").casefold(),
            ),
        )
        rows = [[r.id, r.period.label if r.period else "", r.full_name_snapshot,
                  r.contract_number_snapshot, r.position_snapshot, r.work_days_count()]
                 for r in tabel_rows]
    elif module_code == "SALARY":
        header = ["ID", "Dövr", "Müqavilə N", "Əməkdaş", "Baza", "Əlavə əməkhaqqı", "Mükafat", "Tutulmalar", "Gross", "Net"]
        # Dövr üzrə (yeni -> köhnə), dövr daxilində Müqavilə N-ə (ƏDƏD kimi) görə.
        entries = PayrollEntry.query.all()
        tabel_contract = {}
        for e in entries:
            per = e.payroll_run.period if e.payroll_run else None
            if per and per.id not in tabel_contract:
                tabel_contract[per.id] = {
                    r.employee_id: r.contract_number_snapshot
                    for r in TabelEmployeeRow.query.filter_by(period_id=per.id).all()
                }

        def _entry_contract(e):
            per = e.payroll_run.period if e.payroll_run else None
            return tabel_contract.get(per.id, {}).get(e.employee_id) if per else None

        entries.sort(key=lambda e: (
            -(e.payroll_run.period.year * 100 + e.payroll_run.period.month)
            if e.payroll_run and e.payroll_run.period else 0,
            contract_sort_key(_entry_contract(e)),
            (e.full_name_snapshot or "").casefold(),
        ))
        rows = [[e.id, e.payroll_run.period.label if e.payroll_run and e.payroll_run.period else "",
                  _entry_contract(e), e.full_name_snapshot, e.base_amount, e.additional_salary,
                  e.bonus_total, e.deductions_total, e.gross_total, e.net_total] for e in entries]
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
