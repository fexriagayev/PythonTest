from flask import Blueprint, request, jsonify, flash
from flask_login import login_required, current_user
from datetime import datetime

from app import db
from app.utils.contract_sort import sort_employees_by_contract, contract_numbers_by_employee, sort_rows_by_contract
from app.models import Employee, Obyekt, Briqada, BriqadaWorkPeriod, BriqadaWorkEntry
from app.models.hr.briqada_work import AZ_MONTH_NAMES, RUN_TYPES
from app.utils.decorators import permission_required, log_action
from app.utils.modal import render_form, modal_redirect, is_modal_request
from app.utils.parsing import _parse_date, _parse_int, _parse_decimal
from app.services import briqada_work_service

sites_bp = Blueprint("sites", __name__)
MODULE = "SITES"


# =============================================================================
# Obyektlər
# =============================================================================


@sites_bp.route("/obyekts")
@login_required
@permission_required(MODULE, "can_view")
def list_obyekts():
    from flask import render_template
    return render_template("sites/obyekt_list.html")


@sites_bp.route("/obyekts/api/items")
@login_required
@permission_required(MODULE, "can_view")
def api_obyekts():
    items = Obyekt.query.order_by(Obyekt.priority.desc(), Obyekt.name).all()
    return jsonify([
        {
            "id": o.id,
            "name": o.name,
            "start_date": o.start_date.isoformat() if o.start_date else None,
            "end_date": o.end_date.isoformat() if o.end_date else None,
            "is_active": o.is_active,
            "priority": o.priority,
            "owner_name": o.owner.name if o.owner else None,
        }
        for o in items
    ])


def _apply_obyekt_form(obyekt, form):
    obyekt.name = form.get("name", "").strip()
    obyekt.start_date = _parse_date(form.get("start_date"))
    obyekt.end_date = _parse_date(form.get("end_date"))
    obyekt.is_active = bool(form.get("is_active"))
    obyekt.priority = _parse_int(form.get("priority")) or 0
    owner_id = _parse_int(form.get("owner_id"))
    obyekt.owner_id = owner_id if owner_id else None


def _validate_obyekt(obyekt):
    if not obyekt.name:
        return "Ad mütləqdir."
    if obyekt.end_date and obyekt.start_date and obyekt.end_date < obyekt.start_date:
        return "Bitmə tarixi başlama tarixindən əvvəl ola bilməz."
    if obyekt.owner_id and obyekt.id and obyekt.owner_id == obyekt.id:
        return "Obyekt öz-özünün valideyni ola bilməz."
    return None


def _obyekt_choices(exclude_id=None):
    q = Obyekt.query.order_by(Obyekt.name)
    if exclude_id:
        q = q.filter(Obyekt.id != exclude_id)
    return q.all()


@sites_bp.route("/obyekts/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_OBYEKT")
def add_obyekt():
    if request.method == "POST":
        obyekt = Obyekt()
        _apply_obyekt_form(obyekt, request.form)
        error = _validate_obyekt(obyekt)
        if error:
            flash(error, "danger")
            return render_form("sites/obyekt_form.html", obyekt=obyekt, owners=_obyekt_choices())
        db.session.add(obyekt)
        db.session.commit()
        flash("Obyekt əlavə olundu.", "success")
        return modal_redirect("sites.list_obyekts")
    return render_form("sites/obyekt_form.html", obyekt=None, owners=_obyekt_choices())


@sites_bp.route("/obyekts/edit/<int:obyekt_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_OBYEKT")
def edit_obyekt(obyekt_id):
    obyekt = Obyekt.query.get_or_404(obyekt_id)
    if request.method == "POST":
        _apply_obyekt_form(obyekt, request.form)
        error = _validate_obyekt(obyekt)
        if error:
            flash(error, "danger")
            # VACİB: `obyekt` artıq DB-də mövcud (persistent) bir obyektdir —
            # yuxarıdakı _apply_obyekt_form onu YADDAŞDA artıq dəyişdirib.
            # `_obyekt_choices()` çağırışı YENİ bir sorğu olduğu üçün
            # SQLAlchemy-nin AUTOFLUSH-u bu ETİBARSIZ dəyişikliyi (məs.
            # "özü öz valideyni") COMMIT olmadan belə faktiki DB-yə
            # YAZA BİLƏR. `rollback()` bunu ehtiyatla geri alır.
            db.session.rollback()
            return render_form("sites/obyekt_form.html", obyekt=obyekt, owners=_obyekt_choices(exclude_id=obyekt.id))
        db.session.commit()
        flash("Obyekt yeniləndi.", "success")
        return modal_redirect("sites.list_obyekts")
    return render_form("sites/obyekt_form.html", obyekt=obyekt, owners=_obyekt_choices(exclude_id=obyekt.id))


