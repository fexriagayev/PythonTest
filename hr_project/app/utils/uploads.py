"""Generic, reusable file-upload helpers (photos, documents, any future
attachment). Files are stored under UPLOAD_DIR/<subdir>/, never inside
static/, and are only ever served back out through an authenticated route
that checks the person's module permission first — never as static files."""

import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename


def save_uploaded_file(file_storage, subdir):
    """Saves a Werkzeug FileStorage under UPLOAD_DIR/<subdir>/ with a
    collision-proof generated filename. Returns (stored_filename,
    original_filename), or (None, None) if no file was provided."""
    if not file_storage or not file_storage.filename:
        return None, None

    original_filename = secure_filename(file_storage.filename)
    ext = os.path.splitext(original_filename)[1]
    stored_filename = f"{uuid.uuid4().hex}{ext}"

    target_dir = os.path.join(current_app.config["UPLOAD_DIR"], subdir)
    os.makedirs(target_dir, exist_ok=True)
    file_storage.save(os.path.join(target_dir, stored_filename))

    return stored_filename, original_filename


def delete_uploaded_file(stored_filename, subdir):
    if not stored_filename:
        return
    path = os.path.join(current_app.config["UPLOAD_DIR"], subdir, stored_filename)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            current_app.logger.exception(f"Failed to delete uploaded file {path}")


def uploaded_file_path(stored_filename, subdir):
    return os.path.join(current_app.config["UPLOAD_DIR"], subdir, stored_filename)
