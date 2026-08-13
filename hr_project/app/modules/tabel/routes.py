from flask import Blueprint, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from app import db
from app.models import TabelEntry, Employee
from app.utils.decorators import permission_required, log_action
from app.utils.modal import render_form, modal_redirect, is_modal_request
from app.utils.parsing import _parse_int, _parse_date, _parse_float

tabel_bp = Blueprint("tabel", __name__)
MODULE = "TABEL"


@tabel_bp.route("/")
@login_required
@permission_required(MODULE, "can_view")
def list_entries():
    from flask import render_template
    return render_template("tabel/list.html")


@tabel_bp.route("/api/entries")
@login_required
@permission_required(MODULE, "can_view")
def api_entries():
    entries = TabelEntry.query.all()
    data = [{
        "id": e.id,
        "employee": e.employee.full_name() if e.employee else "",
        "employee_id": e.employee_id,
        "work_date": e.work_date.isoformat() if e.work_date else None,
        "hours_worked": e.hours_worked,
        "status": e.status,
        "note": e.note,
    } for e in entries]
    return jsonify(data)


@tabel_bp.route("/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD")
def add_entry():
    employees = Employee.query.filter_by(is_active=True).all()
    if request.method == "POST":
        employee_id = _parse_int(request.form.get("employee_id"))
        work_date = _parse_date(request.form.get("work_date"))
        hours_worked = _parse_float(request.form.get("hours_worked") or 0)
        employee = Employee.query.get(employee_id) if employee_id else None
        error = None
        if not employee_id or not employee:
            error = "Əməkdaş mütləq seçilməlidir."
        elif not work_date:
            error = "İş tarixi mütləqdir və YYYY-MM-DD formatında olmalıdır."
        elif hours_worked is None or hours_worked < 0:
            error = "İş saatı düzgün daxil edilməlidir."
        elif TabelEntry.query.filter_by(employee_id=employee_id, work_date=work_date).first():
            error = "Bu əməkdaş üçün həmin tarixdə tabel artıq mövcuddur."
        elif TabelEntry.query.filter(TabelEntry.employee_id==employee_id, TabelEntry.work_date==work_date, TabelEntry.id!=entry.id).first():
            error = "Bu əməkdaş üçün həmin tarixdə tabel artıq mövcuddur."
        if error:
            flash(error, "danger")
            return render_form("tabel/form.html", entry=None, employees=employees)
        entry = TabelEntry(
            employee_id=employee_id,
            work_date=work_date,
            hours_worked=hours_worked,
            status=request.form.get("status", "present"),
            note=request.form.get("note", "").strip(),
        )
        db.session.add(entry)
        db.session.commit()
        flash("Tabel qeydi əlavə olundu.", "success")
        return modal_redirect("tabel.list_entries")
    return render_form("tabel/form.html", entry=None, employees=employees)


@tabel_bp.route("/edit/<int:entry_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT")
def edit_entry(entry_id):
    entry = TabelEntry.query.get_or_404(entry_id)
    employees = Employee.query.filter_by(is_active=True).all()
    if request.method == "POST":
        employee_id = _parse_int(request.form.get("employee_id"))
        work_date = _parse_date(request.form.get("work_date"))
        hours_worked = _parse_float(request.form.get("hours_worked") or 0)
        employee = Employee.query.get(employee_id) if employee_id else None
        error = None
        if not employee_id or not employee:
            error = "Əməkdaş mütləq seçilməlidir."
        elif not work_date:
            error = "İş tarixi mütləqdir və YYYY-MM-DD formatında olmalıdır."
        elif hours_worked is None or hours_worked < 0:
            error = "İş saatı düzgün daxil edilməlidir."
        if error:
            flash(error, "danger")
            return render_form("tabel/form.html", entry=entry, employees=employees)
        entry.employee_id = employee_id
        entry.work_date = work_date
        entry.hours_worked = hours_worked
        entry.status = request.form.get("status", "present")
        entry.note = request.form.get("note", "").strip()
        db.session.commit()
        flash("Tabel qeydi yeniləndi.", "success")
        return modal_redirect("tabel.list_entries")
    return render_form("tabel/form.html", entry=entry, employees=employees)


@tabel_bp.route("/delete/<int:entry_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE")
def delete_entry(entry_id):
    entry = TabelEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Tabel qeydi silindi.", "info")
    return redirect(url_for("tabel.list_entries"))
