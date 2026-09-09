from datetime import date, datetime

from flask import Blueprint, request, jsonify, render_template, abort
from flask_login import login_required

from app import db
from app.models import TabelPeriod, TabelEmployeeRow
from app.utils.decorators import permission_required, log_action
from app.utils.modal import render_form
from app.utils.parsing import _parse_int
from app.services.tabel_service import month_bounds, generate_period, cycle_cell, preview_rows
from app.services.document_service import delete_all_documents_for_owner

tabel_bp = Blueprint("tabel", __name__)
MODULE = "TABEL"


# ---------------------------------------------------------------------------
# Dövrlərin siyahısı ("Tabellər")
# ---------------------------------------------------------------------------


@tabel_bp.route("/")
@login_required
@permission_required(MODULE, "can_view")
def list_periods():
    return render_template("tabel/list.html")


@tabel_bp.route("/api/periods")
@login_required
@permission_required(MODULE, "can_view")
def api_periods():
    periods = TabelPeriod.query.order_by(
        TabelPeriod.year.desc(), TabelPeriod.month.desc()
    ).all()
    data = [{"id": p.id, "label": p.label, "is_approved": p.is_approved} for p in periods]
    return jsonify(data)


@tabel_bp.route("/<int:period_id>/delete", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_PERIOD")
def delete_period(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    from app.models import PayrollRun
    run = PayrollRun.query.filter_by(period_id=period.id).first()
    if run:
        message = (
            "Bu dövr üçün əməkhaqqı təsdiqlənib, dövr silinə bilməz."
            if run.is_finalized else
            "Bu dövr üçün əməkhaqqı hesablanıb. Dövrü silmək üçün əvvəlcə tabel təsdiqini geri alın (bu, hesablanmış əməkhaqqını da siləcək)."
        )
        return jsonify({"success": False, "error": message}), 400
    delete_all_documents_for_owner("tabel_period", period.id)
    db.session.delete(period)
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Vahid "Tabel dövrü" modalı — həm YENİ dövr seçimi, həm də MÖVCUD dövrün
# generasiyası/matrisi/sənədləri eyni modalda (bax: tabel/period_modal.html).
# ---------------------------------------------------------------------------


@tabel_bp.route("/add")
@login_required
@permission_required(MODULE, "can_add")
def add_period():
    """Modal fraqmenti — YENİ dövr: Ay/İl seçimi açıqdır, hələ heç bir
    TabelPeriod yaradılmayıb."""
    today = date.today()
    return render_form(
        "tabel/period_modal.html",
        period=None,
        default_year=today.year,
        default_month=today.month,
        days_in_month=None,
        month_names=TabelPeriod.MONTH_NAMES_AZ,
    )


@tabel_bp.route("/edit/<int:period_id>")
@login_required
@permission_required(MODULE, "can_view")
def period_detail(period_id):
    """Modal fraqmenti — MÖVCUD dövr: Ay/İl sabitdir (dəyişdirilə bilmir),
    matris + Sənədlər tabı göstərilir."""
    period = TabelPeriod.query.get_or_404(period_id)
    _, _, days_in_month = month_bounds(period.year, period.month)
    return render_form(
        "tabel/period_modal.html",
        period=period,
        default_year=period.year,
        default_month=period.month,
        days_in_month=days_in_month,
        month_names=TabelPeriod.MONTH_NAMES_AZ,
    )


@tabel_bp.route("/preview")
@login_required
@permission_required(MODULE, "can_view")
def preview_period():
    """AJAX: TabelPeriod hələ yaradılmayıb — seçilmiş Ay/İl üçün əməkdaş
    sətirlərinin ÖNİZLƏMƏSİNİ (bax: tabel_service.preview_rows) qaytarır.
    "Yeni dövr" formasında Ay/İl seçimi hər dəyişəndə çağırılır ki,
    istifadəçi "Generasiya et"-ə basmazdan əvvəl də əməkdaş siyahısını
    görsün. Cavab api_matrix ilə EYNİ formatdadır (is_generated=False)."""
    year = _parse_int(request.args.get("year"))
    month = _parse_int(request.args.get("month"))
    if not year or not month or not (1 <= month <= 12):
        return jsonify({"days_in_month": 30, "is_generated": False, "is_approved": False, "rows": []})
    _, _, days_in_month = month_bounds(year, month)
    return jsonify({
        "days_in_month": days_in_month,
        "is_generated": False,
        "is_approved": False,
        "rows": preview_rows(year, month),
    })


@tabel_bp.route("/lookup")
@login_required
@permission_required(MODULE, "can_view")
def lookup_period():
    """AJAX: seçilmiş Ay/İl üçün TabelPeriod artıq mövcuddursa, onun ID-sini
    qaytarır — modal JS-i bununla avtomatik mövcud tabelə keçir (yeni
    dublikat dövr yaratmadan)."""
    year = _parse_int(request.args.get("year"))
    month = _parse_int(request.args.get("month"))
    period = TabelPeriod.query.filter_by(year=year, month=month).first() if year and month else None
    return jsonify({"exists": bool(period), "period_id": period.id if period else None})


@tabel_bp.route("/create", methods=["POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_PERIOD")
def create_period():
    """AJAX: yeni TabelPeriod yaradır (yalnız hələ mövcud olmayan Ay/İl
    üçün) — "Generasiya et" düyməsi bunu generate-dən əvvəl çağırır."""
    payload = request.get_json(silent=True) or {}
    year = _parse_int(payload.get("year"))
    month = _parse_int(payload.get("month"))
    if not year or not month or not (1 <= month <= 12):
        return jsonify({"success": False, "error": "Ay/İl düzgün deyil."}), 400

    existing = TabelPeriod.query.filter_by(year=year, month=month).first()
    if existing:
        return jsonify({"success": True, "period_id": existing.id})

    period = TabelPeriod(year=year, month=month)
    db.session.add(period)
    db.session.commit()
    return jsonify({"success": True, "period_id": period.id})


# ---------------------------------------------------------------------------
# Matris API-ları
# ---------------------------------------------------------------------------


@tabel_bp.route("/<int:period_id>/api/matrix")
@login_required
@permission_required(MODULE, "can_view")
def api_matrix(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    _, _, days_in_month = month_bounds(period.year, period.month)
    rows = (
        TabelEmployeeRow.query.filter_by(period_id=period.id)
        .order_by(TabelEmployeeRow.row_no)
        .all()
    )
    data = {
        "days_in_month": days_in_month,
        "is_generated": period.is_generated,
        "is_approved": period.is_approved,
        "rows": [
            {
                "id": r.id,
                "full_name": r.full_name_snapshot,
                "position": r.position_snapshot,
                "contract_number": r.contract_number_snapshot,
                "day_marks": r.day_marks or {},
                "work_days_count": r.work_days_count(),
            }
            for r in rows
        ],
    }
    return jsonify(data)


@tabel_bp.route("/<int:period_id>/generate", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "GENERATE_PERIOD")
def generate(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    if period.is_approved:
        return jsonify({"success": False, "error": "Təsdiqlənmiş dövr üçün tabel yenidən generasiya edilə bilməz."}), 400
    generate_period(period)
    db.session.commit()
    return jsonify({"success": True})


@tabel_bp.route("/<int:period_id>/cell", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
def set_cell(period_id):
    period = TabelPeriod.query.get_or_404(period_id)
    if period.is_approved:
        return jsonify({"success": False, "error": "Təsdiqlənmiş tabeldə dəyişiklik edilə bilməz."}), 400

    payload = request.get_json(silent=True) or {}
    row_id = _parse_int(payload.get("row_id"))
    day = _parse_int(payload.get("day"))
    row = TabelEmployeeRow.query.filter_by(id=row_id, period_id=period.id).first()
    if not row or not day:
        abort(404)
    try:
        new_value = cycle_cell(row, day)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    db.session.commit()
    return jsonify(
        {"success": True, "value": new_value, "work_days_count": row.work_days_count()}
    )


@tabel_bp.route("/<int:period_id>/approve", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "APPROVE_PERIOD")
def toggle_approve(period_id):
    period = TabelPeriod.query.get_or_404(period_id)

    if period.is_approved:
        # Təsdiqi GERİ ALMAQ (unapprove) — bu, tabeli yenidən redaktə
        # edilə bilən hala qaytarır (generate/cell marşrutları YALNIZ
        # is_approved=False olduqda icazə verir). Ona görə bu, əməkhaqqı
        # üçün risk yaradan YEGANƏ keçid nöqtəsidir: əgər bu dövr üçün
        # əməkhaqqı artıq hesablanıbsa, tabel dəyişəcək amma əməkhaqqı
        # köhnə (indi səhv) qalacaq.
        from app.models import PayrollRun
        run = PayrollRun.query.filter_by(period_id=period.id).first()
        if run:
            if run.is_finalized:
                return jsonify({
                    "success": False,
                    "error": "Bu dövrün əməkhaqqısı artıq təsdiqlənib. Tabeldə dəyişiklik etmək üçün əvvəlcə əməkhaqqı təsdiqini geri almalısınız.",
                }), 400
            payload = request.get_json(silent=True) or {}
            if not payload.get("confirm_payroll_reset"):
                return jsonify({
                    "success": False,
                    "needs_confirmation": True,
                    "error": "Bu dövrə əməkhaqqı hesablanıb. Tabeldə dəyişiklik etsəniz, həmin əməkhaqqı sıfırlanacaq. Davam etmək istəyirsiniz?",
                }), 409
            # Təsdiqləndi — hesablanmış (amma təsdiqlənməmiş) əməkhaqqını sıfırla.
            db.session.delete(run)

    period.is_approved = not period.is_approved
    period.approved_at = datetime.utcnow() if period.is_approved else None
    db.session.commit()
    return jsonify({"success": True, "is_approved": period.is_approved})