@sites_bp.route("/obyekts/delete/<int:obyekt_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_OBYEKT")
def delete_obyekt(obyekt_id):
    obyekt = Obyekt.query.get_or_404(obyekt_id)
    if obyekt.sub_obyekts:
        error = "Bu obyektin alt-obyektləri var — əvvəlcə onları silin və ya başqa obyektə keçirin."
        if is_modal_request():
            return jsonify({"success": False, "error": error}), 400
        flash(error, "danger")
        return modal_redirect("sites.list_obyekts")
    db.session.delete(obyekt)
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Obyekt silindi.", "info")
    return modal_redirect("sites.list_obyekts")


# =============================================================================
# Briqadalar
# =============================================================================


class BriqadaGroup:
    """Eyni `group_no`-ya aid bütün Briqada sətirlərini (bax: modeldəki
    qeyd — HƏR ÜZV öz sətridir) TƏK bir "briqada" kimi görünəcək şəkildə
    saran yüngül wrapper (DB modeli DEYİL) — siyahı/redaktə/silmə bu
    səviyyədə işləyir, `id` xüsusiyyəti `group_no`-nu göstərir."""

    def __init__(self, rows):
        self.rows = rows
        first = rows[0]
        self.group_no = first.group_no
        self.id = first.group_no
        self.header_id = first.header_id
        self.header = first.header
        self.start_date = first.start_date
        self.end_date = first.end_date
        self.is_active = first.is_active
        self.priority = first.priority
        # Boş "yer tutucu" sətir (member_id VƏ member_name hər ikisi boş —
        # hələ heç bir üzv əlavə olunmayan təzə briqada üçün) real üzv
        # SAYILMIR.
        members = [r for r in rows if r.member_id or r.member_name]
        # Üzvlər Müqavilə N-ə (ƏDƏD kimi) görə; sistemdə əməkdaşı olmayan
        # (sərbəst adlı) üzvlərin nömrəsi yoxdur — sonda.
        numbers = contract_numbers_by_employee([r.member_id for r in members])
        self.members = sort_rows_by_contract(
            members,
            lambda r: numbers.get(r.member_id) if r.member_id else None,
            lambda r: r.member_display_name(),
        )


def _briqada_groups():
    rows = Briqada.query.order_by(
        Briqada.priority.desc(), Briqada.group_no.desc(), Briqada.id
    ).all()
    groups = {}
    order = []
    for r in rows:
        if r.group_no not in groups:
            groups[r.group_no] = []
            order.append(r.group_no)
        groups[r.group_no].append(r)
    return [BriqadaGroup(groups[g]) for g in order]


def _briqada_group(group_no):
    rows = Briqada.query.filter_by(group_no=group_no).order_by(Briqada.id).all()
    return BriqadaGroup(rows) if rows else None


def _next_group_no():
    max_no = db.session.query(db.func.max(Briqada.group_no)).scalar()
    return (max_no or 0) + 1


@sites_bp.route("/briqadalar")
@login_required
@permission_required(MODULE, "can_view")
def list_briqadalar():
    from flask import render_template
    return render_template("sites/briqada_list.html")


@sites_bp.route("/briqadalar/api/items")
@login_required
@permission_required(MODULE, "can_view")
def api_briqadalar():
    items = _briqada_groups()
    return jsonify([
        {
            "id": g.id,
            "header_name": g.header.full_name if g.header else None,
            "member_count": len(g.members),
            "members_preview": ", ".join(m.member_display_name() for m in g.members[:3]) + (
                ", ..." if len(g.members) > 3 else ""
            ),
            "start_date": g.start_date.isoformat() if g.start_date else None,
            "end_date": g.end_date.isoformat() if g.end_date else None,
            "is_active": g.is_active,
            "priority": g.priority,
        }
        for g in items
    ])


