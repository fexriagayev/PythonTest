from flask import Blueprint, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime

from app import db
from app.models import Employee, TabelEmployeeRow
from app.utils.decorators import permission_required, log_action
from app.utils.modal import render_form, modal_redirect, is_modal_request
from app.utils.parsing import _parse_int

salary_bp = Blueprint("salary", __name__)
MODULE = "SALARY"


# =============================================================================
# Əməkhaqqı hesablanması (Payroll) — təsdiqlənmiş Tabel dövrləri üzrə
# =============================================================================

from app.models import TabelPeriod, PayrollRun, PayrollEntry, SalaryAddition, Order, DictionaryItem, PayrollTaxFormula
from app.models.payroll.tax_formula import CODES, CODE_NAMES, TEMPLATE_SCRIPTS, SIDE_BY_CODE
from app.services import payroll_service
from app.services.formula_engine import evaluate_formula, validate_formula, FormulaError
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


@salary_bp.route("/payroll/<int:period_id>/toggle-approval", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "TOGGLE_PAYROLL_APPROVAL")
def toggle_payroll_approval(period_id):
    """Təsdiqlə/Təsdiqi ləğv et — TƏK düymə, əməkhaqqının cari vəziyyətinə
    görə hansı əməliyyatın aparılacağını özü müəyyən edir (bax:
    payroll_periods.html-dəki tək "toggle" düyməsi)."""
    period = TabelPeriod.query.get_or_404(period_id)
    redirect_target = redirect(url_for("salary.list_payroll_periods", year=period.year, month=period.month))
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if not run:
        flash("Bu dövr üçün əməkhaqqı hesablanmayıb.", "danger")
        return redirect_target
    if run.is_finalized:
        run.is_finalized = False
        run.finalized_at = None
        db.session.commit()
        flash("Əməkhaqqı təsdiqi ləğv edildi.", "success")
    else:
        run.is_finalized = True
        run.finalized_at = datetime.utcnow()
        db.session.commit()
        flash("Əməkhaqqı təsdiqləndi.", "success")
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
            "total_deductions": (
                float(e.income_tax or 0) + float(e.dsmf_amount or 0)
                + float(e.unemployment_amount or 0) + float(e.medical_amount or 0)
                + float(e.deductions_total or 0)
            ) if e else 0,
            "net_total": float(e.net_total or 0) if e else 0,
            "employer_dsmf": float(e.employer_dsmf or 0) if e else 0,
            "employer_unemployment": float(e.employer_unemployment or 0) if e else 0,
            "employer_medical": float(e.employer_medical or 0) if e else 0,
            "employer_cost_total": float(e.employer_cost_total or 0) if e else 0,
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
    entry = PayrollEntry.query.get_or_404(entry_id)
    return render_form("salary/employee_additions.html", entry=entry)


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

    # Bu əməkdaşa (individual) yoxsa BÜTÜN əməkdaşlara (all) aid olduğu —
    # formdakı "scope" seçimindən oxunur (defolt: individual).
    scope = form.get("scope")
    addition.scope = scope if scope in ("individual", "all") else "individual"
    addition.employees = [employee] if addition.scope == "individual" and employee else []

    addition.valid_from = _parse_date(form.get("valid_from"))
    addition.valid_to = _parse_date(form.get("valid_to"))
    addition.order_id = _parse_int(form.get("order_id"))
    addition.note = form.get("note", "").strip()
    addition.is_active = bool(form.get("is_active"))
    return addition_type


def _recalculate_affected_entries(addition):
    """Bu əlavə/tutulmanın təsir etdiyi bütün YEKUNLAŞDIRILMAMIŞ (hələ
    təsdiqlənməmiş) PayrollEntry sətirlərini yenidən hesablayır: scope
    "all" olduqda BÜTÜN əməkdaşların cari dövrləri, "individual" olduqda
    isə YALNIZ həmin əməkdaşın dövrləri. Artıq təsdiqlənmiş (finalized)
    dövrlərə TOXUNULMUR — onlar dəyişməz qalmalıdır."""
    query = PayrollEntry.query.join(PayrollRun).filter(PayrollRun.is_finalized.is_(False))
    if addition.scope != "all":
        employee_ids = [e.id for e in addition.employees]
        if not employee_ids:
            return
        query = query.filter(PayrollEntry.employee_id.in_(employee_ids))
    for e in query.all():
        payroll_service.recalculate_entry(e)


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
        _recalculate_affected_entries(addition)
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
        _recalculate_affected_entries(addition)
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
        for e in PayrollEntry.query.join(PayrollRun).filter(
            PayrollRun.is_finalized.is_(False), PayrollEntry.employee_id == employee_id
        ).all():
            payroll_service.recalculate_entry(e)
        db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Əlavə/tutulma silindi.", "info")
    return redirect(url_for("salary.list_payroll_periods"))


# =============================================================================
# Vergi formulaları (gəlir vergisi, DSMF, işsizlik, İTS) — redaktə oluna
# bilən skriptlər. Bax: app.services.formula_engine (təhlükəsizlik/icazə
# verilən sintaksis) və app.models.payroll.tax_formula (default skriptlər).
# =============================================================================


