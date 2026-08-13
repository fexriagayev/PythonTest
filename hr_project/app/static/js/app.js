
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
      } catch (e) {}
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
  const name = prompt("Yeni " + (categoryLabel || category) + " adı:");
  if (!name || !name.trim()) return;

  fetch("/core/dictionary-quick-add", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({ module_code: moduleCode, category: category, name: name.trim() }),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.success) {
        showErrorPopup(data.error || "Əlavə etmək mümkün olmadı.");
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
      showErrorPopup("Əlavə etmək mümkün olmadı: " + err.message, err.stack || "");
    });
}

/**
 * Same idea as quickAddDictionaryItem() but for a checkbox-list (multi-
 * select) dictionary field like Güzəştlər — appends a new checked checkbox
 * chip instead of a <select> option.
 */
function quickAddCheckboxDictionaryItem(moduleCode, category, gridElementId, inputName, categoryLabel) {
  const name = prompt("Yeni " + (categoryLabel || category) + " adı:");
  if (!name || !name.trim()) return;

  fetch("/core/dictionary-quick-add", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({ module_code: moduleCode, category: category, name: name.trim() }),
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.success) {
        showErrorPopup(data.error || "Əlavə etmək mümkün olmadı.");
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
      showErrorPopup("Əlavə etmək mümkün olmadı: " + err.message, err.stack || "");
    });
}

/** Deletes a record via AJAX and reloads the current grid in place
 * (no full page navigation) — used by the row action buttons. */
function ajaxDeleteAndReload(url) {
  if (!confirm("Silmək istədiyinizə əminsiniz?")) return;
  setLastAction("Silməyə çalışdı: " + url);
  fetch(url, {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(function (r) {
      if (!r.ok) throw new Error("Server " + r.status + " qaytardı (" + url + ")");
      if (window.currentGridTable) window.currentGridTable.setData();
    })
    .catch(function (err) {
      showErrorPopup("Silinmə zamanı xəta baş verdi: " + err.message, err.stack || "");
    });
}

/** Kept for any legacy full-page form (non-modal) delete buttons. */
function postAndReload(url) {
  if (!confirm("Silmək istədiyinizə əminsiniz?")) return;
  const f = document.createElement("form");
  f.method = "post";
  f.action = url;
  document.body.appendChild(f);
  f.submit();
}
