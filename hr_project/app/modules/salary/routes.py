from flask import Blueprint, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime

from app import db
from app.models import SalaryEntry, Employee, TabelEmployeeRow
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

from app.models import TabelPeriod, PayrollRun, PayrollEntry, SalaryAddition, Order, DictionaryItem
from app.services import payroll_service
from app.utils.parsing import _parse_decimal


@salary_bp.route("/payroll")
@login_required
@permission_required(MODULE, "can_view")
def list_payroll_periods():
    from flask import render_template
    from datetime import date as _date

    year = _parse_int(request.args.get("year"))
    month = _parse_int(request.args.get("month"))
    if not year or not month:
        latest = TabelPeriod.query.order_by(
            TabelPeriod.year.desc(), TabelPeriod.month.desc()
        ).first()
        today = _date.today()
        year = year or (latest.year if latest else today.year)
        month = month or (latest.month if latest else today.month)

    period = TabelPeriod.query.filter_by(year=year, month=month).first()
    run = PayrollRun.query.filter_by(period_id=period.id).first() if period else None

    return render_template(
        "salary/payroll_periods.html",
        year=year, month=month, period=period, run=run,
        month_names=TabelPeriod.MONTH_NAMES_AZ,
        # Bu bayraqları burada (Python-da) hesablayıb ötürürük, çünki
        # Jinja-da {% set %} ilə `content` blokunda təyin olunan dəyişən
        # `extra_scripts` bloku üçün GÖRÜNMÜR (hər `{% block %}` Jinja-da
        # ayrı skop-dur) — bu, "grid görünmür" bug-ının əsl səbəbi idi:
        # şablonda tabel_exists həmişə "false" kimi render olunurdu.
        tabel_exists=period is not None,
        tabel_approved=period is not None and period.is_approved,
        payroll_calculated=run is not None,
        payroll_approved=run is not None and run.is_finalized,
    )