# =============================================================================
# Vergi formulaları (gəlir vergisi, DSMF, işsizlik, İTS) — TARİXLİ VERSİYALAR
# kimi saxlanılır (qüvvəyə minmə/bitmə tarixi + tam tarixçə). Bax:
# app.services.formula_engine (təhlükəsizlik/icazə verilən sintaksis) və
# app.models.payroll.tax_formula (versiya modeli, default skriptlər).
# =============================================================================

from datetime import date, timedelta
from app.utils.parsing import _parse_date


def _save_new_formula_version(code, name, script, valid_from, valid_to, user_id, exclude_id=None):
    """Yeni (tarixli) formula versiyası yaradır/YENİLƏYİR (bax: exclude_id —
    redaktə zamanı versiyanın ÖZÜ ilə "üst-üstə düşmə" yoxlamasından
    çıxarılır). Mövcud versiyalarla ÜST-ÜSTƏ DÜŞMƏ olarsa rədd edir —
    İSTİSNA: yeni versiya indiyə qədər AÇIQ (valid_to=NULL, "hələ də
    qüvvədədir") olan versiyanı VAXT ETİBARİLƏ davam etdirirsə (yəni
    sadəcə "qanun dəyişdi, buradan etibarən yeni formula qüvvəyə minir"
    adi halıdırsa), köhnə versiyanı avtomatik bağlayır (onun valid_to-sunu
    yeni versiyanın valid_from-undan 1 gün əvvələ təyin edir)."""
    if valid_to is not None and valid_to < valid_from:
        raise ValueError("Bitmə tarixi başlama tarixindən əvvəl ola bilməz.")

    new_end = valid_to or date.max
    query = PayrollTaxFormula.query.filter_by(code=code)
    if exclude_id is not None:
        query = query.filter(PayrollTaxFormula.id != exclude_id)
    for row in query.all():
        row_end = row.valid_to or date.max
        overlaps = row.valid_from <= new_end and valid_from <= row_end
        if not overlaps:
            continue
        if row.valid_to is None and valid_from > row.valid_from:
            # Adi hal: qanun dəyişib, əvvəlki (açıq) versiya bu tarixdə bağlanır.
            row.valid_to = valid_from - timedelta(days=1)
            continue
        raise ValueError(
            "Bu tarix aralığı artıq mövcud bir versiya ilə üst-üstə düşür: "
            f"{row.valid_from.isoformat()} — {row.valid_to.isoformat() if row.valid_to else 'indiyədək'}."
        )

    return PayrollTaxFormula(
        code=code, name=name, script=script,
        valid_from=valid_from, valid_to=valid_to, created_by_id=user_id,
    )


@salary_bp.route("/tax-formulas")
@login_required
@permission_required(MODULE, "can_view")
def list_tax_formulas():
    # Köhnə (versiyalı formaya keçirilməzdən əvvəl yaradılmış) sətirləri
    # təmir edir — bax: PayrollTaxFormula.heal_legacy_rows(). HEÇ bir
    # avtomatik "default" sətir YARADILMIR — konfiqurasiya olunmayan kodlar
    # sadəcə "konfiqurasiya olunmayıb" kimi göstərilir (bax: current=None).
    PayrollTaxFormula.heal_legacy_rows()
    employee_items = []
    employer_items = []
    for code, name, side, _script in CODES:
        current = PayrollTaxFormula.current_version(code)
        history = PayrollTaxFormula.history_for_code(code)
        item = {
            "code": code,
            "name": name,
            "current": current,
            "history_count": len(history),
        }
        (employee_items if side == "employee" else employer_items).append(item)
    from flask import render_template
    return render_template(
        "salary/tax_formulas.html",
        employee_items=employee_items, employer_items=employer_items,
    )


@salary_bp.route("/tax-formulas/<string:code>/history")
@login_required
@permission_required(MODULE, "can_view")
def tax_formula_history(code):
    PayrollTaxFormula.heal_legacy_rows()
    if code not in CODE_NAMES:
        from flask import abort
        abort(404)
    versions = PayrollTaxFormula.history_for_code(code)
    return render_form(
        "salary/tax_formula_history.html",
        code=code, name=CODE_NAMES[code], versions=versions, today=date.today(),
    )


