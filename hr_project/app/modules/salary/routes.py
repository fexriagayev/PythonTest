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
        "employee": e.employee.full_name if e.employee else "",
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


# =============================================================================
# Əməkhaqqı hesablanması (Payroll) — təsdiqlənmiş Tabel dövrləri üzrə
# =============================================================================

from app.models import TabelPeriod, PayrollRun, PayrollEntry, SalaryAddition, Order
from app.services import payroll_service
from app.utils.parsing import _parse_decimal


@salary_bp.route("/payroll")
@login_required
@permission_required(MODULE, "can_view")
def list_payroll_periods():
    from flask import render_template
    return render_template("salary/payroll_periods.html")


@salary_bp.route("/payroll/api/periods")
@login_required
@permission_required(MODULE, "can_view")
def api_payroll_periods():
    periods = (
        TabelPeriod.query.filter_by(is_approved=True)
        .order_by(TabelPeriod.year.desc(), TabelPeriod.month.desc())
        .all()
    )
    data = []
    for p in periods:
        run = PayrollRun.query.filter_by(period_id=p.id).first()
        net_total = (
            sum(float(e.net_total or 0) for e in run.entries) if run else None
        )
        data.append({
            "id": p.id,
            "period": p.label,
            "employee_count": len(p.rows),
            "is_calculated": run is not None,
            "net_total": net_total,
        })
    return jsonify(data)


@salary_bp.route("/payroll/<int:period_id>")
@login_required
@permission_required(MODULE, "can_view")
def payroll_period(period_id):
    from flask import render_template
    period = TabelPeriod.query.get_or_404(period_id)
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    return render_template("salary/payroll_period.html", period=period, run=run)


