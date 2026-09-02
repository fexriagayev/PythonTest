import os
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    send_file,
)
from flask_login import login_required

from app import db
from app.models import (
    Employee,
    DictionaryItem,
    Order,
    EmploymentRecord,
    LeaveCategory,
    EmploymentContractNotification,
    LeaveReason,
    Holiday,
    LeaveRequest,
    VacationCompensation,
    InsurancePolicy,
    SalaryCard,
)
from app.utils.decorators import permission_required, log_action
from app.utils.uploads import (
    save_uploaded_file,
    delete_uploaded_file,
    uploaded_file_path,
)
from app.services.document_service import delete_all_documents_for_owner
from app.services.hr_service import (
    recompute_employee_from_history,
    recompute_employee_contract_from_bildiris,
    get_last_current_company_record,
)
from app.services.leave_service import (
    compute_leave_periods,
    get_leave_balance,
    get_remaining_vacation_days_live,
    compute_end_date,
    validate_leave_request,
)
from app.utils.date_overlap import find_overlapping
from app.utils.parsing import _parse_date, _parse_int, _parse_decimal
from app.utils.modal import (
    render_form,
    modal_redirect,
    modal_employee_saved,
    is_modal_request,
)
from app.i18n import translate, current_lang

hr_bp = Blueprint("hr", __name__)
MODULE = "HR"


def _employee_page_layout():
    return "modal_layout.html" if request.args.get("embedded") == "1" else "base.html"


def _dict_options(category):
    return (
        DictionaryItem.query.filter_by(
            module_code=MODULE, category=category, is_active=True
        )
        .order_by(DictionaryItem.name)
        .all()
    )


def _form_choices():
    """All dictionary-driven combobox options used on the employee form."""
    return {
        "genders": _dict_options("gender"),
        "family_statuses": _dict_options("family_status"),
        "education_types": _dict_options("education_type"),
        "benefit_options": _dict_options("benefits"),
    }


def _apply_form_to_employee(employee, form):
    # Ad Soyad Ata adı (vahid sahə)
    employee.full_name = form.get("full_name", "").strip()

    # Şəxsi məlumatlar (dictionary-driven)
    employee.gender_id = _parse_int(form.get("gender_id"))
    employee.family_status_id = _parse_int(form.get("family_status_id"))
    employee.education_type_id = _parse_int(form.get("education_type_id"))
    employee.birth_date = _parse_date(form.get("birth_date"))

    # Güzəşt (single-select dictionary)
    employee.benefit_id = _parse_int(form.get("benefit_id"))

    # Sənəd məlumatları
    employee.fin_code = form.get("fin_code", "").strip()
    employee.id_card_number = form.get("id_card_number", "").strip()
    employee.social_insurance_number = form.get("social_insurance_number", "").strip()

    # İş məlumatları — department/position/hire_date/termination_date/
    # is_active/*_experience/remaining_vacation_days are NOT read here
    # anymore: they are computed automatically from the employee's
    # "İş yerləri" (əmək kitabçası) və "Məzuniyyət günləri" hesablamalarından.
    # See app/services/hr_service.py.
    # salary / contract_start_date / contract_end_date are NOT read here —
    # they are computed from the employee's "Bildirişlər" records. See
    # app/services/hr_service.py:recompute_employee_contract_from_bildiris().
    if not employee.full_name:
        raise ValueError("Ad Soyad Ata adı mütləqdir")

    # Əlaqə / digər
    employee.phone = form.get("phone", "").strip()
    employee.email = form.get("email", "").strip()
    employee.note = form.get("note", "").strip()

    if employee.id is None:
        # Brand-new employee: no employment history yet, default to active
        employee.is_active = True


@hr_bp.route("/")
@login_required
@permission_required(MODULE, "can_view")
def list_employees():
    return render_template("hr/list.html")


@hr_bp.route("/api/employees")
@login_required
@permission_required(MODULE, "can_view")
def api_employees():
    # Əməkdaşların siyahısında default olaraq yalnız AKTİV əməkdaşlar
    # göstərilir (is_active "son iş yeri" qeydindən avtomatik hesablanır,
    # bax: app/services/hr_service.py:recompute_employee_from_history).
    # "Passiv əməkdaşları göstər" işarələndikdə isə YALNIZ passivlər
    # göstərilir (bax: hr/list.html-dəki filter).
    show_inactive = request.args.get("include_inactive") == "1"
    query = Employee.query.filter(Employee.is_active.is_(not show_inactive))
    employees = query.all()
    data = [
        {
            "id": e.id,
            "full_name": e.full_name,
            "gender": e.gender.name if e.gender else None,
            "birth_date": e.birth_date.isoformat() if e.birth_date else None,
            "department": e.department,
            "position": e.position,
            "hire_date": e.hire_date.isoformat() if e.hire_date else None,
            # Canlı hesablanır (bax: leave_service.get_remaining_vacation_days_live) —
            # saxlanılan sütundan deyil, çünki nəticə bugünkü tarixdən asılıdır.
            "remaining_vacation_days": get_remaining_vacation_days_live(e),
            "phone": e.phone,
            "email": e.email,
            "is_active": e.is_active,
        }
        for e in employees
    ]
    return jsonify(data)


@hr_bp.route("/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD")
def add_employee():
    if request.method == "POST":
        employee = Employee()
        _apply_form_to_employee(employee, request.form)
        db.session.add(employee)
        db.session.flush()
        recompute_employee_from_history(employee)
        db.session.commit()
        flash(
            "Əməkdaş əlavə olundu. İndi digər məlumat bölmələrini doldura bilərsiniz.",
            "success",
        )
        return modal_employee_saved(employee.id)
    return render_form("hr/form.html", employee=None, **_form_choices())


@hr_bp.route("/edit/<int:emp_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT")
def edit_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        _apply_form_to_employee(employee, request.form)
        recompute_employee_from_history(employee)
        db.session.commit()
        flash("Əməkdaşın məlumatları yeniləndi.", "success")

        if is_modal_request():
            return jsonify(
                {
                    "success": True,
                    "keep_open": True,
                    "reload_url": url_for("hr.edit_employee", emp_id=employee.id),
                    "employee_id": employee.id,
                }
            )

        return redirect(url_for("hr.list_employees"))
    # "Qalan məzuniyyət günləri" hər dəfə "Məzuniyyət günləri" cədvəlindən
    # canlı hesablanır (bax: leave_service.get_remaining_vacation_days_live) —
    # bugünkü tarixdən asılı olduğu üçün saxlanılan sütuna güvənilmir.
    return render_form(
        "hr/form.html",
        employee=employee,
        remaining_vacation_days_live=get_remaining_vacation_days_live(employee),
        **_form_choices(),
    )


@hr_bp.route("/delete/<int:emp_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE")
def delete_employee(emp_id):
    employee = Employee.query.get_or_404(emp_id)

    # Physical files aren't covered by the DB cascade — clean those up first.
    delete_uploaded_file(employee.photo_path, PHOTO_SUBDIR)
    delete_all_documents_for_owner("employee", employee.id)

    db.session.delete(employee)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Əməkdaş silindi.", "info")
    return redirect(url_for("hr.list_employees"))


# ---------------------------------------------------------------------------
# Əmrlər (Orders) — a structured HR dictionary used to justify hiring /
# internal transfer / termination records in the əmək kitabçası below.
# Reuses the HR module's dict_* permissions since this is conceptually
# "an HR dictionary", just with real structured fields instead of name/value.
# ---------------------------------------------------------------------------


