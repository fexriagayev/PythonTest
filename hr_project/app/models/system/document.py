from app import db
from datetime import datetime


class Document(db.Model):
    """Generic 'Sənədlər' (attached file) system, usable from ANY module.

    Instead of a hard FK to one owning table (the old design only worked
    for Employee), a Document is attached via a polymorphic
    (owner_type, owner_id) pair — e.g. owner_type='employee' or
    owner_type='tabel_period'. This lets brand-new modules (Tabel, and
    anything added later) reuse the exact same upload/list/view/download/
    delete flow (see app/services/document_service.py and
    app/modules/documents/routes.py) without duplicating any code.

    To attach Documents to a new entity type:
      1. Add an entry to DOCUMENT_OWNER_MODULES in document_service.py
         mapping the new owner_type -> (permission module_code, Model
         class, "endpoint.name" to redirect back to, url kwarg name).
      2. Embed templates/partials/documents_panel.html in that entity's
         template, passing owner_type/owner_id/panel_id.
    """

    __tablename__ = "documents"
    __table_args__ = (
        db.Index("ix_documents_owner", "owner_type", "owner_id"),
    )

    id = db.Column(db.Integer, primary_key=True)

    owner_type = db.Column(db.String(30), nullable=False)
    owner_id = db.Column(db.Integer, nullable=False)

    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)  # actual name on disk
    document_type_id = db.Column(db.Integer, db.ForeignKey("dictionary_items.id"))
    note = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    document_type = db.relationship("DictionaryItem", foreign_keys=[document_type_id])
