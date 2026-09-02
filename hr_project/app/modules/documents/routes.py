"""Generic 'Sənədlər' routes — works for any owner_type registered in
app/services/document_service.py (currently: employee, tabel_period).

This blueprint is what templates/partials/documents_panel.html talks to.
Adding Sənədlər support to a brand-new module means adding one entry to
DOCUMENT_OWNERS there — nothing needs to change here.
"""

import os

from flask import Blueprint, request, redirect, url_for, flash, jsonify, abort, send_file
from flask_login import login_required, current_user

from app import db
from app.models import DictionaryItem
from app.utils.modal import render_form, modal_redirect, is_modal_request
from app.utils.parsing import _parse_int
from app.utils.logger import write_log
from app.services.document_service import (
    get_owner_config,
    list_documents,
    save_document,
    delete_document,
    document_file_path,
)

documents_bp = Blueprint("documents", __name__)


def _owner_or_404(owner_type, owner_id):
    """Validates owner_type is a known registry entry AND owner_id refers
    to a real row, returning (owner_config, owner_row)."""
    config = get_owner_config(owner_type)
    if not config:
        abort(404)
    owner_row = config.model.query.get_or_404(owner_id)
    return config, owner_row


def _require_perm(config, field):
    if not current_user.is_authenticated or not current_user.has_perm(
        config.permission_module, field
    ):
        abort(403)


def _dict_options(module_code, category):
    return (
        DictionaryItem.query.filter_by(
            module_code=module_code, category=category, is_active=True
        )
        .order_by(DictionaryItem.name)
        .all()
    )


def _back_url(config, owner_id):
    return url_for(config.back_endpoint, **{config.back_url_kwarg: owner_id})


@documents_bp.route("/<owner_type>/<int:owner_id>/api/records")
@login_required
def api_records(owner_type, owner_id):
    config, _owner = _owner_or_404(owner_type, owner_id)
    _require_perm(config, "can_view")
    records = list_documents(owner_type, owner_id)
    data = [
        {
            "id": d.id,
            "original_filename": d.original_filename,
            "document_type": d.document_type.name if d.document_type else None,
            "note": d.note,
            "uploaded_at": (
                d.uploaded_at.strftime("%Y-%m-%d %H:%M") if d.uploaded_at else None
            ),
        }
        for d in records
    ]
    return jsonify(data)


@documents_bp.route("/<owner_type>/<int:owner_id>/add", methods=["GET", "POST"])
@login_required
def add(owner_type, owner_id):
    config, owner_row = _owner_or_404(owner_type, owner_id)
    _require_perm(config, "can_add")
    doc_types = _dict_options(config.permission_module, "document_type")

    if request.method == "POST":
        file = request.files.get("file")
        doc = save_document(
            owner_type,
            owner_id,
            file,
            _parse_int(request.form.get("document_type_id")),
            request.form.get("note", ""),
        )
        if not doc:
            flash("Fayl seçilməyib.", "danger")
            return render_form(
                "partials/document_form.html",
                owner_type=owner_type,
                owner_id=owner_id,
                owner_module=config.permission_module,
                doc_types=doc_types,
                cancel_url=_back_url(config, owner_id),
            )
        db.session.commit()
        write_log(current_user, config.permission_module, "ADD_DOCUMENT",
                   description=f"{owner_type}#{owner_id}: {doc.original_filename}")
        flash("Sənəd əlavə olundu.", "success")
        return modal_redirect(config.back_endpoint, **{config.back_url_kwarg: owner_id})

    return render_form(
        "partials/document_form.html",
        owner_type=owner_type,
        owner_id=owner_id,
        owner_module=config.permission_module,
        doc_types=doc_types,
        cancel_url=_back_url(config, owner_id),
    )


@documents_bp.route("/<owner_type>/<int:owner_id>/<int:doc_id>/download")
@login_required
def download(owner_type, owner_id, doc_id):
    config, _owner = _owner_or_404(owner_type, owner_id)
    _require_perm(config, "can_view")
    doc = next((d for d in list_documents(owner_type, owner_id) if d.id == doc_id), None)
    if not doc:
        abort(404)
    path = document_file_path(doc)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=doc.original_filename)


@documents_bp.route("/<owner_type>/<int:owner_id>/<int:doc_id>/view")
@login_required
def view(owner_type, owner_id, doc_id):
    """Same file as download(), but shown inline (PDF/image/text) instead
    of forcing a download — used by the "Bax" (preview) row action."""
    config, _owner = _owner_or_404(owner_type, owner_id)
    _require_perm(config, "can_view")
    doc = next((d for d in list_documents(owner_type, owner_id) if d.id == doc_id), None)
    if not doc:
        abort(404)
    path = document_file_path(doc)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=False, download_name=doc.original_filename)


@documents_bp.route("/<owner_type>/<int:owner_id>/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete(owner_type, owner_id, doc_id):
    config, _owner = _owner_or_404(owner_type, owner_id)
    _require_perm(config, "can_delete")
    doc = next((d for d in list_documents(owner_type, owner_id) if d.id == doc_id), None)
    if not doc:
        abort(404)
    delete_document(doc)
    db.session.commit()
    write_log(current_user, config.permission_module, "DELETE_DOCUMENT",
               description=f"{owner_type}#{owner_id}: doc#{doc_id}")
    if is_modal_request():
        return jsonify({"success": True})
    flash("Sənəd silindi.", "info")
    return redirect(_back_url(config, owner_id))
