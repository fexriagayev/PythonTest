/**
 * Client-side translation lookup — mirrors the server's t(key) so JS
 * (modal.js, app.js, ...) doesn't hardcode its own copy of the same
 * strings. window.I18N is populated once in base.html from the same
 * TRANSLATIONS dict the server templates use (app/i18n.py), for the
 * user's current language.
 *
 * Supports simple {placeholder} substitution, e.g.:
 *   t("js_generic_fetch_error", {status: 500, url: "/hr/add"})
 */
function t(key, vars) {
  var text = (window.I18N && window.I18N[key]) || key;
  if (vars) {
    Object.keys(vars).forEach(function (k) {
      text = text.replace("{" + k + "}", vars[k]);
    });
  }
  return text;
}

/** CSRF protection for native forms and same-origin AJAX requests. */
(function () {
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.matches || !form.matches("form")) return;
    if (form.querySelector('input[name="csrf_token"]')) return;
    var token = csrfToken();
    if (!token) return;
    var input = document.createElement("input");
    input.type = "hidden";
    input.name = "csrf_token";
    input.value = token;
    form.appendChild(input);
  }, true);

  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    init = init || {};
    var method = String(init.method || (input && input.method) || "GET").toUpperCase();
    if (["POST", "PUT", "PATCH", "DELETE"].indexOf(method) !== -1) {
      var url = typeof input === "string" ? input : (input && input.url) || "";
      try {
        var target = new URL(url, window.location.href);
        if (target.origin === window.location.origin) {
          var headers = new Headers(init.headers || {});
          if (!headers.has("X-CSRFToken")) headers.set("X-CSRFToken", csrfToken());
          init.headers = headers;
        }
      } catch (e) { }
    }
    return nativeFetch(input, init);
  };
})();

/* Shared helpers used by the DevExtreme DataGrid based list pages. */

/**
 * Global search box for a DevExtreme grid.
 *
 * Uses DevExtreme's native search text, so it does not destroy or replace
 * individual column filters.
 */
function wireGlobalSearch(grid, inputEl, fields) {
  if (!inputEl || !grid) return;

  if (fields && fields.length) {
    grid.option("searchPanel.searchExpr", fields);
  }

  inputEl.addEventListener("input", function () {
    grid.option(
      "searchPanel.text",
      inputEl.value || ""
    );
  });
}

/**
 * Wires a select to DevExtreme grouping.
 */
function wireGroupBy(grid, selectEl) {
  if (!selectEl || !grid) return;

  selectEl.addEventListener("change", function () {
    const field = selectEl.value || null;

    grid.clearGrouping();

    if (field) {
      grid.columnOption(
        field,
        "groupIndex",
        0
      );
    }

    if (typeof grid._advancedGridMarkDirty === "function") {
      grid._advancedGridMarkDirty();
    }
  });
}

/**
 * Refreshes the employee edit view after a photo change.
 */
function refreshEmployeeFormView(refreshUrl) {
  const modalRoot = document.getElementById("appModal");

  if (
    modalRoot &&
    modalRoot.classList.contains("open")
  ) {
    openFormModal(
      refreshUrl,
      function () {
        if (window.currentGridTable) {
          window.currentGridTable.setData();
        }
      }
    );
  } else {
    window.location.reload();
  }
}

function quickAddDictionaryItem(moduleCode, category, selectElementId, categoryLabel) {
  const name = prompt(t("quick_add_prompt", { label: categoryLabel || category }));
  if (!name || !name.trim()) return;

  fetch("/core/dictionary-quick-add", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({ module_code: moduleCode, category: category, name: name.trim() }),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.success) {
        showErrorPopup(data.error || t("quick_add_failed"));
        return;
      }
      const select = document.getElementById(selectElementId);
      if (!select) return;
      const opt = document.createElement("option");
      opt.value = data.item.id;
      opt.textContent = data.item.name;
      select.appendChild(opt);
      select.value = data.item.id;
    })
    .catch(function (err) {
      showErrorPopup(t("quick_add_failed_with_msg", { msg: err.message }), err.stack || "");
    });
}

/**
 * Same idea as quickAddDictionaryItem() but for a checkbox-list (multi-
 * select) dictionary field like Güzəştlər — appends a new checked checkbox
 * chip instead of a <select> option.
 */
