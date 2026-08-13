"""
Lets every add/edit view support two response modes with minimal code:

  1. Normal navigation (GET a full page, POST -> redirect) — used when the
     person opens the URL directly (e.g. bookmark, JS disabled).
  2. Modal popup (GET a bare form fragment, POST -> JSON) — used by
     openFormModal()/wireModalForm() in app/static/js/modal.js. The request
     is recognised by the `X-Requested-With: XMLHttpRequest` header that the
     modal JS always sends.

Usage in a view:

    from app.utils.modal import is_modal_request, render_form, modal_redirect

    @bp.route("/add", methods=["GET", "POST"])
    def add_thing():
        if request.method == "POST":
            error = validate(...)
            if error:
                flash(error, "danger")
                return render_form("things/form.html", thing=None, **choices)
            ...save...
            return modal_redirect("things.list_things")
        return render_form("things/form.html", thing=None, **choices)
"""

from flask import request, render_template, redirect, url_for, jsonify


def is_modal_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def render_form(template, **context):
    """Renders an add/edit template either as a full page (default layout)
    or as a bare fragment (when opened inside the modal popup)."""
    layout = "modal_layout.html" if is_modal_request() else "base.html"
    if is_modal_request() and request.method == "POST":
        # Validation failed on a modal POST: return JSON so the modal JS
        # knows to swap in the re-rendered (error-containing) fragment
        # instead of treating this as a normal page load.
        html = render_template(template, layout=layout, **context)
        return jsonify({"success": False, "html": html})
    return render_template(template, layout=layout, **context)


def modal_redirect(endpoint, **values):
    """Call this instead of redirect() after a successful save. Returns a
    normal redirect for full-page navigation, or a small JSON success
    payload for modal popups (the modal JS then closes the popup and
    reloads the grid behind it — no navigation happens)."""
    if is_modal_request():
        return jsonify({"success": True})
    return redirect(url_for(endpoint, **values))

def modal_employee_saved(employee_id):
    """Keep the employee master modal open after the first save."""
    if is_modal_request():
        return jsonify({
            "success": True,
            "keep_open": True,
            "reload_url": url_for("hr.edit_employee", emp_id=employee_id),
            "employee_id": employee_id,
        })

    return redirect(url_for("hr.edit_employee", emp_id=employee_id))