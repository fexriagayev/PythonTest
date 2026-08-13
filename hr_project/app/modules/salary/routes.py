from flask import Blueprint, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from app import db
from app.models import SalaryEntry, Employee
from app.utils.decorators import permission_required, log_action
from app.utils.modal import render_form, modal_redirect, is_modal_request
from app.utils.parsing import _parse_int

salary_bp = Blueprint("salary", __name__)
MODULE = "SALARY"


@salary_bp.route("/")
@login_required
@permission_required(MODULE, "can_view")
def list_entries():
    from flask import render_template
    return render_template("salary/list.html")


@salary_bp.route("/api/entries")
@login_required
@permission_required(MODULE, "can_view")
def api_entries():
    entries = SalaryEntry.query.all()
    data = [{
        "id": e.id,
        "employee": e.employee.full_name() if e.employee else "",
        "employee_id": e.employee_id,
        "period": e.period,
        "base_salary": float(e.base_salary or 0),
        "bonus": float(e.bonus or 0),
        "deductions": float(e.deductions or 0),
        "total": float(e.total or 0),
        "note": e.note,
    } for e in entries]
    return jsonify(data)


def _parse_amount(value):
    try:
        if value is None or str(value).strip() == "":
            return 0.0
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _valid_period(value):
    import re
    return bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", (value or "").strip()))


def _calc_total(base, bonus, deductions):
    return float(base or 0) + float(bonus or 0) - float(deductions or 0)


@salary_bp.route("/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD")
def add_entry():
    employees = Employee.query.filter_by(is_active=True).all()
    if request.method == "POST":
        employee_id = _parse_int(request.form.get("employee_id"))
        period = request.form.get("period", "").strip()
        base = _parse_amount(request.form.get("base_salary"))
        bonus = _parse_amount(request.form.get("bonus"))
        deductions = _parse_amount(request.form.get("deductions"))
        employee = Employee.query.get(employee_id) if employee_id else None
        error = None
        if not employee_id or not employee:
            error = "Əməkdaş mütləq seçilməlidir."
        elif not _valid_period(period):
            error = "Dövr YYYY-MM formatında olmalıdır."
        elif None in (base, bonus, deductions):
            error = "Maaş, bonus və tutulmalar düzgün rəqəm olmalıdır."
        elif deductions < 0:
            error = "Tutulma mənfi ola bilməz."
        elif deductions < 0:
            error = "Tutulma mənfi ola bilməz."
        elif SalaryEntry.query.filter_by(employee_id=employee_id, period=period).first():
            error = "Bu əməkdaş üçün həmin dövr üzrə maaş artıq mövcuddur."
        if error:
            flash(error, "danger")
            return render_form("salary/form.html", entry=None, employees=employees)
        entry = SalaryEntry(
            employee_id=employee_id,
            period=period,
            base_salary=base,
            bonus=bonus,
            deductions=deductions,
            total=_calc_total(base, bonus, deductions),
            note=request.form.get("note", "").strip(),
        )
        db.session.add(entry)
        db.session.commit()
        flash("Əməkhaqqı qeydi əlavə olundu.", "success")
        return modal_redirect("salary.list_entries")
    return render_form("salary/form.html", entry=None, employees=employees)


@salary_bp.route("/edit/<int:entry_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT")
def edit_entry(entry_id):
    entry = SalaryEntry.query.get_or_404(entry_id)
    employees = Employee.query.filter_by(is_active=True).all()
    if request.method == "POST":
        employee_id = _parse_int(request.form.get("employee_id"))
        period = request.form.get("period", "").strip()
        base = _parse_amount(request.form.get("base_salary"))
        bonus = _parse_amount(request.form.get("bonus"))
        deductions = _parse_amount(request.form.get("deductions"))
        employee = Employee.query.get(employee_id) if employee_id else None
        error = None
        if not employee_id or not employee:
            error = "Əməkdaş mütləq seçilməlidir."
        elif not _valid_period(period):
            error = "Dövr YYYY-MM formatında olmalıdır."
        elif None in (base, bonus, deductions):
            error = "Maaş, bonus və tutulmalar düzgün rəqəm olmalıdır."
        elif deductions < 0:
            error = "Tutulma mənfi ola bilməz."
        elif deductions < 0:
            error = "Tutulma mənfi ola bilməz."
        elif SalaryEntry.query.filter_by(employee_id=employee_id, period=period).first():
            error = "Bu əməkdaş üçün həmin dövr üzrə maaş artıq mövcuddur."
        if error:
            flash(error, "danger")
            return render_form("salary/form.html", entry=entry, employees=employees)
        entry.employee_id = employee_id
        entry.period = period
        entry.base_salary = base
        entry.bonus = bonus
        entry.deductions = deductions
        if SalaryEntry.query.filter(SalaryEntry.employee_id==employee_id, SalaryEntry.period==period, SalaryEntry.id!=entry.id).first():
            flash("Bu əməkdaş üçün həmin dövr üzrə maaş artıq mövcuddur.","danger")
            return render_form("salary/form.html", entry=entry, employees=employees)
        entry.total = _calc_total(base, bonus, deductions)
        entry.note = request.form.get("note", "").strip()
        db.session.commit()
        flash("Əməkhaqqı qeydi yeniləndi.", "success")
        return modal_redirect("salary.list_entries")
    return render_form("salary/form.html", entry=entry, employees=employees)


@salary_bp.route("/delete/<int:entry_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE")
def delete_entry(entry_id):
    entry = SalaryEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Əməkhaqqı qeydi silindi.", "info")
    return redirect(url_for("salary.list_entries"))