def _employee_choices():
    # Müqavilə N-ə (ƏDƏD kimi) görə — bax: app/utils/contract_sort.py
    return sort_employees_by_contract(Employee.query.filter_by(is_active=True).all())


def _briqada_shared_fields_from_form(form):
    return {
        "header_id": _parse_int(form.get("header_id")),
        "start_date": _parse_date(form.get("start_date")),
        "end_date": _parse_date(form.get("end_date")),
        "is_active": bool(form.get("is_active")),
        "priority": _parse_int(form.get("priority")) or 0,
    }


def _validate_briqada_fields(fields):
    if not fields["header_id"]:
        return "Sərkərdə (header) mütləqdir."
    if fields["end_date"] and fields["start_date"] and fields["end_date"] < fields["start_date"]:
        return "Bitmə tarixi başlama tarixindən əvvəl ola bilməz."
    return None


def _parse_briqada_members_from_form(form):
    """Formdan `member_employee_id[]`/`member_name[]` cütlərini oxuyub
    (eyni indeksli, hər sətir YA əməkdaş seçimi YA sərbəst ad, heç biri
    olmayan sətirlər KEÇİLİR, təkrar əməkdaşlar bir dəfə sayılır)
    [(member_id, member_name), ...] siyahısı qaytarır — boşdursa []."""
    employee_ids = form.getlist("member_employee_id[]")
    names = form.getlist("member_name[]")
    result = []
    seen = set()
    for i in range(max(len(employee_ids), len(names))):
        emp_id = _parse_int(employee_ids[i]) if i < len(employee_ids) else None
        name = (names[i] if i < len(names) else "").strip()
        if emp_id:
            if emp_id in seen:
                continue
            seen.add(emp_id)
            result.append((emp_id, None))
        elif name:
            result.append((None, name))
    return result


def _detach_briqada_work_entries(row):
    """Bir Briqada üzv SƏTRİ silinməzdən ƏVVƏL çağırılır: bu sətrə aid
    "Obyektlər üzrə görülən işlər" xanaları (BriqadaWorkEntry.briqada_id)
    varsa, onları İTİRMƏDƏN (tarix üzrə hesablanmış avans/yekun rəqəmləri
    saxlanılsın deyə) köçürür, ƏKS HALDA silinmə FK məhdudiyyətinə görə
    (bax: app/__init__.py IntegrityError -> 409) uğursuz olardı.

      - Sistemdəki əməkdaşa bağlı üzv (member_id): xana həmin əməkdaşa
        BİRBAŞA ("employee_id") bağlanır — bax: BriqadaWorkEntry modelinin
        iki mümkün sahib sxemi. Həmin dövr/obyektdə onun artıq "employee"
        xanası varsa (nadir), MƏBLƏĞLƏR CƏMLƏNİR, dublikat sətir silinir.
      - Sərbəst adla yazılmış (sistemdə əməkdaşı olmayan) üzv: köçürüləcək
        yer YOXDUR. Belə xananın datası varsa, silinməyə İCAZƏ VERİLMİR —
        ValueError qaldırılır (route bunu aydın mesajla flash edir);
        məlumatı olmayan sərbəst üzv problemsiz silinir.
    """
    entries = BriqadaWorkEntry.query.filter_by(briqada_id=row.id).all()
    if not entries:
        return
    if row.member_id is None:
        raise ValueError(
            f"\"{row.member_display_name()}\" üzvünün Obyektlər üzrə görülən işlər "
            "matrisində daxil edilmiş məbləği var. Sərbəst adla yazılmış (sistemdə "
            "əməkdaşı olmayan) üzv üçün bu məbləğ başqa yerə köçürülə bilmədiyindən, "
            "əvvəlcə həmin matrisdəki rəqəmləri silin, sonra üzvü çıxarın."
        )
    for e in entries:
        existing = BriqadaWorkEntry.query.filter_by(
            period_id=e.period_id, employee_id=row.member_id, obyekt_id=e.obyekt_id
        ).first()
        if existing:
            existing.amount = float(existing.amount or 0) + float(e.amount or 0)
            db.session.delete(e)
        else:
            e.briqada_id = None
            e.employee_id = row.member_id