@salary_bp.route("/payroll/<int:period_id>/generate", methods=["POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "GENERATE_PAYROLL")
def generate_payroll(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    if not period.is_approved:
        flash("Əməkhaqqı yalnız təsdiq olunmuş dövr üçün hesablana bilər.", "danger")
        return redirect(url_for("salary.payroll_period", period_id=period.id))
    if not period.rows:
        flash("Bu dövr üçün tabel generasiya olunmayıb.", "danger")
        return redirect(url_for("salary.payroll_period", period_id=period.id))
    payroll_service.generate_or_refresh_payroll(period)
    db.session.commit()
    flash("Əməkhaqqı hesablandı.", "success")
    return redirect(url_for("salary.payroll_period", period_id=period.id))


@salary_bp.route("/payroll/<int:period_id>/api/entries")
@login_required
@permission_required(MODULE, "can_view")
def api_payroll_entries(period_id):
    run = PayrollRun.query.filter_by(period_id=period_id).first()
    if not run:
        return jsonify([])
    data = [{
        "id": e.id,
        "row_no": e.row_no,
        "employee": e.full_name_snapshot,
        "position": e.position_snapshot,
        "monthly_salary": float(e.monthly_salary or 0),
        "norm_days": e.norm_days,
        "worked_days": e.worked_days,
        "base_amount": float(e.base_amount or 0),
        "extra_amount": float(e.extra_amount or 0),
        "vacation_pay": float(e.vacation_pay or 0),
        "sick_pay": float(e.sick_pay or 0),
        "bonus": float(e.bonus or 0),
        "additions_total": float(e.additions_total or 0),
        "gross_total": float(e.gross_total or 0),
        "income_tax": float(e.income_tax or 0),
        "dsmf_amount": float(e.dsmf_amount or 0),
        "unemployment_amount": float(e.unemployment_amount or 0),
        "medical_amount": float(e.medical_amount or 0),
        "net_total": float(e.net_total or 0),
        "note": e.note,
    } for e in run.entries]
    return jsonify(data)


@salary_bp.route("/payroll/entry/edit/<int:entry_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_PAYROLL_ENTRY")
def edit_payroll_entry(entry_id):
    entry = PayrollEntry.query.get_or_404(entry_id)
    if request.method == "POST":
        extra = _parse_decimal(request.form.get("extra_amount"))
        bonus = _parse_decimal(request.form.get("bonus"))
        error = None
        if extra is None or bonus is None or extra < 0 or bonus < 0:
            error = "Əlavə əməkhaqqı və mükafat düzgün, mənfi olmayan rəqəm olmalıdır."
        if error:
            flash(error, "danger")
            return render_form("salary/payroll_entry_form.html", entry=entry)

        entry.extra_amount = extra
        entry.bonus = bonus
        entry.note = request.form.get("note", "").strip()
        # extra_amount/bonus dəyişdiyi üçün gross/net-i yenidən hesablayaq;
        # vacation_pay/sick_pay/additions öz mənbələrindən təzələnir.
        payroll_service.recalculate_entry(entry)
        db.session.commit()
        flash("Əməkhaqqı sətri yeniləndi.", "success")
        return modal_redirect("salary.payroll_period", period_id=entry.payroll_run.period_id)
    return render_form("salary/payroll_entry_form.html", entry=entry)


# =============================================================================
# Əlavələr (SalaryAddition)
# =============================================================================


@salary_bp.route("/additions")
@login_required
@permission_required(MODULE, "can_view")
def list_additions():
    from flask import render_template
    return render_template("salary/additions_list.html")


@salary_bp.route("/additions/api")
@login_required
@permission_required(MODULE, "can_view")
def api_additions():
    items = SalaryAddition.query.order_by(SalaryAddition.valid_from.desc()).all()
    data = [{
        "id": a.id,
        "name": a.name,
        "amount_type": a.amount_type_label(),
        "amount": float(a.amount) if a.amount_type == "fixed" and a.amount else None,
        "percent": float(a.percent) if a.amount_type == "percent" and a.percent else None,
        "scope": a.scope_label(),
        "employee_count": len(a.employees) if a.scope == "individual" else None,
        "valid_from": a.valid_from.isoformat() if a.valid_from else "",
        "valid_to": a.valid_to.isoformat() if a.valid_to else "",
        "order": a.order.label() if a.order else "",
        "is_active": a.is_active,
        "note": a.note,
    } for a in items]
    return jsonify(data)


def _addition_form_choices():
    return {
        "employees": Employee.query.filter_by(is_active=True).order_by(Employee.full_name).all(),
        "orders": Order.query.order_by(Order.order_date.desc()).all(),
    }


def _apply_addition_form(addition, form):
    from app.utils.parsing import _parse_date, _parse_int

    addition.name = form.get("name", "").strip()
    addition.amount_type = form.get("amount_type", "fixed")
    addition.amount = _parse_decimal(form.get("amount")) if addition.amount_type == "fixed" else None
    addition.percent = _parse_decimal(form.get("percent")) if addition.amount_type == "percent" else None
    addition.scope = form.get("scope", "all")
    addition.valid_from = _parse_date(form.get("valid_from"))
    addition.valid_to = _parse_date(form.get("valid_to"))
    addition.order_id = _parse_int(form.get("order_id"))
    addition.note = form.get("note", "").strip()
    addition.is_active = bool(form.get("is_active"))

    if addition.scope == "individual":
        ids = [int(v) for v in form.getlist("employee_ids") if v.strip().isdigit()]
        addition.employees = Employee.query.filter(Employee.id.in_(ids)).all() if ids else []
    else:
        addition.employees = []


@salary_bp.route("/additions/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_ADDITION")
def add_addition():
    if request.method == "POST":
        addition = SalaryAddition()
        _apply_addition_form(addition, request.form)
        error = None
        if not addition.name:
            error = "Əlavənin adı mütləqdir."
        elif not addition.valid_from:
            error = "Qüvvəyə minmə tarixi mütləqdir."
        elif addition.amount_type == "fixed" and not addition.amount:
            error = "Sabit məbləğ daxil edilməlidir."
        elif addition.amount_type == "percent" and not addition.percent:
            error = "Faiz dəyəri daxil edilməlidir."
        elif addition.scope == "individual" and not addition.employees:
            error = "Fərdi əlavə üçün ən azı bir əməkdaş seçilməlidir."
        if error:
            flash(error, "danger")
            return render_form("salary/addition_form.html", addition=None, **_addition_form_choices())
        db.session.add(addition)
        db.session.commit()
        flash("Əlavə əlavə olundu.", "success")
        return modal_redirect("salary.list_additions")
    return render_form("salary/addition_form.html", addition=None, **_addition_form_choices())


@salary_bp.route("/additions/edit/<int:addition_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_ADDITION")
def edit_addition(addition_id):
    addition = SalaryAddition.query.get_or_404(addition_id)
    if request.method == "POST":
        _apply_addition_form(addition, request.form)
        error = None
        if not addition.name:
            error = "Əlavənin adı mütləqdir."
        elif not addition.valid_from:
            error = "Qüvvəyə minmə tarixi mütləqdir."
        elif addition.amount_type == "fixed" and not addition.amount:
            error = "Sabit məbləğ daxil edilməlidir."
        elif addition.amount_type == "percent" and not addition.percent:
            error = "Faiz dəyəri daxil edilməlidir."
        elif addition.scope == "individual" and not addition.employees:
            error = "Fərdi əlavə üçün ən azı bir əməkdaş seçilməlidir."
        if error:
            flash(error, "danger")
            return render_form("salary/addition_form.html", addition=addition, **_addition_form_choices())
        db.session.commit()
        flash("Əlavə yeniləndi.", "success")
        return modal_redirect("salary.list_additions")
    return render_form("salary/addition_form.html", addition=addition, **_addition_form_choices())


@salary_bp.route("/additions/delete/<int:addition_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_ADDITION")
def delete_addition(addition_id):
    addition = SalaryAddition.query.get_or_404(addition_id)
    db.session.delete(addition)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Əlavə silindi.", "info")
    return redirect(url_for("salary.list_additions"))