@salary_bp.route("/tax-formulas/<string:code>/add-version", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "ADD_TAX_FORMULA_VERSION")
def add_tax_formula_version(code):
    PayrollTaxFormula.heal_legacy_rows()
    if code not in CODE_NAMES:
        from flask import abort
        abort(404)
    name = CODE_NAMES[code]
    current = PayrollTaxFormula.current_version(code)
    # Skript üçün başlanğıc mətn: mövcud (bu gün qüvvədə olan) versiya
    # varsa ondan davam edilir; yoxdursa, redaktə etməyə başlamaq üçün
    # bir NÜMUNƏ (TEMPLATE) göstərilir — bu, SAXLANANDA istifadə olunan
    # "gizli default" DEYİL, sadəcə boş bir mətn qutusu əvəzinə əlverişli
    # bir başlanğıc nöqtəsidir.
    starter_script = current.script if current else TEMPLATE_SCRIPTS[code]
    # Yeni versiya defolt olaraq SABAHDAN başlayır (bu gündən deyil) —
    # "bu gün üçün qüvvədə olan" hesablamaların bu redaktə zamanı,
    # yarımçıq/sınaq mərhələsində qəflətən dəyişməsinin qarşısını almaq
    # üçün. İstifadəçi istənilən tarixi seçə bilər (o cümlədən keçmiş bir
    # tarixi — tarixçəyə boşluq doldurmaq üçün).
    default_valid_from = date.today() + timedelta(days=1)

    if request.method == "POST":
        script = request.form.get("script", "")
        valid_from = _parse_date(request.form.get("valid_from"))
        valid_to = _parse_date(request.form.get("valid_to"))
        error = None
        if not valid_from:
            error = "Başlama tarixi mütləqdir."
        else:
            try:
                validate_formula(script)
            except FormulaError as e:
                error = f"Formula saxlanılmadı: {e}"
        version = None
        if not error:
            try:
                version = _save_new_formula_version(code, name, script, valid_from, valid_to, current_user.id)
            except ValueError as e:
                error = str(e)
        if error:
            flash(error, "danger")
            return render_form(
                "salary/tax_formula_form.html", code=code, name=name,
                script=script, valid_from=request.form.get("valid_from"),
                valid_to=request.form.get("valid_to"), version=None,
            )
        db.session.add(version)
        db.session.commit()
        flash(f"'{name}' üçün yeni formula versiyası əlavə olundu.", "success")
        return modal_redirect("salary.list_tax_formulas")

    return render_form(
        "salary/tax_formula_form.html", code=code, name=name,
        script=starter_script, valid_from=default_valid_from.isoformat(), valid_to="", version=None,
    )


@salary_bp.route("/tax-formulas/version/<int:version_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_TAX_FORMULA_VERSION")
def edit_tax_formula_version(version_id):
    version = PayrollTaxFormula.query.get_or_404(version_id)
    code, name = version.code, version.name

    if request.method == "POST":
        script = request.form.get("script", "")
        valid_from = _parse_date(request.form.get("valid_from"))
        valid_to = _parse_date(request.form.get("valid_to"))
        error = None
        if not valid_from:
            error = "Başlama tarixi mütləqdir."
        else:
            try:
                validate_formula(script)
            except FormulaError as e:
                error = f"Formula saxlanılmadı: {e}"
        if not error:
            try:
                # exclude_id=version.id: bu versiyanın ÖZÜ ilə "üst-üstə
                # düşmə" yoxlaması aparılmır — yalnız DİGƏR versiyalarla.
                _save_new_formula_version(
                    code, name, script, valid_from, valid_to,
                    current_user.id, exclude_id=version.id,
                )
            except ValueError as e:
                error = str(e)
        if error:
            flash(error, "danger")
            return render_form(
                "salary/tax_formula_form.html", code=code, name=name,
                script=script, valid_from=request.form.get("valid_from"),
                valid_to=request.form.get("valid_to"), version=version,
            )
        version.script = script
        version.valid_from = valid_from
        version.valid_to = valid_to
        version.updated_by_id = current_user.id
        db.session.commit()
        flash(f"'{name}' versiyası ({valid_from.strftime('%d.%m.%Y')}) yeniləndi.", "success")
        return modal_redirect("salary.tax_formula_history", code=code)

    return render_form(
        "salary/tax_formula_form.html", code=code, name=name,
        script=version.script,
        valid_from=version.valid_from.isoformat() if version.valid_from else "",
        valid_to=version.valid_to.isoformat() if version.valid_to else "",
        version=version,
    )


@salary_bp.route("/tax-formulas/version/<int:version_id>/delete", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_TAX_FORMULA_VERSION")
def delete_tax_formula_version(version_id):
    version = PayrollTaxFormula.query.get_or_404(version_id)
    code = version.code
    db.session.delete(version)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Formula versiyası silindi.", "info")
    return redirect(url_for("salary.tax_formula_history", code=code))


@salary_bp.route("/tax-formulas/test", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
def test_tax_formula():
    """"Vergi formulaları" redaktə pəncərəsindəki "Nəticəni hesabla"
    düyməsi üçün — SAXLAMADAN, cari (hələ yadda saxlanılmamış) skripti
    nümunə bir GROSS dəyəri ilə sınayır."""
    script = (request.get_json(silent=True) or {}).get("script", "")
    gross = (request.get_json(silent=True) or {}).get("gross")
    try:
        gross_val = float(gross)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Gross ədəd olmalıdır."})
    try:
        result = evaluate_formula(script, gross_val)
    except FormulaError as e:
        return jsonify({"success": False, "error": str(e)})
    return jsonify({"success": True, "result": round(result, 2)})