def _sync_briqada_members(group, fields, members):
    """Briqadanı redaktə edərkən üzv sətirlərini (Briqada.id-lər DƏYİŞMƏDƏN
    qalsın deyə) UYĞUNLAŞDIRIR — köhnə "hamısını sil, yenidən yarat" üsulu
    ƏVƏZİNƏ: dəyişməyən üzvlərin sətri (və `id`-si) olduğu kimi qalır,
    yalnız HƏQİQƏTƏN çıxarılan üzvlər silinir (bax: _detach_briqada_work_entries
    — silinməzdən əvvəl onların "Obyektlər üzrə görülən işlər" datası
    köçürülür). Bu, İKİ problemi həll edir: (1) bir üzvü silmək istəyəndə,
    matrisdə HEÇ BİR ƏLAQƏSİ olmayan DİGƏR üzvlərin sətri boş yerə silinib
    yenidən yaranmır, ona görə onların `briqada_id`-yə bağlı matris datası
    da pozulmur; (2) HƏQİQƏTƏN silinən üzvün datası varsa, artıq FK xətası
    (409) yox, aydın mesajla İCAZƏ VERİLMİR."""
    existing = list(group.rows)
    existing_by_emp = {r.member_id: r for r in existing if r.member_id is not None}
    existing_freeform = [r for r in existing if r.member_id is None and r.member_name]
    existing_placeholder = next(
        (r for r in existing if r.member_id is None and not r.member_name), None
    )

    submitted = members or [(None, None)]
    keep_ids = set()

    for emp_id, name in submitted:
        row = None
        if emp_id is not None:
            row = existing_by_emp.pop(emp_id, None)
        elif name:
            for i, r in enumerate(existing_freeform):
                if r.member_name == name:
                    row = existing_freeform.pop(i)
                    break
        else:
            row = existing_placeholder
            existing_placeholder = None

        if row is not None:
            for k, v in fields.items():
                setattr(row, k, v)
            row.member_id = emp_id
            row.member_name = name
            keep_ids.add(row.id)
        else:
            db.session.add(Briqada(group_no=group.group_no, member_id=emp_id, member_name=name, **fields))

    # Submitted siyahıda uyğunu tapılmayan (əvvəlki placeholder daxil)
    # sətirlər HƏQİQƏTƏN çıxarılıb — silinməzdən əvvəl datası köçürülür.
    to_remove = [r for r in existing if r.id not in keep_ids]
    for row in to_remove:
        _detach_briqada_work_entries(row)
        db.session.delete(row)


@sites_bp.route("/briqadalar/add", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "ADD_BRIQADA")
def add_briqada():
    if request.method == "POST":
        fields = _briqada_shared_fields_from_form(request.form)
        error = _validate_briqada_fields(fields)
        if error:
            flash(error, "danger")
            fake = type("_F", (), fields)()
            fake.id = None
            fake.members = []
            return render_form("sites/briqada_form.html", briqada=fake, employees=_employee_choices())
        members = _parse_briqada_members_from_form(request.form)
        group_no = _next_group_no()
        rows_to_add = members or [(None, None)]  # üzv yoxdursa, briqada boş "yer tutucu" ilə yaranır
        for emp_id, name in rows_to_add:
            db.session.add(Briqada(group_no=group_no, member_id=emp_id, member_name=name, **fields))
        db.session.commit()
        flash("Briqada əlavə olundu.", "success")
        return modal_redirect("sites.list_briqadalar")
    return render_form("sites/briqada_form.html", briqada=None, employees=_employee_choices())


