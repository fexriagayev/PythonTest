from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import DictionaryItem
from app.utils.decorators import log_action
from app.utils.modal import render_form, modal_redirect, is_modal_request

dict_bp = Blueprint("dictionaries", __name__)

VALID_MODULES = ["HR", "TABEL", "SALARY"]



def _find_dictionary_usage(item_id):
    """Return the first ORM reference to a DictionaryItem, if any.

    This is intentionally generic: new dictionary-backed FK fields are then
    protected automatically instead of requiring another hand-written check.
    """
    for mapper in db.Model.registry.mappers:
        model = mapper.class_
        if model is DictionaryItem:
            continue
        for column in mapper.columns:
            if any(fk.target_fullname == "dictionary_items.id" for fk in column.foreign_keys):
                if model.query.filter(column == item_id).first() is not None:
                    return model.__name__, column.name
    return None


def _check(module_code, field):
    if not current_user.has_perm(module_code, field):
        abort(403)


@dict_bp.route("/")
@login_required
def index():
    # Show only the module dictionaries the user has at least dict_view on
    visible = [m for m in VALID_MODULES if current_user.has_perm(m, "dict_view")]
    return render_template("dictionaries/index.html", visible_modules=visible)


@dict_bp.route("/<module_code>")
@login_required
def list_items(module_code):
    module_code = module_code.upper()
    if module_code not in VALID_MODULES:
        abort(404)
    _check(module_code, "dict_view")
    return render_template("dictionaries/list.html", module_code=module_code)


@dict_bp.route("/<module_code>/api/items")
@login_required
def api_items(module_code):
    module_code = module_code.upper()
    if module_code not in VALID_MODULES:
        abort(404)
    _check(module_code, "dict_view")
    items = DictionaryItem.query.filter_by(module_code=module_code).all()
    data = [{
        "id": i.id, "category": i.category, "name": i.name,
        "value": i.value, "is_active": i.is_active,
    } for i in items]
    return jsonify(data)


@dict_bp.route("/<module_code>/add", methods=["GET", "POST"])
@login_required
@log_action("DICTIONARY", "ADD")
def add_item(module_code):
    module_code = module_code.upper()
    if module_code not in VALID_MODULES:
        abort(404)
    _check(module_code, "dict_add")
    if request.method == "POST":
        item = DictionaryItem(
            module_code=module_code,
            category=request.form.get("category", "").strip(),
            name=request.form.get("name", "").strip(),
            value=request.form.get("value", "").strip(),
            is_active=bool(request.form.get("is_active")),
        )
        db.session.add(item)
        db.session.commit()
        flash("Kitabça qeydi əlavə olundu.", "success")
        return modal_redirect("dictionaries.list_items", module_code=module_code)
    return render_form("dictionaries/form.html", item=None, module_code=module_code)


@dict_bp.route("/<module_code>/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
@log_action("DICTIONARY", "EDIT")
def edit_item(module_code, item_id):
    module_code = module_code.upper()
    if module_code not in VALID_MODULES:
        abort(404)
    _check(module_code, "dict_edit")
    item = DictionaryItem.query.get_or_404(item_id)
    if request.method == "POST":
        item.category = request.form.get("category", "").strip()
        item.name = request.form.get("name", "").strip()
        item.value = request.form.get("value", "").strip()
        item.is_active = bool(request.form.get("is_active"))
        db.session.commit()
        flash("Kitabça qeydi yeniləndi.", "success")
        return modal_redirect("dictionaries.list_items", module_code=module_code)
    return render_form("dictionaries/form.html", item=item, module_code=module_code)


@dict_bp.route("/<module_code>/delete/<int:item_id>", methods=["POST"])
@login_required
@log_action("DICTIONARY", "DELETE")
def delete_item(module_code, item_id):
    module_code = module_code.upper()
    if module_code not in VALID_MODULES:
        abort(404)
    _check(module_code, "dict_delete")
    item = DictionaryItem.query.get_or_404(item_id)
    usage = _find_dictionary_usage(item.id)
    if usage:
        model_name, field_name = usage
        message = "Bu kitabça qeydi sistemdə istifadə olunur və silinə bilməz."
        if is_modal_request():
            return jsonify({"success": False, "error": message})
        flash(message, "danger")
        return redirect(url_for("dictionaries.list_items", module_code=module_code))
    try:
        db.session.delete(item)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        message = "Bu kitabça qeydi sistemdə istifadə olunur və silinə bilməz."
        if is_modal_request():
            return jsonify({"success": False, "error": message})
        flash(message, "danger")
        return redirect(url_for("dictionaries.list_items", module_code=module_code))
    if is_modal_request():
        return jsonify({"success": True})
    flash("Kitabça qeydi silindi.", "info")
    return redirect(url_for("dictionaries.list_items", module_code=module_code))