@hr_bp.route("/orders")
@login_required
@permission_required(MODULE, "dict_view")
def list_orders():
    return render_template("hr/orders_list.html")


@hr_bp.route("/orders/api/orders")
@login_required
@permission_required(MODULE, "dict_view")
def api_orders():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    data = [
        {
            "id": o.id,
            "number": o.number,
            "order_date": o.order_date.isoformat() if o.order_date else None,
            "effective_date": (
                o.effective_date.isoformat() if o.effective_date else None
            ),
            "order_type": o.order_type.name if o.order_type else None,
            "note": o.note,
        }
        for o in orders
    ]
    return jsonify(data)


@hr_bp.route("/orders/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_add")
@log_action("HR_ORDERS", "ADD")
def add_order():
    order_types = _dict_options("order_type")
    if request.method == "POST":
        order = Order(
            number=request.form.get("number", "").strip(),
            order_date=_parse_date(request.form.get("order_date")),
            effective_date=_parse_date(request.form.get("effective_date")),
            order_type_id=_parse_int(request.form.get("order_type_id")),
            note=request.form.get("note", "").strip(),
        )
        db.session.add(order)
        db.session.commit()
        flash("Əmr əlavə olundu.", "success")
        return modal_redirect("hr.list_orders")
    return render_form(
        "hr/order_form.html",
        order=None,
        order_types=order_types,
        usage_records=[],
        usage_notifications=[],
    )


@hr_bp.route("/orders/edit/<int:order_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_edit")
@log_action("HR_ORDERS", "EDIT")
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    order_types = _dict_options("order_type")
    usage_records = (
        EmploymentRecord.query.filter_by(order_id=order.id)
        .order_by(EmploymentRecord.date_from.desc())
        .all()
    )
    usage_notifications = (
        EmploymentContractNotification.query.filter_by(order_id=order.id)
        .order_by(EmploymentContractNotification.start_date.desc())
        .all()
    )
    if request.method == "POST":
        order.number = request.form.get("number", "").strip()
        order.order_date = _parse_date(request.form.get("order_date"))
        order.effective_date = _parse_date(request.form.get("effective_date"))
        order.order_type_id = _parse_int(request.form.get("order_type_id"))
        order.note = request.form.get("note", "").strip()
        db.session.commit()
        flash("Əmr yeniləndi.", "success")
        return modal_redirect("hr.list_orders")
    return render_form(
        "hr/order_form.html",
        order=order,
        order_types=order_types,
        usage_records=usage_records,
        usage_notifications=usage_notifications,
    )