@salary_bp.route("/payroll/<int:period_id>/generate", methods=["POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "GENERATE_PAYROLL")
def generate_payroll(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    redirect_target = redirect(url_for("salary.list_payroll_periods", year=period.year, month=period.month))
    if not period.is_approved:
        flash("Əməkhaqqı yalnız təsdiq olunmuş dövr üçün hesablana bilər.", "danger")
        return redirect_target
    if not period.rows:
        flash("Bu dövr üçün tabel generasiya olunmayıb.", "danger")
        return redirect_target
    existing_run = PayrollRun.query.filter_by(period_id=period.id).first()
    if existing_run and existing_run.is_finalized:
        flash("Bu dövrün əməkhaqqısı artıq təsdiqlənib, yenidən hesablana bilməz.", "danger")
        return redirect_target
    payroll_service.generate_or_refresh_payroll(period)
    db.session.commit()
    flash("Əməkhaqqı hesablandı.", "success")
    return redirect_target


@salary_bp.route("/payroll/<int:period_id>/approve", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "APPROVE_PAYROLL")
def approve_payroll(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    redirect_target = redirect(url_for("salary.list_payroll_periods", year=period.year, month=period.month))
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if not run:
        flash("Bu dövr üçün əməkhaqqı hesablanmayıb.", "danger")
        return redirect_target
    if run.is_finalized:
        flash("Əməkhaqqı artıq təsdiqlənib.", "info")
        return redirect_target
    run.is_finalized = True
    run.finalized_at = datetime.utcnow()
    db.session.commit()
    flash("Əməkhaqqı təsdiqləndi.", "success")
    return redirect_target


@salary_bp.route("/payroll/<int:period_id>/unapprove", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "UNAPPROVE_PAYROLL")
def unapprove_payroll(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    redirect_target = redirect(url_for("salary.list_payroll_periods", year=period.year, month=period.month))
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if not run or not run.is_finalized:
        flash("Bu dövrün əməkhaqqısı təsdiqlənməyib.", "info")
        return redirect_target
    run.is_finalized = False
    run.finalized_at = None
    db.session.commit()
    flash("Əməkhaqqı təsdiqi ləğv edildi.", "success")
    return redirect_target


@salary_bp.route("/payroll/<int:period_id>/reset", methods=["POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "RESET_PAYROLL")
def reset_payroll(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    redirect_target = redirect(url_for("salary.list_payroll_periods", year=period.year, month=period.month))
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if not run:
        flash("Bu dövr üçün hesablanmış əməkhaqqı yoxdur.", "info")
        return redirect_target
    if run.is_finalized:
        flash("Təsdiqlənmiş əməkhaqqı sıfırlana bilməz — əvvəlcə təsdiqi ləğv edin.", "danger")
        return redirect_target
    db.session.delete(run)
    db.session.commit()
    flash("Əməkhaqqı sıfırlandı.", "success")
    return redirect_target


@salary_bp.route("/payroll/<int:period_id>/api/entries")
@login_required
@permission_required(MODULE, "can_view")
def api_payroll_entries(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    entries_by_employee = {e.employee_id: e for e in run.entries} if run else {}

    rows = (
        TabelEmployeeRow.query.filter_by(period_id=period.id)
        .order_by(TabelEmployeeRow.row_no)
        .all()
    )
    data = []
    for r in rows:
        e = entries_by_employee.get(r.employee_id)
        data.append({
            "entry_id": e.id if e else None,
            "row_no": r.row_no,
            "employee": r.full_name_snapshot,
            "contract_number": r.contract_number_snapshot,
            "position": r.position_snapshot,
            "monthly_salary": float(e.monthly_salary or 0) if e else 0,
            "norm_days": e.norm_days if e else 0,
            "worked_days": e.worked_days if e else 0,
            "base_amount": float(e.base_amount or 0) if e else 0,
            "vacation_pay": float(e.vacation_pay or 0) if e else 0,
            "sick_pay": float(e.sick_pay or 0) if e else 0,
            "additions_total": float(e.additions_total or 0) if e else 0,
            "deductions_total": float(e.deductions_total or 0) if e else 0,
            "gross_total": float(e.gross_total or 0) if e else 0,
            "income_tax": float(e.income_tax or 0) if e else 0,
            "dsmf_amount": float(e.dsmf_amount or 0) if e else 0,
            "unemployment_amount": float(e.unemployment_amount or 0) if e else 0,
            "medical_amount": float(e.medical_amount or 0) if e else 0,
            "net_total": float(e.net_total or 0) if e else 0,
            "note": e.note if e else None,
        })
    return jsonify(data)


# =============================================================================
# Əməkhaqqı əlavələri/tutulmaları (SalaryAddition) — KONKRET əməkdaş üçün.
# Ayrıca ümumi "Əlavələr" menyusu YOXDUR: bu pəncərə YALNIZ payroll
# siyahısında bir əməkdaşın sətrini "Dəyiş" edərkən açılır (bax:
# payroll_period.html editUrlTemplate -> /salary/payroll/entry/<id>/additions).
# =============================================================================


@salary_bp.route("/payroll/entry/<int:entry_id>/additions")
@login_required
@permission_required(MODULE, "can_view")
def employee_additions(entry_id):
    from flask import render_template
    entry = PayrollEntry.query.get_or_404(entry_id)
    return render_template("salary/employee_additions.html", entry=entry)


@salary_bp.route("/payroll/entry/<int:entry_id>/additions/api")
@login_required
@permission_required(MODULE, "can_view")
def api_employee_additions(entry_id):
    entry = PayrollEntry.query.get_or_404(entry_id)
    items = (
        SalaryAddition.query.filter(
            db.or_(
                SalaryAddition.employees.any(id=entry.employee_id),
                SalaryAddition.scope == "all",
            )
        )
        .order_by(SalaryAddition.valid_from.desc())
        .all()
    )
    data = [{
        "id": a.id,
        "type_name": a.type_name(),
        "kind": "Tutulma" if a.is_deduction() else "Əlavə",
        "amount_type": a.amount_type_label(),
        "amount": float(a.amount) if a.amount_type == "fixed" and a.amount else None,
        "percent": float(a.percent) if a.amount_type == "percent" and a.percent else None,
        "scope": a.scope_label(),
        "valid_from": a.valid_from.isoformat() if a.valid_from else "",
        "valid_to": a.valid_to.isoformat() if a.valid_to else "",
        "order": a.order.label() if a.order else "",
        "is_active": a.is_active,
        "note": a.note,
        "editable": a.scope == "individual",
    } for a in items]
    return jsonify(data)


def _apply_addition_form(addition, form, employee):
    from app.utils.parsing import _parse_date, _parse_int

    addition_type = DictionaryItem.query.get(_parse_int(form.get("addition_type_id")))
    addition.addition_type_id = addition_type.id if addition_type else None

    addition.amount_type = form.get("amount_type", "fixed")
    addition.amount = _parse_decimal(form.get("amount")) if addition.amount_type == "fixed" else None
    addition.percent = _parse_decimal(form.get("percent")) if addition.amount_type == "percent" else None

    addition.scope = "individual"
    addition.employees = [employee] if employee else []

    addition.valid_from = _parse_date(form.get("valid_from"))
    addition.valid_to = _parse_date(form.get("valid_to"))
    addition.order_id = _parse_int(form.get("order_id"))
    addition.note = form.get("note", "").strip()
    addition.is_active = bool(form.get("is_active"))
    return addition_type


def _validate_addition(addition, addition_type):
    if not addition_type:
        return "Əlavə/tutulma növü seçilməlidir."
    if not addition.valid_from:
        return "Qüvvəyə minmə tarixi mütləqdir."
    if addition.amount_type == "fixed" and not addition.amount:
        return "Sabit məbləğ daxil edilməlidir."
    if addition.amount_type == "percent" and not addition.percent:
        return "Faiz dəyəri daxil edilməlidir."
    return payroll_service.validate_addition_dates(addition.valid_from, addition.valid_to)


@salary_bp.route("/payroll/entry/<int:entry_id>/additions/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_ADDITION")
def add_addition(entry_id):
    entry = PayrollEntry.query.get_or_404(entry_id)
    if entry.payroll_run.is_finalized:
        flash("Bu dövrün əməkhaqqısı təsdiqlənib, əlavə/tutulma dəyişdirilə bilməz.", "danger")
        return redirect(url_for(
            "salary.list_payroll_periods",
            year=entry.payroll_run.period.year, month=entry.payroll_run.period.month,
        ))
    addition_types = DictionaryItem.query.filter_by(
        module_code="SALARY", category="salary_addition_type", is_active=True
    ).order_by(DictionaryItem.name).all()
    orders = Order.query.order_by(Order.order_date.desc()).all()
    if request.method == "POST":
        addition = SalaryAddition()
        addition_type = _apply_addition_form(addition, request.form, entry.employee)
        error = _validate_addition(addition, addition_type)
        if error:
            flash(error, "danger")
            return render_form(
                "salary/addition_form.html", addition=None, entry=entry,
                addition_types=addition_types, orders=orders,
            )
        db.session.add(addition)
        db.session.commit()
        payroll_service.recalculate_entry(entry)
        db.session.commit()
        flash("Əlavə/tutulma əlavə olundu.", "success")
        return modal_redirect("salary.employee_additions", entry_id=entry.id)
    return render_form(
        "salary/addition_form.html", addition=None, entry=entry,
        addition_types=addition_types, orders=orders,
    )


@salary_bp.route("/additions/edit/<int:addition_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_ADDITION")
def edit_addition(addition_id):
    addition = SalaryAddition.query.get_or_404(addition_id)
    if addition.scope != "individual":
        flash("Bütün əməkdaşlara aid əlavə/tutulmalar bu pəncərədən redaktə oluna bilməz.", "danger")
        return redirect(url_for("salary.list_payroll_periods"))
    # Hansı PayrollEntry-dən (əməkdaşdan) açıldığını tapaq ki, Save/Cancel
    # düzgün pəncərəyə qayıtsın.
    employee = addition.employees[0] if addition.employees else None
    entry = (
        PayrollEntry.query.filter_by(employee_id=employee.id).first()
        if employee else None
    )
    addition_types = DictionaryItem.query.filter_by(
        module_code="SALARY", category="salary_addition_type", is_active=True
    ).order_by(DictionaryItem.name).all()
    orders = Order.query.order_by(Order.order_date.desc()).all()
    if request.method == "POST":
        addition_type = _apply_addition_form(addition, request.form, employee)
        error = _validate_addition(addition, addition_type)
        if error:
            flash(error, "danger")
            return render_form(
                "salary/addition_form.html", addition=addition, entry=entry,
                addition_types=addition_types, orders=orders,
            )
        db.session.commit()
        for e in PayrollEntry.query.filter_by(employee_id=employee.id).all() if employee else []:
            payroll_service.recalculate_entry(e)
        db.session.commit()
        flash("Əlavə/tutulma yeniləndi.", "success")
        return modal_redirect(
            "salary.employee_additions", entry_id=entry.id if entry else 0
        )
    return render_form(
        "salary/addition_form.html", addition=addition, entry=entry,
        addition_types=addition_types, orders=orders,
    )


@salary_bp.route("/additions/delete/<int:addition_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_ADDITION")
def delete_addition(addition_id):
    addition = SalaryAddition.query.get_or_404(addition_id)
    if addition.scope != "individual":
        message = "Bütün əməkdaşlara aid əlavə/tutulmalar bu pəncərədən silinə bilməz."
        if is_modal_request():
            return jsonify({"success": False, "error": message})
        flash(message, "danger")
        return redirect(url_for("salary.list_payroll_periods"))
    employee_id = addition.employees[0].id if addition.employees else None
    db.session.delete(addition)
    db.session.commit()
    if employee_id:
        for e in PayrollEntry.query.filter_by(employee_id=employee_id).all():
            payroll_service.recalculate_entry(e)
        db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Əlavə/tutulma silindi.", "info")
    return redirect(url_for("salary.list_payroll_periods"))
