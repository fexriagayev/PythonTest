"""Generic 'Sənədlər' (attached file) service.

This is the SINGLE place that knows how to save/list/delete Document rows
(app/models/system/document.py) for ANY owner entity. Every module (HR
employees, Tabel periods, and anything added later) goes through this
service + app/modules/documents/routes.py instead of having its own
copy-pasted upload/list/delete code.

To attach documents to a brand-new entity type, just add one line to
DOCUMENT_OWNERS below.
"""

from app import db
from app.models import Document
from app.utils.uploads import save_uploaded_file, delete_uploaded_file, uploaded_file_path

DOCUMENT_SUBDIR = "attachments"


class DocumentOwner:
    """Describes how one owner_type plugs into the generic documents system."""

    def __init__(self, model, permission_module, back_endpoint, back_url_kwarg):
        self.model = model  # SQLAlchemy model class, for get_or_404 + existence checks
        self.permission_module = permission_module  # e.g. "HR", "TABEL"
        self.back_endpoint = back_endpoint  # endpoint to redirect to (non-modal fallback)
        self.back_url_kwarg = back_url_kwarg  # kwarg name that endpoint expects


def _build_owners():
    # Local imports to avoid module-load-order cycles.
    from app.models import Employee
    from app.models.tabel.tabel import TabelPeriod

    return {
        "employee": DocumentOwner(Employee, "HR", "hr.document_list", "emp_id"),
        "tabel_period": DocumentOwner(
            TabelPeriod, "TABEL", "tabel.period_detail", "period_id"
        ),
    }


def get_owner_config(owner_type):
    """Returns the DocumentOwner for this owner_type, or None if unknown."""
    return _build_owners().get(owner_type)


def list_documents(owner_type, owner_id):
    return (
        Document.query.filter_by(owner_type=owner_type, owner_id=owner_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def save_document(owner_type, owner_id, file_storage, document_type_id, note):
    """Saves the uploaded file to disk + creates the Document row (not yet
    committed). Returns the new Document, or None if no file was given."""
    stored, original = save_uploaded_file(file_storage, DOCUMENT_SUBDIR)
    if not stored:
        return None
    doc = Document(
        owner_type=owner_type,
        owner_id=owner_id,
        original_filename=original,
        stored_filename=stored,
        document_type_id=document_type_id,
        note=(note or "").strip(),
    )
    db.session.add(doc)
    return doc


def delete_document(doc):
    """Deletes the physical file + the Document row (not yet committed)."""
    delete_uploaded_file(doc.stored_filename, DOCUMENT_SUBDIR)
    db.session.delete(doc)


def delete_all_documents_for_owner(owner_type, owner_id):
    """Call this before deleting an owner row (e.g. Employee, TabelPeriod)
    since Document isn't a real FK relationship and has no DB cascade."""
    for doc in list_documents(owner_type, owner_id):
        delete_document(doc)


def document_file_path(doc):
    return uploaded_file_path(doc.stored_filename, DOCUMENT_SUBDIR)