@hr_bp.route("/orders/delete/<int:order_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "dict_delete")
@log_action("HR_ORDERS", "DELETE")
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    in_use = (
        EmploymentRecord.query.filter_by(order_id=order.id).first()
        or EmploymentContractNotification.query.filter_by(order_id=order.id).first()
    )
    if in_use:
        if is_modal_request():
            return jsonify(
                {
                    "success": False,
                    "html": "<div class='flash flash-danger'>Bu əmr iş yerləri və ya bildiriş qeydlərində istifadə olunur, silinə bilməz.</div>",
                }
            )
        flash(
            "Bu əmr iş yerləri və ya bildiriş qeydlərində istifadə olunur, silinə bilməz.",
            "danger",
        )
        return redirect(url_for("hr.list_orders"))
    db.session.delete(order)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Əmr silindi.", "info")
    return redirect(url_for("hr.list_orders"))


# ---------------------------------------------------------------------------
# İş yerləri (əmək kitabçası) — nested under a specific employee.
# ---------------------------------------------------------------------------

# Static (Azerbaijani) fallback keys — kept for any code that still reads
# MOVEMENT_LABELS directly. Prefer _movement_labels()/translate() for
# anything user-facing, since those respect the current user's language.
MOVEMENT_LABELS = {
    "hire": "İşə qəbul",
    "transfer": "Daxili keçid (struktur/vəzifə dəyişikliyi)",
    "termination": "İşdən çıxma",
}

_MOVEMENT_LABEL_KEYS = {
    "hire": "movement_hire",
    "transfer": "movement_transfer",
    "termination": "movement_termination",
}


def _movement_labels():
    """Translated {code: label} dict, in the current user's language."""
    lang = current_lang()
    return {code: translate(key, lang) for code, key in _MOVEMENT_LABEL_KEYS.items()}


def _allowed_movement_types(
    employee_id, exclude_id=None, keep_code=None, before_date=None, is_current=True
):
    """Which 'Hərəkət növü' codes are allowed at position `before_date` in
    this employee's CARİ ŞİRKƏT chain (is_current=True) or KƏNAR ŞİRKƏT
    chain (is_current=False) — the two chains are tracked independently,
    per the same business rule in both cases:
      - boş zəncir (və ya bu tarixdən əvvəl heç nə yoxdursa) -> yalnız 'hire'
      - dərhal əvvəlki qeyd 'termination' -> yalnız 'hire' (yeni iş dövrü)
      - dərhal əvvəlki qeyd 'hire'/'transfer' -> 'transfer' / 'termination'
    `before_date` MUST be the record's own date_from when validating/
    rendering an EDIT — otherwise "the record right before this one" can
    wrongly resolve to a record that is actually chronologically AFTER it
    (see get_last_current_company_record). `keep_code` (the record's own
    current movement_type, when editing) is always included so an existing
    record can still be saved unchanged.
    """
    last = get_last_current_company_record(
        employee_id, exclude_id=exclude_id, before_date=before_date, is_current=is_current
    )
    if last is None or last.movement_type == "termination":
        allowed = ["hire"]
    else:
        allowed = ["transfer", "termination"]
    if keep_code and keep_code not in allowed:
        allowed.append(keep_code)
    return allowed


def _work_history_form_choices(employee_id=None, record=None):
    exclude_id = record.id if record else None
    keep_code = record.movement_type if record else None
    # GET-də (yenidən render) mövqe = qeydin ÖZ (hazırkı) date_from-udur;
    # yeni qeyd üçün before_date=None (= "xronoloji cəhətdən son", çünki
    # yeni qeyd adətən zəncirin sonuna əlavə olunur).
    before_date = record.date_from if record else None
    last_current = get_last_current_company_record(
        employee_id, exclude_id=exclude_id, before_date=before_date, is_current=True
    )
    last_external = get_last_current_company_record(
        employee_id, exclude_id=exclude_id, before_date=before_date, is_current=False
    )
    return {
        "departments": _dict_options("department"),
        "positions": _dict_options("position"),
        "orders": Order.query.order_by(Order.order_date.desc()).all(),
        "movement_labels": _movement_labels(),
        "allowed_movement_types": _allowed_movement_types(
            employee_id,
            exclude_id=exclude_id,
            keep_code=keep_code,
            before_date=before_date,
            is_current=True,
        ),
        "allowed_movement_types_external": _allowed_movement_types(
            employee_id,
            exclude_id=exclude_id,
            keep_code=keep_code,
            before_date=before_date,
            is_current=False,
        ),
        "last_department_id": last_current.department_id if last_current else None,
        "last_department_name": last_current.department.name
        if last_current and last_current.department
        else "",
        "last_position_id": last_current.position_id if last_current else None,
        "last_position_name": last_current.position.name
        if last_current and last_current.position
        else "",
        "last_external_company_name": last_external.external_company_name
        if last_external
        else "",
        "last_external_department": last_external.external_department
        if last_external
        else "",
        "last_external_position": last_external.external_position
        if last_external
        else "",
    }


@hr_bp.route("/<int:emp_id>/work-history")
@login_required
@permission_required(MODULE, "can_view")
def work_history(emp_id):
    employee = Employee.query.get_or_404(emp_id)

    if request.args.get("embedded") == "1":
        return render_template(
            "hr/partials/employee/work_history.html",
            employee=employee,
        )

    return render_template(
        "hr/work_history_list.html",
        employee=employee,
    )


@hr_bp.route("/<int:emp_id>/work-history/api/records")
@login_required
@permission_required(MODULE, "can_view")
def api_work_history(emp_id):
    records = (
        EmploymentRecord.query.filter_by(employee_id=emp_id)
        .order_by(EmploymentRecord.date_from.asc())
        .all()
    )
    lang = current_lang()
    movement_labels = _movement_labels()
    ticket_current = translate("wh_ticket_current_short", lang)
    ticket_external = translate("wh_ticket_external_short", lang)
    data = [
        {
            "id": r.id,
            "is_current_company": r.is_current_company,
            "ticket": ticket_current if r.is_current_company else ticket_external,
            "movement_type": movement_labels.get(r.movement_type, r.movement_type),
            "workplace": r.workplace_label(),
            "position": r.position_label(),
            "order": r.order.label() if r.order else None,
            "date_from": r.date_from.isoformat() if r.date_from else None,
            "note": r.note,
        }
        for r in records
    ]
    return jsonify(data)


@hr_bp.route("/<int:emp_id>/work-history/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_WORK_HISTORY")
def add_work_history(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        error = _validate_work_history_form(request.form, employee_id=emp_id)
        if error:
            flash(error, "danger")
            return render_form(
                "hr/work_history_form.html",
                employee=employee,
                record=None,
                **_work_history_form_choices(employee_id=emp_id),
            )
        record = EmploymentRecord(employee_id=employee.id)
        _apply_work_history_form(record, request.form, employee_id=emp_id)
        db.session.add(record)
        db.session.flush()
        recompute_employee_from_history(employee)
        db.session.commit()
        flash("İş yeri qeydi əlavə olundu.", "success")
        return modal_redirect("hr.work_history", emp_id=employee.id)
    return render_form(
        "hr/work_history_form.html",
        employee=employee,
        record=None,
        **_work_history_form_choices(employee_id=emp_id),
    )


@hr_bp.route("/<int:emp_id>/work-history/edit/<int:record_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_WORK_HISTORY")
def edit_work_history(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = EmploymentRecord.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    if request.method == "POST":
        error = _validate_work_history_form(
            request.form, employee_id=emp_id, exclude_id=record.id
        )
        if error:
            flash(error, "danger")
            return render_form(
                "hr/work_history_form.html",
                employee=employee,
                record=record,
                **_work_history_form_choices(employee_id=emp_id, record=record),
            )
        _apply_work_history_form(
            record, request.form, employee_id=emp_id, exclude_id=record.id
        )
        db.session.flush()
        recompute_employee_from_history(employee)
        db.session.commit()
        flash("İş yeri qeydi yeniləndi.", "success")
        return modal_redirect("hr.work_history", emp_id=employee.id)
    return render_form(
        "hr/work_history_form.html",
        employee=employee,
        record=record,
        **_work_history_form_choices(employee_id=emp_id, record=record),
    )


@hr_bp.route("/<int:emp_id>/work-history/delete/<int:record_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_WORK_HISTORY")
def delete_work_history(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = EmploymentRecord.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    db.session.delete(record)
    db.session.flush()
    recompute_employee_from_history(employee)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("İş yeri qeydi silindi.", "info")
    return redirect(url_for("hr.work_history", emp_id=employee.id))


def _validate_work_history_form(form, employee_id, exclude_id=None):
    # date_to formda da, databasede də yoxdur — bütün qeydlərin bitmə tarixi
    # hər dəfə xronoloji zəncirdən anlıq hesablanır (bax:
    # app.services.hr_service.compute_chain_end_dates), ona görə tarix
    # kəsişməsi (overlap) yoxlamasına da artıq ehtiyac qalmır.
    is_current = form.get("is_current_company") == "1"
    if not form.get("date_from"):
        return "Başlama tarixi mütləq daxil edilməlidir."

    # 'Hərəkət növü' həm cari şirkət, həm də kənar şirkət qeydləri üçün
    # eyni qaydada tətbiq olunur — hər ikisinin öz müstəqil zənciri var
    # (bax: _allowed_movement_types / get_last_current_company_record).
    movement = form.get("movement_type") or "hire"
    allowed = _allowed_movement_types(
        employee_id, exclude_id=exclude_id, is_current=is_current
    )
    if movement not in allowed:
        if allowed == ["hire"]:
            return "Bu, zəncirdəki növbəti qeyddir və yalnız 'İşə qəbul' ola bilər."
        return (
            "Son qeyd 'İşdən çıxma' olmadığı üçün növbəti qeyd "
            "'İşə qəbul' ola bilməz — 'Daxili keçid' və ya 'İşdən çıxma' seçin."
        )

    if is_current:
        if not form.get("order_id"):
            return "Cari şirkət qeydi üçün əmr seçilməlidir."
        # 'İşdən çıxma' qeydinin öz struktur/vəzifəsi yoxdur — son cari
        # şirkət qeydindən avtomatik götürülür, ona görə bu iki sahə
        # yalnız 'hire'/'transfer' üçün tələb olunur.
        if movement != "termination":
            if not form.get("department_id"):
                return "Struktur (şöbə) seçilməlidir."
            if not form.get("position_id"):
                return "Vəzifə seçilməlidir."
        elif get_last_current_company_record(employee_id, exclude_id=exclude_id, is_current=True) is None:
            return "İşdən çıxma qeydi üçün əvvəlcə İşə qəbul qeydi olmalıdır."
    else:
        # Kənar şirkət qeydi üçün də eyni məntiq: 'İşdən çıxma' qeydinin öz
        # şirkət/struktur/vəzifəsi yoxdur — son kənar qeyddən avtomatik
        # götürülür, ona görə bu sahə yalnız 'hire'/'transfer' üçün tələb
        # olunur.
        if movement != "termination":
            if not form.get("external_company_name", "").strip():
                return "Kənar şirkətin adı daxil edilməlidir."
        elif get_last_current_company_record(employee_id, exclude_id=exclude_id, is_current=False) is None:
            return "İşdən çıxma qeydi üçün əvvəlcə kənar şirkətdə işə başlama qeydi olmalıdır."

    return None


def _apply_work_history_form(record, form, employee_id, exclude_id=None):
    is_current = form.get("is_current_company") == "1"
    record.is_current_company = is_current
    record.date_from = _parse_date(form.get("date_from"))
    record.note = form.get("note", "").strip()

    movement = form.get("movement_type") or "hire"
    record.movement_type = movement

    if is_current:
        record.order_id = _parse_int(form.get("order_id"))
        if movement == "termination":
            # Öz struktur/vəzifəsi yoxdur — son cari şirkət qeydindən
            # avtomatik götürülür (form-dan gələn dəyərlər nəzərə alınmır,
            # çünki həmin sahələr formda disable olunub).
            last_current = get_last_current_company_record(
                employee_id, exclude_id=exclude_id, is_current=True
            )
            record.department_id = last_current.department_id if last_current else None
            record.position_id = last_current.position_id if last_current else None
        else:
            record.department_id = _parse_int(form.get("department_id"))
            record.position_id = _parse_int(form.get("position_id"))
        record.external_company_name = None
        record.external_department = None
        record.external_position = None
    else:
        record.department_id = None
        record.position_id = None
        record.order_id = None
        if movement == "termination":
            # Kənar şirkət üçün də eyni qayda: 'İşdən çıxma' qeydinin öz
            # şirkət/struktur/vəzifəsi yoxdur — son kənar qeyddən avtomatik
            # götürülür (bu sahələr formda disable olunub).
            last_external = get_last_current_company_record(
                employee_id, exclude_id=exclude_id, is_current=False
            )
            record.external_company_name = (
                last_external.external_company_name if last_external else None
            )
            record.external_department = (
                last_external.external_department if last_external else None
            )
            record.external_position = (
                last_external.external_position if last_external else None
            )
        else:
            record.external_company_name = form.get("external_company_name", "").strip()
            record.external_department = form.get("external_department", "").strip()
            record.external_position = form.get("external_position", "").strip()

    # date_to bu funksiyada VƏ HEÇ BİR YERDƏ təyin OLUNMUR — o, artıq
    # saxlanmır; hər dəfə app.services.hr_service.compute_chain_end_dates()
    # tərəfindən employee-nin bütün xronoloji zəncirindən anlıq hesablanır.


# ---------------------------------------------------------------------------
# Kateqoriyalar (LeaveCategory) — structured HR dictionary that drives
# vacation-day calculations. Reuses HR's dict_* permissions.
# ---------------------------------------------------------------------------


@hr_bp.route("/leave-categories")
@login_required
@permission_required(MODULE, "dict_view")
def list_leave_categories():
    return render_template("hr/leave_category_list.html")


@hr_bp.route("/leave-categories/api/items")
@login_required
@permission_required(MODULE, "dict_view")
def api_leave_categories():
    items = LeaveCategory.query.order_by(LeaveCategory.name).all()
    data = [
        {
            "id": c.id,
            "name": c.name,
            "base_vacation_days": c.base_vacation_days,
            "seniority_years_per_bonus": c.seniority_years_per_bonus,
            "bonus_days_per_interval": c.bonus_days_per_interval,
            "max_bonus_days": c.max_bonus_days,
            "is_active": c.is_active,
        }
        for c in items
    ]
    return jsonify(data)


def _apply_leave_category_form(category, form):
    category.name = form.get("name", "").strip()
    category.base_vacation_days = _parse_int(form.get("base_vacation_days")) or 0
    category.seniority_years_per_bonus = (
        _parse_int(form.get("seniority_years_per_bonus")) or 0
    )
    category.bonus_days_per_interval = (
        _parse_int(form.get("bonus_days_per_interval")) or 0
    )
    category.max_bonus_days = _parse_int(form.get("max_bonus_days")) or 0
    category.is_active = bool(form.get("is_active"))


@hr_bp.route("/leave-categories/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_add")
@log_action("HR_LEAVE_CATEGORY", "ADD")
def add_leave_category():
    if request.method == "POST":
        category = LeaveCategory()
        _apply_leave_category_form(category, request.form)
        db.session.add(category)
        db.session.commit()
        flash("Kateqoriya əlavə olundu.", "success")
        return modal_redirect("hr.list_leave_categories")
    return render_form("hr/leave_category_form.html", category=None)


@hr_bp.route("/leave-categories/edit/<int:category_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_edit")
@log_action("HR_LEAVE_CATEGORY", "EDIT")
def edit_leave_category(category_id):
    category = LeaveCategory.query.get_or_404(category_id)
    if request.method == "POST":
        _apply_leave_category_form(category, request.form)
        db.session.commit()
        flash("Kateqoriya yeniləndi.", "success")
        return modal_redirect("hr.list_leave_categories")
    return render_form("hr/leave_category_form.html", category=category)


@hr_bp.route("/leave-categories/delete/<int:category_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "dict_delete")
@log_action("HR_LEAVE_CATEGORY", "DELETE")
def delete_leave_category(category_id):
    category = LeaveCategory.query.get_or_404(category_id)
    if EmploymentContractNotification.query.filter_by(
        leave_category_id=category.id
    ).first():
        if is_modal_request():
            return jsonify(
                {
                    "success": False,
                    "html": "<div class='flash flash-danger'>Bu kateqoriya bildiriş qeydlərində istifadə olunur, silinə bilməz.</div>",
                }
            )
        flash(
            "Bu kateqoriya bildiriş qeydlərində istifadə olunur, silinə bilməz.",
            "danger",
        )
        return redirect(url_for("hr.list_leave_categories"))
    db.session.delete(category)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Kateqoriya silindi.", "info")
    return redirect(url_for("hr.list_leave_categories"))


# ---------------------------------------------------------------------------
# Bildirişlər (EmploymentContractNotification) — DSMF saytına daxil edilmiş məlumatların
# kopyası. Nested under a specific employee, same pattern as work-history.
# ---------------------------------------------------------------------------


def _notifications_form_choices():
    return {
        "employment_classifications": _dict_options("employment_classification"),
        "employment_positions": _dict_options("employment_position"),
        "contract_types": _dict_options("contract_type"),
        "work_types": _dict_options("work_type"),
        "labor_types": _dict_options("labor_type"),
        "leave_categories": LeaveCategory.query.filter_by(is_active=True)
        .order_by(LeaveCategory.name)
        .all(),
        "orders": Order.query.order_by(Order.order_date.desc()).all(),
    }


@hr_bp.route("/<int:emp_id>/notifications")
@login_required
@permission_required(MODULE, "can_view")
def notifications(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return render_template(
        "hr/notifications_list.html",
        employee=employee,
        layout=_employee_page_layout(),
    )


@hr_bp.route("/<int:emp_id>/notifications/api/records")
@login_required
@permission_required(MODULE, "can_view")
def api_notifications(emp_id):
    records = (
        EmploymentContractNotification.query.filter_by(employee_id=emp_id)
        .order_by(
            EmploymentContractNotification.start_date.desc(),
            EmploymentContractNotification.created_at.desc(),
        )
        .all()
    )
    data = [
        {
            "id": r.id,
            "number": r.number,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "order": r.order.label() if r.order else None,
            "employment_classification": (
                r.employment_classification.name
                if r.employment_classification
                else None
            ),
            "employment_position": (
                r.employment_position.name if r.employment_position else None
            ),
            "contract_number": r.contract_number,
            "contract_type": r.contract_type.name if r.contract_type else None,
            "contract_start_date": (
                r.contract_start_date.isoformat() if r.contract_start_date else None
            ),
            "contract_end_date": (
                r.contract_end_date.isoformat() if r.contract_end_date else None
            ),
            "work_type": r.work_type.name if r.work_type else None,
            "labor_type": r.labor_type.name if r.labor_type else None,
            "leave_category": r.leave_category.name if r.leave_category else None,
            "salary": float(r.salary) if r.salary is not None else None,
            "note": r.note,
        }
        for r in records
    ]
    return jsonify(data)


def _apply_notification_form(record, form):
    if not record.id and record.employee_id:
        previous = (
            EmploymentContractNotification.query.filter_by(
                employee_id=record.employee_id
            )
            .order_by(
                EmploymentContractNotification.start_date.desc(),
                EmploymentContractNotification.created_at.desc(),
            )
            .first()
        )
        if previous:
            for field in [
                "employment_classification_id",
                "employment_position_id",
                "contract_number",
                "contract_type_id",
                "contract_start_date",
                "contract_end_date",
                "work_type_id",
                "labor_type_id",
                "leave_category_id",
                "salary",
                "note",
            ]:
                setattr(record, field, getattr(previous, field))
    record.number = form.get("number", "").strip()
    record.start_date = _parse_date(form.get("start_date"))
    record.order_id = _parse_int(form.get("order_id"))

    record.employment_classification_id = _parse_int(
        form.get("employment_classification_id")
    )
    record.employment_position_id = _parse_int(form.get("employment_position_id"))
    record.contract_number = form.get("contract_number", "").strip()
    record.contract_type_id = _parse_int(form.get("contract_type_id"))
    record.contract_start_date = _parse_date(form.get("contract_start_date"))
    record.contract_end_date = _parse_date(form.get("contract_end_date"))

    record.work_type_id = _parse_int(form.get("work_type_id"))
    record.labor_type_id = _parse_int(form.get("labor_type_id"))
    record.leave_category_id = _parse_int(form.get("leave_category_id"))

    record.salary = _parse_decimal(form.get("salary"))
    record.note = form.get("note", "").strip()


def _validate_notification_form(form):
    if not form.get("number", "").strip():
        return "Bildirişin nömrəsi mütləqdir."
    if not form.get("start_date"):
        return "Başlama tarixi mütləqdir."
    if not form.get("order_id"):
        return "Əmr seçilməlidir."
    return None


@hr_bp.route("/<int:emp_id>/notifications/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_NOTIFICATION")
def add_notification(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    # Pre-fill Part 2-6 with the most recent notification's values, since
    # only Part 1 (number/date/order) is guaranteed to change every time.
    latest = (
        EmploymentContractNotification.query.filter_by(employee_id=emp_id)
        .order_by(
            EmploymentContractNotification.start_date.desc(),
            EmploymentContractNotification.created_at.desc(),
        )
        .first()
    )
    if request.method == "POST":
        error = _validate_notification_form(request.form)
        if error:
            flash(error, "danger")
            return render_form(
                "hr/notification_form.html",
                employee=employee,
                record=None,
                latest=latest,
                **_notifications_form_choices(),
            )
        record = EmploymentContractNotification(employee_id=employee.id)
        _apply_notification_form(record, request.form)
        db.session.add(record)
        db.session.flush()
        recompute_employee_contract_from_bildiris(employee)
        db.session.commit()
        flash("Bildiriş əlavə olundu.", "success")
        return modal_redirect("hr.notifications", emp_id=employee.id)
    return render_form(
        "hr/notification_form.html",
        employee=employee,
        record=None,
        latest=latest,
        **_notifications_form_choices(),
    )


@hr_bp.route(
    "/<int:emp_id>/notifications/edit/<int:record_id>", methods=["GET", "POST"]
)
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_NOTIFICATION")
def edit_notification(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = EmploymentContractNotification.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    if request.method == "POST":
        error = _validate_notification_form(request.form)
        if error:
            flash(error, "danger")
            return render_form(
                "hr/notification_form.html",
                employee=employee,
                record=record,
                latest=None,
                **_notifications_form_choices(),
            )
        _apply_notification_form(record, request.form)
        recompute_employee_contract_from_bildiris(employee)
        db.session.commit()
        flash("Bildiriş yeniləndi.", "success")
        return modal_redirect("hr.notifications", emp_id=employee.id)
    return render_form(
        "hr/notification_form.html",
        employee=employee,
        record=record,
        latest=None,
        **_notifications_form_choices(),
    )


@hr_bp.route("/<int:emp_id>/notifications/delete/<int:record_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_NOTIFICATION")
def delete_notification(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = EmploymentContractNotification.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    db.session.delete(record)
    db.session.flush()
    recompute_employee_contract_from_bildiris(employee)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Bildiriş silindi.", "info")
    return redirect(url_for("hr.notifications", emp_id=employee.id))


# ---------------------------------------------------------------------------
# Məzuniyyət səbəbləri (LeaveReason) — structured dictionary with a day-
# counting rule. Reuses HR's dict_* permissions.
# ---------------------------------------------------------------------------


@hr_bp.route("/leave-reasons")
@login_required
@permission_required(MODULE, "dict_view")
def list_leave_reasons():
    return render_template("hr/leave_reason_list.html")


@hr_bp.route("/leave-reasons/api/items")
@login_required
@permission_required(MODULE, "dict_view")
def api_leave_reasons():
    items = LeaveReason.query.order_by(LeaveReason.name).all()
    data = [
        {
            "id": r.id,
            "name": r.name,
            "counting_method": r.counting_method_label(),
            "is_annual_leave": r.is_annual_leave,
            "is_active": r.is_active,
            "tabel_code": r.tabel_code,
        }
        for r in items
    ]
    return jsonify(data)


def _apply_leave_reason_form(reason, form):
    reason.name = form.get("name", "").strip()
    reason.counting_method = form.get("counting_method", "calendar")
    reason.is_annual_leave = bool(form.get("is_annual_leave"))
    reason.is_active = bool(form.get("is_active"))
    reason.tabel_code = form.get("tabel_code", "").strip() or None


@hr_bp.route("/leave-reasons/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_add")
@log_action("HR_LEAVE_REASON", "ADD")
def add_leave_reason():
    if request.method == "POST":
        reason = LeaveReason()
        _apply_leave_reason_form(reason, request.form)
        db.session.add(reason)
        db.session.commit()
        flash("Səbəb əlavə olundu.", "success")
        return modal_redirect("hr.list_leave_reasons")
    return render_form(
        "hr/leave_reason_form.html", reason=None, methods=LeaveReason.COUNTING_METHODS
    )


@hr_bp.route("/leave-reasons/edit/<int:reason_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_edit")
@log_action("HR_LEAVE_REASON", "EDIT")
def edit_leave_reason(reason_id):
    reason = LeaveReason.query.get_or_404(reason_id)
    if request.method == "POST":
        _apply_leave_reason_form(reason, request.form)
        db.session.commit()
        flash("Səbəb yeniləndi.", "success")
        return modal_redirect("hr.list_leave_reasons")
    return render_form(
        "hr/leave_reason_form.html", reason=reason, methods=LeaveReason.COUNTING_METHODS
    )


@hr_bp.route("/leave-reasons/delete/<int:reason_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "dict_delete")
@log_action("HR_LEAVE_REASON", "DELETE")
def delete_leave_reason(reason_id):
    reason = LeaveReason.query.get_or_404(reason_id)
    if LeaveRequest.query.filter_by(leave_reason_id=reason.id).first():
        if is_modal_request():
            return jsonify(
                {
                    "success": False,
                    "html": "<div class='flash flash-danger'>Bu səbəb iş buraxma qeydlərində istifadə olunur, silinə bilməz.</div>",
                }
            )
        flash(
            "Bu səbəb iş buraxma qeydlərində istifadə olunur, silinə bilməz.", "danger"
        )
        return redirect(url_for("hr.list_leave_reasons"))
    db.session.delete(reason)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Səbəb silindi.", "info")
    return redirect(url_for("hr.list_leave_reasons"))


# ---------------------------------------------------------------------------
# Bayram/matəm günləri (Holiday) — simple date list.
# ---------------------------------------------------------------------------


@hr_bp.route("/holidays")
@login_required
@permission_required(MODULE, "dict_view")
def list_holidays():
    return render_template("hr/holiday_list.html")


@hr_bp.route("/holidays/api/items")
@login_required
@permission_required(MODULE, "dict_view")
def api_holidays():
    items = Holiday.query.order_by(Holiday.date).all()
    return jsonify(
        [{"id": h.id, "date": h.date.isoformat(), "name": h.name} for h in items]
    )


@hr_bp.route("/holidays/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_add")
@log_action("HR_HOLIDAY", "ADD")
def add_holiday():
    if request.method == "POST":
        holiday = Holiday(
            date=_parse_date(request.form.get("date")),
            name=request.form.get("name", "").strip(),
        )
        if Holiday.query.filter_by(date=holiday.date).first():
            flash("Bu tarix artıq bayram kimi qeyd olunub.", "danger")
            return render_form("hr/holiday_form.html", holiday=holiday)
        db.session.add(holiday)
        db.session.commit()
        flash("Bayram günü əlavə olundu.", "success")
        return modal_redirect("hr.list_holidays")
    return render_form("hr/holiday_form.html", holiday=None)


@hr_bp.route("/holidays/edit/<int:holiday_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "dict_edit")
@log_action("HR_HOLIDAY", "EDIT")
def edit_holiday(holiday_id):
    holiday = Holiday.query.get_or_404(holiday_id)
    if request.method == "POST":
        holiday.date = _parse_date(request.form.get("date"))
        holiday.name = request.form.get("name", "").strip()
        db.session.commit()
        flash("Bayram günü yeniləndi.", "success")
        return modal_redirect("hr.list_holidays")
    return render_form("hr/holiday_form.html", holiday=holiday)


@hr_bp.route("/holidays/delete/<int:holiday_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "dict_delete")
@log_action("HR_HOLIDAY", "DELETE")
def delete_holiday(holiday_id):
    holiday = Holiday.query.get_or_404(holiday_id)
    db.session.delete(holiday)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Bayram günü silindi.", "info")
    return redirect(url_for("hr.list_holidays"))


# ---------------------------------------------------------------------------
# Məzuniyyət günləri — read-only computed periods + manual compensation
# ---------------------------------------------------------------------------


@hr_bp.route("/<int:emp_id>/vacation-periods")
@login_required
@permission_required(MODULE, "can_view")
def vacation_periods(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return render_template(
        "hr/vacation_periods.html",
        employee=employee,
        layout=_employee_page_layout(),
    )


@hr_bp.route("/<int:emp_id>/vacation-periods/api/periods")
@login_required
@permission_required(MODULE, "can_view")
def api_vacation_periods(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    periods = compute_leave_periods(employee)
    data = [
        {
            "period_start": p["period_start"].isoformat(),
            "period_end": p["period_end"].isoformat(),
            "category": p["category"],
            "category_days": p["category_days"],
            "entitled_base": p["entitled_base"],
            "entitled_bonus": p["entitled_bonus"],
            "used_base": p["used_base"],
            "used_bonus": p["used_bonus"],
            "compensated_base": p["compensated_base"],
            "remaining_base": p["remaining_base"],
            "remaining_bonus": p["remaining_bonus"],
        }
        for p in periods
    ]
    return jsonify(data)


@hr_bp.route("/<int:emp_id>/vacation-periods/compensation", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "SET_COMPENSATION")
def set_compensation(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    period_start = _parse_date(
        request.args.get("period_start") or request.form.get("period_start")
    )
    period_end = _parse_date(
        request.args.get("period_end") or request.form.get("period_end")
    )
    comp = VacationCompensation.query.filter_by(
        employee_id=emp_id, period_start=period_start
    ).first()

    # Kompensasiya yalnız İSTİFADƏ EDİLMƏMİŞ ƏSAS günlərə görə verilir.
    # Bu tavan — entitled_base - used_base — hər
    # dəfə compute_leave_periods-dən təzədən oxunur ki, İş buraxmaları və ya
    # kateqoriya sonradan dəyişsə belə köhnəlmiş dəyər göstərilməsin/qəbul
    # olunmasın.
    period = next(
        (
            p
            for p in compute_leave_periods(employee)
            if p["period_start"] == period_start
        ),
        None,
    )
    max_compensable_base = (
        max(period["entitled_base"] - period["used_base"], 0) if period else 0
    )

    if request.method == "POST":
        days = _parse_int(request.form.get("compensated_base_days")) or 0

        if days < 0 or days > max_compensable_base:
            flash(
                "Kompensasiya günlərinin sayı 0 ilə {0} arasında olmalıdır "
                "(kompensasiya yalnız istifadə edilməmiş əsas günlərə görə "
                "verilir).".format(max_compensable_base),
                "danger",
            )
            return render_form(
                "hr/compensation_form.html",
                employee=employee,
                comp=comp,
                period_start=period_start,
                period_end=period_end,
                max_compensable_base=max_compensable_base,
            )

        if not comp:
            comp = VacationCompensation(
                employee_id=emp_id, period_start=period_start, period_end=period_end
            )
            db.session.add(comp)
        comp.period_end = period_end
        comp.compensated_base_days = days
        comp.note = request.form.get("note", "").strip()
        # Kompensasiya "Qalan məzuniyyət günləri" balansına birbaşa təsir edir
        # (bax: leave_service.compute_leave_periods -> remaining_base), ona
        # görə əməkdaşın kartındakı yekun sahə də dərhal yenilənməlidir.
        recompute_employee_from_history(employee)
        db.session.commit()
        flash("Kompensasiya qeyd olundu.", "success")
        return modal_redirect("hr.vacation_periods", emp_id=emp_id)

    return render_form(
        "hr/compensation_form.html",
        employee=employee,
        comp=comp,
        period_start=period_start,
        period_end=period_end,
        max_compensable_base=max_compensable_base,
    )


# ---------------------------------------------------------------------------
# İş buraxmaları (LeaveRequest) — nested under a specific employee.
# ---------------------------------------------------------------------------


@hr_bp.route("/<int:emp_id>/leave-requests")
@login_required
@permission_required(MODULE, "can_view")
def leave_requests(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return render_template(
        "hr/leave_requests_list.html",
        employee=employee,
        layout=_employee_page_layout(),
    )


@hr_bp.route("/<int:emp_id>/leave-requests/api/records")
@login_required
@permission_required(MODULE, "can_view")
def api_leave_requests(emp_id):
    records = (
        LeaveRequest.query.filter_by(employee_id=emp_id)
        .order_by(LeaveRequest.start_date.desc())
        .all()
    )
    data = [
        {
            "id": r.id,
            "reason": r.leave_reason.name if r.leave_reason else None,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "day_count": r.day_count,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "order": r.order.label() if r.order else None,
            "note": r.note,
        }
        for r in records
    ]
    return jsonify(data)


@hr_bp.route("/<int:emp_id>/leave-requests/api/balance")
@login_required
@permission_required(MODULE, "can_view")
def api_leave_balance(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return jsonify(get_leave_balance(employee))


@hr_bp.route("/<int:emp_id>/leave-requests/api/end-date")
@login_required
@permission_required(MODULE, "can_view")
def api_compute_end_date(emp_id):
    start = _parse_date(request.args.get("start_date"))
    day_count = _parse_int(request.args.get("day_count"))
    reason_id = _parse_int(request.args.get("leave_reason_id"))
    reason = LeaveReason.query.get(reason_id) if reason_id else None
    if not start or not day_count or not reason:
        return jsonify({"end_date": None})
    end = compute_end_date(start, day_count, reason.counting_method)
    return jsonify({"end_date": end.isoformat() if end else None})


def _leave_request_form_choices():
    return {
        "reasons": LeaveReason.query.filter_by(is_active=True)
        .order_by(LeaveReason.name)
        .all(),
        "orders": Order.query.order_by(Order.order_date.desc()).all(),
    }


@hr_bp.route("/<int:emp_id>/leave-requests/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_LEAVE_REQUEST")
def add_leave_request(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    balance = get_leave_balance(employee)
    if request.method == "POST":
        reason = LeaveReason.query.get(_parse_int(request.form.get("leave_reason_id")))
        start = _parse_date(request.form.get("start_date"))
        day_count = _parse_int(request.form.get("day_count"))
        error = None
        if not reason or not start or not day_count:
            error = "Səbəb, başlama tarixi və gün sayı mütləqdir."
        else:
            end = compute_end_date(start, day_count, reason.counting_method)
            overlap_error = validate_leave_request(employee, start, end)
            if overlap_error:
                error = overlap_error
            elif reason.is_annual_leave and day_count > balance["total"]:
                error = (
                    f"Kifayət qədər məzuniyyət günü yoxdur. Qalıq: "
                    f"{balance['base']} əsas + {balance['bonus']} əlavə = {balance['total']} gün."
                )
        if error:
            flash(error, "danger")
            return render_form(
                "hr/leave_request_form.html",
                employee=employee,
                record=None,
                balance=balance,
                **_leave_request_form_choices(),
            )

        record = LeaveRequest(
            employee_id=employee.id,
            leave_reason_id=reason.id,
            start_date=start,
            day_count=day_count,
            end_date=end,
            order_id=_parse_int(request.form.get("order_id")),
            note=request.form.get("note", "").strip(),
        )
        db.session.add(record)
        recompute_employee_from_history(employee)
        db.session.commit()
        flash("İş buraxması əlavə olundu.", "success")
        return modal_redirect("hr.leave_requests", emp_id=employee.id)

    return render_form(
        "hr/leave_request_form.html",
        employee=employee,
        record=None,
        balance=balance,
        **_leave_request_form_choices(),
    )


@hr_bp.route(
    "/<int:emp_id>/leave-requests/edit/<int:record_id>", methods=["GET", "POST"]
)
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_LEAVE_REQUEST")
def edit_leave_request(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = LeaveRequest.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    balance = get_leave_balance(employee)
    if request.method == "POST":
        reason = LeaveReason.query.get(_parse_int(request.form.get("leave_reason_id")))
        start = _parse_date(request.form.get("start_date"))
        day_count = _parse_int(request.form.get("day_count"))
        error = None
        if not reason or not start or not day_count:
            error = "Səbəb, başlama tarixi və gün sayı mütləqdir."
        else:
            end = compute_end_date(start, day_count, reason.counting_method)
            overlap_error = validate_leave_request(
                employee, start, end, exclude_id=record.id
            )
            if overlap_error:
                error = overlap_error
            elif reason.is_annual_leave:
                # allow the days already allocated to THIS record back into the balance before checking
                available = balance["total"] + record.day_count
                if day_count > available:
                    error = (
                        f"Kifayət qədər məzuniyyət günü yoxdur. Qalıq (bu qeyd nəzərə alınmadan): "
                        f"{available} gün."
                    )
        if error:
            flash(error, "danger")
            return render_form(
                "hr/leave_request_form.html",
                employee=employee,
                record=record,
                balance=balance,
                **_leave_request_form_choices(),
            )

        record.leave_reason_id = reason.id
        record.start_date = start
        record.day_count = day_count
        record.end_date = end
        record.order_id = _parse_int(request.form.get("order_id"))
        record.note = request.form.get("note", "").strip()
        recompute_employee_from_history(employee)
        db.session.commit()
        flash("İş buraxması yeniləndi.", "success")
        return modal_redirect("hr.leave_requests", emp_id=employee.id)

    return render_form(
        "hr/leave_request_form.html",
        employee=employee,
        record=record,
        balance=balance,
        **_leave_request_form_choices(),
    )


@hr_bp.route("/<int:emp_id>/leave-requests/delete/<int:record_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_LEAVE_REQUEST")
def delete_leave_request(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = LeaveRequest.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    db.session.delete(record)
    recompute_employee_from_history(employee)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("İş buraxması silindi.", "info")
    return redirect(url_for("hr.leave_requests", emp_id=emp_id))


# ---------------------------------------------------------------------------
# Şəkil (employee photo) — upload / delete / serve
# ---------------------------------------------------------------------------

PHOTO_SUBDIR = "employee_photos"


@hr_bp.route("/<int:emp_id>/photo", methods=["GET"])
@login_required
@permission_required(MODULE, "can_view")
def get_photo(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if not employee.photo_path:
        abort(404)
    path = uploaded_file_path(employee.photo_path, PHOTO_SUBDIR)
    if not os.path.exists(path):
        abort(404)
    return send_file(path)


@hr_bp.route("/<int:emp_id>/photo/upload", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "UPLOAD_PHOTO")
def upload_photo(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    file = request.files.get("photo")
    stored, _original = save_uploaded_file(file, PHOTO_SUBDIR)
    if stored:
        delete_uploaded_file(employee.photo_path, PHOTO_SUBDIR)
        employee.photo_path = stored
        db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Şəkil yükləndi.", "success")
    return redirect(url_for("hr.edit_employee", emp_id=emp_id))


@hr_bp.route("/<int:emp_id>/photo/delete", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "DELETE_PHOTO")
def delete_photo(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    delete_uploaded_file(employee.photo_path, PHOTO_SUBDIR)
    employee.photo_path = None
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Şəkil silindi.", "info")
    return redirect(url_for("hr.edit_employee", emp_id=emp_id))


# ---------------------------------------------------------------------------
# Sığorta məlumatları (InsurancePolicy)
# ---------------------------------------------------------------------------


def _insurance_form_choices():
    return {
        "companies": _dict_options("insurance_company"),
        "types": _dict_options("insurance_type"),
    }


@hr_bp.route("/<int:emp_id>/insurance")
@login_required
@permission_required(MODULE, "can_view")
def insurance_list(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return render_template(
        "hr/insurance_list.html",
        employee=employee,
        layout=_employee_page_layout(),
    )


@hr_bp.route("/<int:emp_id>/insurance/api/records")
@login_required
@permission_required(MODULE, "can_view")
def api_insurance(emp_id):
    today = datetime.utcnow().date()
    records = (
        InsurancePolicy.query.filter_by(employee_id=emp_id)
        .order_by(InsurancePolicy.end_date.desc())
        .all()
    )
    data = []
    for r in records:
        days_left = (r.end_date - today).days
        status = "active"
        if days_left < 0:
            status = "expired"
        elif days_left <= 30:
            status = "expiring_soon"
        data.append(
            {
                "id": r.id,
                "start_date": r.start_date.isoformat() if r.start_date else None,
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "company": r.insurance_company.name if r.insurance_company else None,
                "type": r.insurance_type.name if r.insurance_type else None,
                "policy_number": r.policy_number,
                "amount": float(r.amount) if r.amount is not None else None,
                "note": r.note,
                "status": status,
            }
        )
    return jsonify(data)


def _apply_insurance_form(record, form):
    record.start_date = _parse_date(form.get("start_date"))
    record.end_date = _parse_date(form.get("end_date"))
    record.insurance_company_id = _parse_int(form.get("insurance_company_id"))
    record.insurance_type_id = _parse_int(form.get("insurance_type_id"))
    record.policy_number = form.get("policy_number", "").strip()
    record.amount = _parse_decimal(form.get("amount"))
    record.note = form.get("note", "").strip()


def _validate_insurance_form(form, employee_id, exclude_id=None):
    new_start = _parse_date(form.get("start_date"))
    new_end = _parse_date(form.get("end_date"))
    if not new_start or not new_end:
        return "Başlama və bitmə tarixi mütləqdir."
    if new_end < new_start:
        return "Bitmə tarixi başlama tarixindən əvvəl ola bilməz."
    existing = InsurancePolicy.query.filter_by(employee_id=employee_id).all()
    conflict = find_overlapping(
        existing,
        new_start,
        new_end,
        exclude_id=exclude_id,
        start_attr="start_date",
        end_attr="end_date",
    )
    if conflict:
        return (
            f"Tarix aralığı mövcud sığorta qeydi ilə kəsişir "
            f"({conflict.start_date} — {conflict.end_date}). Zəhmət olmasa tarixləri yoxlayın."
        )
    return None


@hr_bp.route("/<int:emp_id>/insurance/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_INSURANCE")
def add_insurance(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        error = _validate_insurance_form(request.form, employee_id=emp_id)
        if error:
            flash(error, "danger")
            return render_form(
                "hr/insurance_form.html",
                employee=employee,
                record=None,
                **_insurance_form_choices(),
            )
        record = InsurancePolicy(employee_id=employee.id)
        _apply_insurance_form(record, request.form)
        db.session.add(record)
        db.session.commit()
        flash("Sığorta qeydi əlavə olundu.", "success")
        return modal_redirect("hr.insurance_list", emp_id=employee.id)
    return render_form(
        "hr/insurance_form.html",
        employee=employee,
        record=None,
        **_insurance_form_choices(),
    )


@hr_bp.route("/<int:emp_id>/insurance/edit/<int:record_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_INSURANCE")
def edit_insurance(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = InsurancePolicy.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    if request.method == "POST":
        error = _validate_insurance_form(
            request.form, employee_id=emp_id, exclude_id=record.id
        )
        if error:
            flash(error, "danger")
            return render_form(
                "hr/insurance_form.html",
                employee=employee,
                record=record,
                **_insurance_form_choices(),
            )
        _apply_insurance_form(record, request.form)
        db.session.commit()
        flash("Sığorta qeydi yeniləndi.", "success")
        return modal_redirect("hr.insurance_list", emp_id=employee.id)
    return render_form(
        "hr/insurance_form.html",
        employee=employee,
        record=record,
        **_insurance_form_choices(),
    )


@hr_bp.route("/<int:emp_id>/insurance/delete/<int:record_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_INSURANCE")
def delete_insurance(emp_id, record_id):
    record = InsurancePolicy.query.filter_by(
        id=record_id, employee_id=emp_id
    ).first_or_404()
    db.session.delete(record)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Sığorta qeydi silindi.", "info")
    return redirect(url_for("hr.insurance_list", emp_id=emp_id))


# ---------------------------------------------------------------------------
# Maaş kartları (SalaryCard)
# ---------------------------------------------------------------------------


@hr_bp.route("/<int:emp_id>/salary-cards")
@login_required
@permission_required(MODULE, "can_view")
def salary_card_list(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return render_template(
        "hr/salary_card_list.html",
        employee=employee,
        layout=_employee_page_layout(),
    )


@hr_bp.route("/<int:emp_id>/salary-cards/api/records")
@login_required
@permission_required(MODULE, "can_view")
def api_salary_cards(emp_id):
    today = datetime.utcnow().date()
    records = (
        SalaryCard.query.filter_by(employee_id=emp_id)
        .order_by(SalaryCard.valid_until.desc())
        .all()
    )
    data = []
    for r in records:
        status = "active"
        if r.valid_until:
            days_left = (r.valid_until - today).days
            if days_left < 0:
                status = "expired"
            elif days_left <= 30:
                status = "expiring_soon"
        data.append(
            {
                "id": r.id,
                "bank": r.bank.name if r.bank else None,
                "account_number": r.account_number,
                "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                "card_holder_name": r.card_holder_name,
                "note": r.note,
                "status": status,
            }
        )
    return jsonify(data)


def _apply_salary_card_form(record, form):
    record.bank_id = _parse_int(form.get("bank_id"))
    record.account_number = form.get("account_number", "").strip()
    record.valid_until = _parse_date(form.get("valid_until"))
    record.card_holder_name = form.get("card_holder_name", "").strip()
    record.note = form.get("note", "").strip()


@hr_bp.route("/<int:emp_id>/salary-cards/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_SALARY_CARD")
def add_salary_card(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    if request.method == "POST":
        record = SalaryCard(employee_id=employee.id)
        _apply_salary_card_form(record, request.form)
        db.session.add(record)
        db.session.commit()
        flash("Maaş kartı əlavə olundu.", "success")
        return modal_redirect("hr.salary_card_list", emp_id=employee.id)
    return render_form(
        "hr/salary_card_form.html",
        employee=employee,
        record=None,
        banks=_dict_options("bank"),
    )


@hr_bp.route("/<int:emp_id>/salary-cards/edit/<int:record_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_SALARY_CARD")
def edit_salary_card(emp_id, record_id):
    employee = Employee.query.get_or_404(emp_id)
    record = SalaryCard.query.filter_by(id=record_id, employee_id=emp_id).first_or_404()
    if request.method == "POST":
        _apply_salary_card_form(record, request.form)
        db.session.commit()
        flash("Maaş kartı yeniləndi.", "success")
        return modal_redirect("hr.salary_card_list", emp_id=employee.id)
    return render_form(
        "hr/salary_card_form.html",
        employee=employee,
        record=record,
        banks=_dict_options("bank"),
    )


@hr_bp.route("/<int:emp_id>/salary-cards/delete/<int:record_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_SALARY_CARD")
def delete_salary_card(emp_id, record_id):
    record = SalaryCard.query.filter_by(id=record_id, employee_id=emp_id).first_or_404()
    db.session.delete(record)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Maaş kartı silindi.", "info")
    return redirect(url_for("hr.salary_card_list", emp_id=emp_id))


# ---------------------------------------------------------------------------
# Sənədlər (Document) — this tab is just a thin wrapper around the
# GENERIC documents system (app.services.document_service +
# app.modules.documents.routes + templates/partials/documents_panel.html),
# shared with any other module (e.g. Tabel). See app/models/system/document.py.
# ---------------------------------------------------------------------------


@hr_bp.route("/<int:emp_id>/documents")
@login_required
@permission_required(MODULE, "can_view")
def document_list(emp_id):
    employee = Employee.query.get_or_404(emp_id)
    return render_template(
        "hr/document_list.html",
        employee=employee,
        layout=_employee_page_layout(),
    )