function quickAddCheckboxDictionaryItem(moduleCode, category, gridElementId, inputName, categoryLabel) {
  const name = prompt(t("quick_add_prompt", { label: categoryLabel || category }));
  if (!name || !name.trim()) return;

  fetch("/core/dictionary-quick-add", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({ module_code: moduleCode, category: category, name: name.trim() }),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.success) {
        showErrorPopup(data.error || t("quick_add_failed"));
        return;
      }
      const grid = document.getElementById(gridElementId);
      if (!grid) return;
      const emptyMsg = grid.querySelector("p");
      if (emptyMsg) emptyMsg.remove();
      const label = document.createElement("label");
      label.className = "checkbox-chip";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = inputName;
      cb.value = data.item.id;
      cb.checked = true;
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + data.item.name));
      grid.appendChild(label);
    })
    .catch(function (err) {
      showErrorPopup(t("quick_add_failed_with_msg", { msg: err.message }), err.stack || "");
    });
}

/** Deletes a record via AJAX and reloads the current grid in place
 * (no full page navigation) — used by the row action buttons. */
function ajaxDeleteAndReload(url) {
  if (!confirm(t("js_confirm_delete"))) return;
  setLastAction(t("last_action_delete_attempt", { url: url }));
  fetch(url, {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(function (r) {
      if (!r.ok) throw new Error(t("js_generic_fetch_error", { status: r.status, url: url }));
      if (window.currentGridTable) window.currentGridTable.setData();
    })
    .catch(function (err) {
      showErrorPopup(t("js_delete_error") + err.message, err.stack || "");
    });
}

/** Kept for any legacy full-page form (non-modal) delete buttons. */
function postAndReload(url) {
  if (!confirm(t("js_confirm_delete"))) return;
  const f = document.createElement("form");
  f.method = "post";
  f.action = url;
  document.body.appendChild(f);
  f.submit();
}

/** Reloads a single form in place after a side-action that doesn't go
 * through the normal submit flow (photo upload/delete). Reuses the modal
 * body swap if a modal is open, otherwise falls back to a full page
 * navigation (e.g. the form was opened directly, not inside a modal). */
function reloadFormInPlace(reloadUrl) {
  const body = document.getElementById("modalBody");
  const form = body ? body.querySelector("form") : null;
  if (!body || !form) {
    window.location.href = reloadUrl;
    return Promise.resolve();
  }
  return fetch(reloadUrl, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(function (r) {
      if (!r.ok) throw new Error(t("js_generic_fetch_error", { status: r.status, url: reloadUrl }));
      return r.text();
    })
    .then(function (html) {
      body.innerHTML = html;
      if (typeof relocateModalFlash === "function") relocateModalFlash(body);
      if (typeof executeInjectedScripts === "function") executeInjectedScripts(body);
      if (typeof wireModalForm === "function") {
        wireModalForm(window.__currentModalSavedCallback);
      }
    });
}

/** Uploads a photo (employee, etc.) via AJAX, then reloads the form so the
 * new image and the enabled "Sil" button show up. */
function uploadEmployeePhoto(uploadUrl, reloadUrl, inputEl) {
  const file = inputEl && inputEl.files && inputEl.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("photo", file);

  setLastAction(t("last_action_photo_upload_attempt", { url: uploadUrl }));
  fetch(uploadUrl, {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
    body: formData,
  })
    .then(function (r) {
      if (!r.ok) throw new Error(t("js_generic_fetch_error", { status: r.status, url: uploadUrl }));
      return reloadFormInPlace(reloadUrl);
    })
    .catch(function (err) {
      showErrorPopup(t("js_photo_upload_error") + err.message, err.stack || "");
    });
}

/** Deletes a record via AJAX, then reloads a single form in place
 * (used by the employee photo "Sil" button). */
function ajaxDeleteAndReloadPage(deleteUrl, reloadUrl) {
  if (!confirm(t("js_confirm_delete"))) return;
  setLastAction(t("last_action_delete_attempt", { url: deleteUrl }));
  fetch(deleteUrl, {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(function (r) {
      if (!r.ok) throw new Error(t("js_generic_fetch_error", { status: r.status, url: deleteUrl }));
      return reloadFormInPlace(reloadUrl);
    })
    .catch(function (err) {
      showErrorPopup(t("js_delete_error") + err.message, err.stack || "");
    });
}