@sites_bp.route("/briqadalar/edit/<int:briqada_id>", methods=["GET", "POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "EDIT_BRIQADA")
def edit_briqada(briqada_id):
    group = _briqada_group(briqada_id)
    if not group:
        from flask import abort
        abort(404)
    if request.method == "POST":
        fields = _briqada_shared_fields_from_form(request.form)
        error = _validate_briqada_fields(fields)
        if error:
            flash(error, "danger")
            return render_form("sites/briqada_form.html", briqada=group, employees=_employee_choices())
        members = _parse_briqada_members_from_form(request.form)
        # Dəyişməyən üzvlərin sətri (id-si) olduğu kimi qalır — bax:
        # _sync_briqada_members. Yalnız HƏQİQƏTƏN çıxarılan üzv üçün
        # (və onun "Obyektlər üzrə görülən işlər" datası köçürülə
        # bilmirsə) aydın xəta veriləcək.
        try:
            _sync_briqada_members(group, fields, members)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_form("sites/briqada_form.html", briqada=group, employees=_employee_choices())
        db.session.commit()
        flash("Briqada yeniləndi.", "success")
        return modal_redirect("sites.list_briqadalar")
    return render_form("sites/briqada_form.html", briqada=group, employees=_employee_choices())


@sites_bp.route("/briqadalar/delete/<int:briqada_id>", methods=["POST"])
@login_required
@permission_required(MODULE, "can_delete")
@log_action(MODULE, "DELETE_BRIQADA")
def delete_briqada(briqada_id):
    group = _briqada_group(briqada_id)
    if not group:
        from flask import abort
        abort(404)
    try:
        for row in group.rows:
            _detach_briqada_work_entries(row)
            db.session.delete(row)
    except ValueError as exc:
        db.session.rollback()
        message = str(exc)
        if is_modal_request():
            return jsonify({"success": False, "error": message}), 400
        flash(message, "danger")
        return modal_redirect("sites.list_briqadalar")
    db.session.commit()
    if is_modal_request():
        return jsonify({"success": True})
    flash("Briqada silindi.", "info")
    return modal_redirect("sites.list_briqadalar")


# =============================================================================
# Obyektlər üzrə görülən işlər (Briqada Work matrisi) — ayda 2 dəfə
# (avans/yekun) doldurulan, ayrıca təsdiqlənən matris. Bax:
# app.services.briqada_work_service (struktur/hesablama) və
# app.models.hr.briqada_work (BriqadaWorkPeriod/BriqadaWorkEntry).
# =============================================================================


@sites_bp.route("/briqada-work")
@login_required
@permission_required(MODULE, "can_view")
def list_briqada_work():
    from flask import render_template
    return render_template("sites/briqada_work_list.html")


@sites_bp.route("/briqada-work/api/items")
@login_required
@permission_required(MODULE, "can_view")
def api_briqada_work_periods():
    periods = BriqadaWorkPeriod.query.order_by(
        BriqadaWorkPeriod.year.desc(), BriqadaWorkPeriod.month.desc(),
        BriqadaWorkPeriod.run_type,
    ).all()
    return jsonify([
        {
            "id": p.id,
            "label": p.label,
            "year": p.year,
            "month": p.month,
            "run_type": p.run_type,
            "is_approved": p.is_approved,
        }
        for p in periods
    ])


@sites_bp.route("/briqada-work/lookup")
@login_required
@permission_required(MODULE, "can_view")
def lookup_briqada_work_period():
    year = _parse_int(request.args.get("year"))
    month = _parse_int(request.args.get("month"))
    run_type = request.args.get("run_type")
    period = BriqadaWorkPeriod.query.filter_by(year=year, month=month, run_type=run_type).first()
    return jsonify({"exists": bool(period), "period_id": period.id if period else None})


@sites_bp.route("/briqada-work/create", methods=["POST"])
@login_required
@permission_required(MODULE, "can_add")
@log_action(MODULE, "CREATE_BRIQADA_WORK_PERIOD")
def create_briqada_work_period():
    payload = request.get_json(silent=True) or {}
    year = _parse_int(payload.get("year"))
    month = _parse_int(payload.get("month"))
    run_type = payload.get("run_type")
    if not year or not month or run_type not in dict(RUN_TYPES):
        return jsonify({"success": False, "error": "Il, ay və dövr növü mütləqdir."}), 400
    existing = BriqadaWorkPeriod.query.filter_by(year=year, month=month, run_type=run_type).first()
    if existing:
        return jsonify({"success": True, "period_id": existing.id})
    period = BriqadaWorkPeriod(year=year, month=month, run_type=run_type)
    db.session.add(period)
    db.session.commit()
    return jsonify({"success": True, "period_id": period.id})


@sites_bp.route("/briqada-work/add")
@login_required
@permission_required(MODULE, "can_add")
def add_briqada_work_period():
    today = datetime.today()
    return render_form(
        "sites/briqada_work_modal.html", period=None,
        default_year=today.year, default_month=today.month,
        month_names=AZ_MONTH_NAMES, run_types=RUN_TYPES,
    )


@sites_bp.route("/briqada-work/<int:period_id>/edit")
@login_required
@permission_required(MODULE, "can_view")
def edit_briqada_work_period(period_id):
    period = BriqadaWorkPeriod.query.get_or_404(period_id)
    return render_form(
        "sites/briqada_work_modal.html", period=period,
        default_year=period.year, default_month=period.month,
        month_names=AZ_MONTH_NAMES, run_types=RUN_TYPES,
    )


@sites_bp.route("/briqada-work/<int:period_id>/api/matrix")
@login_required
@permission_required(MODULE, "can_view")
def api_briqada_work_matrix(period_id):
    period = BriqadaWorkPeriod.query.get_or_404(period_id)
    return jsonify(briqada_work_service.matrix_data(period))


@sites_bp.route("/briqada-work/<int:period_id>/cell", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
def set_briqada_work_cell(period_id):
    period = BriqadaWorkPeriod.query.get_or_404(period_id)
    if period.is_approved:
        return jsonify({"success": False, "error": "Bu dövr artıq TƏSDİQLƏNİB — dəyişiklik edilə bilməz."}), 400
    payload = request.get_json(silent=True) or {}
    briqada_id = _parse_int(payload.get("briqada_id"))
    employee_id = _parse_int(payload.get("employee_id"))
    obyekt_id = _parse_int(payload.get("obyekt_id"))
    amount = _parse_decimal(payload.get("amount"))
    if not obyekt_id or not (briqada_id or employee_id):
        return jsonify({"success": False, "error": "briqada_id/employee_id və obyekt_id mütləqdir."}), 400
    key_type = "briqada" if briqada_id else "employee"
    key_id = briqada_id if briqada_id else employee_id
    briqada_work_service.set_cell(period, key_type, key_id, obyekt_id, amount)
    db.session.commit()
    return jsonify({"success": True})


@sites_bp.route("/briqada-work/<int:period_id>/reset", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "RESET_BRIQADA_WORK_PERIOD")
def reset_briqada_work_period(period_id):
    period = BriqadaWorkPeriod.query.get_or_404(period_id)
    if period.is_approved:
        return jsonify({"success": False, "error": "Bu dövr artıq TƏSDİQLƏNİB — sıfırlana bilməz."}), 400
    for entry in list(period.entries):
        db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True})


@sites_bp.route("/briqada-work/<int:period_id>/approve", methods=["POST"])
@login_required
@permission_required(MODULE, "can_edit")
@log_action(MODULE, "APPROVE_BRIQADA_WORK_PERIOD")
def approve_briqada_work_period(period_id):
    period = BriqadaWorkPeriod.query.get_or_404(period_id)
    period.is_approved = not period.is_approved
    period.approved_at = datetime.utcnow() if period.is_approved else None
    period.approved_by_id = current_user.id if period.is_approved else None
    db.session.commit()
    # Bu ayın əməkhaqqısı artıq hesablanıb, amma hələ təsdiqlənməyibsə —
    # obyekt işi məbləğləri (net -> gross) dərhal yenilənsin. Təsdiqlənmiş
    # əməkhaqqıya toxunulmur.
    from app.services import payroll_service
    refreshed = payroll_service.refresh_unfinalized_payroll(period.year, period.month)
    if refreshed:
        db.session.commit()
    return jsonify({
        "success": True, "is_approved": period.is_approved,
        "payroll_refreshed": bool(refreshed),
    })