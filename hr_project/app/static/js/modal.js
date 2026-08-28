/* ===========================================================================
   DevExtreme modal/form system
   ---------------------------------------------------------------------------
   - Uses DevExtreme dxPopup for every Add/Edit modal.
   - Uses DevExtreme editors for standard form controls.
   - Keeps the existing server-rendered <form> and FormData submission, so
     existing Flask routes and validation do not need to change.
   - Forms use a shared responsive layout defined by modal_form_base.html.
   =========================================================================== */

// Plain "\u25A1" / "\u2750" glyph characters render blank in some fonts —
// most reliably reproducible on narrower viewports / specific OS font
// substitution, which is exactly where it went unnoticed during testing.
// Inline SVG data URIs render identically everywhere, independent of
// whatever font happens to be active.
function svgDataUri(svg) {
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

const MODAL_MAXIMIZE_ICON = svgDataUri(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16">' +
    '<rect x="4" y="4" width="16" height="16" fill="none" stroke="#5b6472" stroke-width="2"/>' +
    "</svg>"
);

const MODAL_RESTORE_ICON = svgDataUri(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16">' +
    '<rect x="7" y="3" width="14" height="14" fill="none" stroke="#5b6472" stroke-width="2"/>' +
    '<rect x="3" y="7" width="14" height="14" fill="#fff" stroke="#5b6472" stroke-width="2"/>' +
    "</svg>"
);

function ensureModalRoot() {
  let root = document.getElementById("appModal");
  if (root && root.__dxPopup) return root;

  if (root) {
    root.remove();
  }

  root = document.createElement("div");
  root.id = "appModal";
  document.body.appendChild(root);

  // Normal-size geometry, kept here (not just inline in the dxPopup config
  // below) so toggleModalMaximize() can restore back to these exact values.
  const NORMAL_GEOMETRY = {
    width: "min(960px, 94vw)",
    height: "auto",
    maxHeight: "92vh",
    position: {
      my: "top",
      at: "top",
      of: window,
      offset: "0 32"
    }
  };

  const MAXIMIZED_GEOMETRY = {
    width: "100vw",
    height: "100vh",
    maxHeight: "100vh",
    position: {
      my: "top",
      at: "top",
      of: window,
      offset: "0 0"
    }
  };

  root.__modalNormalGeometry = NORMAL_GEOMETRY;
  root.__modalMaximizedGeometry = MAXIMIZED_GEOMETRY;
  root.__isMaximized = false;

  $(root).dxPopup({
    visible: false,
    deferRendering: false,
    dragEnabled: true,
    hideOnOutsideClick: false,
    showCloseButton: false,
    resizeEnabled: true,
    shading: true,
    width: NORMAL_GEOMETRY.width,
    height: NORMAL_GEOMETRY.height,
    maxHeight: NORMAL_GEOMETRY.maxHeight,
    // Anchored near the top instead of the default vertical centering.
    // Centering recalculates (and visibly jumps) every time the content
    // height changes — e.g. switching employee tabs. Anchoring the top
    // edge keeps it fixed; only the bottom edge grows/shrinks.
    position: NORMAL_GEOMETRY.position,
    showTitle: true,
    title: "Forma",
    // The dark "shading" only visually blocks the background — it does
    // not stop the underlying page from scrolling on its own, which is
    // why the page's own scrollbar was visible next to the popup card.
    // Lock/unlock page scroll on every show/hide. Some browsers scroll
    // <html> rather than <body>, so both are locked to be safe.
    onShowing: function () {
      document.documentElement.classList.add("modal-scroll-lock");
    },
    onHidden: function () {
      document.documentElement.classList.remove("modal-scroll-lock");
    },
    toolbarItems: [
      // Maximize / restore toggle. Defined before "titleClose" below so it
      // renders to its left (top-toolbar "after" items lay out in the
      // order they're declared, ending flush with the right edge).
      {
        name: "maximizeToggle",
        toolbar: "top",
        location: "after",
        widget: "dxButton",
        options: {
          icon: MODAL_MAXIMIZE_ICON,
          stylingMode: "text",
          hint: t("js_maximize"),
          onInitialized: function (e) {
            root.__maximizeButton = e.component;
          },
          onClick: function () {
            toggleModalMaximize();
          }
        }
      },
      // Custom title-bar close ("X"). DevExtreme's own built-in
      // showCloseButton icon always hides the popup outright and its
      // onHiding event is NOT cancelable for dxPopup, so there was no
      // way to make the default X respect a parent form waiting on the
      // modalStateStack (e.g. "+" a work-history record from inside the
      // employee tabs) — it always closed everything instead of just
      // the sub-form. Replacing it with our own button, wired to the
      // exact same handler as "Bağla", is the only reliable fix.
      {
        name: "titleClose",
        toolbar: "top",
        location: "after",
        widget: "dxButton",
        options: {
          icon: "close",
          stylingMode: "text",
          hint: t("js_close"),
          onClick: function () {
            if (restoreParentModal()) {
              return;
            }

            hideModal();
          }
        }
      },
      {
        name: "cancel",
        toolbar: "bottom",
        location: "after",
        widget: "dxButton",
        options: {
          text: t("js_close"),
          type: "normal",
          stylingMode: "outlined",
          onClick: function () {
            if (restoreParentModal()) {
              return;
            }

            hideModal();
          }
        }
      },
      {
        // Identified by `name`, not by matching its display text — the
        // text changes with the user's language (and briefly to
        // "Yadda saxlanılır..." while saving), so text-matching would
        // silently break as soon as either of those changes.
        name: "save",
        toolbar: "bottom",
        location: "after",
        widget: "dxButton",
        options: {
          text: t("js_save"),
          type: "default",
          stylingMode: "contained",
          onClick: function () {
            const form = getModalBody() && getModalBody().querySelector("form");
            if (form && typeof form.__submitModalForm === "function") {
              form.__submitModalForm();
            }
          }
        }
      }
    ],
    contentTemplate: function (contentElement) {
      // A single, fixed-position flash slot — ABOVE the scrollable modal
      // body, so it's always in the exact same place regardless of which
      // tab/subpage happens to be showing. Every place that loads new
      // server-rendered HTML into the modal (see relocateModalFlash) pulls
      // any embedded flash message(s) out of that HTML and puts ONLY the
      // most recent one here, replacing whatever was shown before — this
      // is what fixes flash messages appearing in a different spot each
      // time, and more than one showing at once.
      const flashSlot = document.createElement("div");
      flashSlot.id = "modalFlashSlot";
      contentElement.append(flashSlot);

      const body = document.createElement("div");
      body.id = "modalBody";
      body.className = "dx-modal-body";
      contentElement.append(body);
    },
    onHiding: function () {
      const body = document.getElementById("modalBody");

      if (body) {
        body.innerHTML = "";
      }

      const flashSlot = document.getElementById("modalFlashSlot");
      if (flashSlot) {
        flashSlot.innerHTML = "";
      }
    }
  });

  root.__dxPopup = $(root).dxPopup("instance");

  return root;
}

// Toggles the shared modal between its normal size (see NORMAL_GEOMETRY in
// ensureModalRoot) and a full-viewport size (MAXIMIZED_GEOMETRY). Called
// from the corner toolbar button (see MODAL_MAXIMIZE_ICON /
// MODAL_RESTORE_ICON above), but exposed on window so it could also be
// triggered elsewhere (e.g. a keyboard shortcut) later.
function toggleModalMaximize() {
  const root = document.getElementById("appModal");
  if (!root || !root.__dxPopup) return;

  const goingToMaximized = !root.__isMaximized;
  const geometry = goingToMaximized
    ? root.__modalMaximizedGeometry
    : root.__modalNormalGeometry;

  root.__dxPopup.option({
    width: geometry.width,
    height: geometry.height,
    maxHeight: geometry.maxHeight,
    position: geometry.position
  });

  root.__isMaximized = goingToMaximized;

  if (root.__maximizeButton) {
    root.__maximizeButton.option({
      icon: goingToMaximized ? MODAL_RESTORE_ICON : MODAL_MAXIMIZE_ICON,
      hint: goingToMaximized ? t("js_restore") : t("js_maximize")
    });
  }

  // Any DevExtreme grid inside the modal (work history, vacation periods,
  // leave requests, ...) sizes its own height once, up front, from
  // `window.innerHeight - <grid's top offset> - 16` (see advanced-grid.js,
  // computeInitialHeight/resizeHandler) — it does NOT know the popup
  // itself just changed size, because nothing about the browser window
  // changed. Firing a synthetic "resize" re-runs that same calculation
  // (grid's top offset is different now that the popup is maximized/
  // restored), which is what makes the grid fill the popup's new height
  // instead of leaving empty space below it ("Align = client"). The
  // popup's geometry change above is applied synchronously (no
  // animation), but a tick's delay lets the browser finish reflowing the
  // new layout before the grid measures its new top offset.
  window.setTimeout(function () {
    window.dispatchEvent(new Event("resize"));
  }, 50);
}

function getModalPopup() {
  return ensureModalRoot().__dxPopup;
}

function getModalBody() {
  ensureModalRoot();
  return document.getElementById("modalBody");
}

/* ---------------------------------------------------------------------------
   Flash messages
   ---------------------------------------------------------------------------
   Every add/edit template still renders its own `.flash-wrap` (via
   modal_layout.html / get_flashed_messages), because Flask's flash queue is
   consumed by whichever request happens to render next — that could be the
   main employee form reloading, a different sub-tab loading, etc. Left
   in place, that meant the message showed up wherever that particular
   fragment happened to land in the modal (above the tabs, inside a
   sub-tab's own content, ...), and if more than one message was queued
   they all rendered together.

   This pulls any `.flash-wrap` back OUT of the just-loaded fragment and
   shows only the LAST message in it, in the single fixed #modalFlashSlot
   at the top of the modal — always the same place, never more than one at
   once. Call this right after setting .innerHTML on any modal content
   fetched from the server (see call sites in openFormModal, submitModalForm,
   loadEmployeeModalTab below, and reloadFormInPlace in app.js).
   --------------------------------------------------------------------------- */
function relocateModalFlash(container) {
  if (!container) return;

  const slot = document.getElementById("modalFlashSlot");
  const wraps = container.querySelectorAll(".flash-wrap");

  let lastFlash = null;
  wraps.forEach(function (wrap) {
    const flashes = wrap.querySelectorAll(".flash");
    if (flashes.length) {
      lastFlash = flashes[flashes.length - 1];
    }
    wrap.remove();
  });

  if (!slot) return;

  slot.innerHTML = "";

  if (lastFlash) {
    const newWrap = document.createElement("div");
    newWrap.className = "flash-wrap";
    newWrap.appendChild(lastFlash.cloneNode(true));
    slot.appendChild(newWrap);
  }
}

// Finds the Save toolbar button by its stable `name`, not by matching
// display text — the text changes with the user's language and while
// saving ("Yadda saxlanılır..."), so a text-based lookup breaks easily.
function findSaveToolbarItem(toolbarItems) {
  return (
    toolbarItems &&
    toolbarItems.find(function (item) {
      return item.name === "save";
    })
  );
}

function showModal(title) {
  const popup = getModalPopup();
  if (title) popup.option("title", title);
  popup.show();
}

function hideModal() {
  const root = document.getElementById("appModal");
  if (root && root.__dxPopup) {
    root.__dxPopup.hide();

    // Always leave the shared popup at its normal size for the *next*
    // completely fresh openFormModal() call — maximize/restore is only
    // meant to persist for the lifetime of the current modal session
    // (including any nested sub-forms pushed onto modalStateStack while
    // it's open), not carry over once the whole thing has been closed.
    if (root.__isMaximized) {
      toggleModalMaximize();
    }
  }

  // Full close (not "back to parent tab/form"): clear out this session's
  // state so the next openFormModal() call starts clean. Without this,
  // stale HTML left in the body from the just-closed modal would make the
  // *next* openFormModal() think a parent modal is still open and wrongly
  // push that stale content (and whatever callback happened to be set at
  // the time) onto modalStateStack — corrupting the next modal session's
  // "restore parent" / close behavior.
  const body = getModalBody();
  if (body) {
    body.innerHTML = "";
  }

  const flashSlot = document.getElementById("modalFlashSlot");
  if (flashSlot) {
    flashSlot.innerHTML = "";
  }

  modalStateStack.length = 0;
  window.__currentModalSavedCallback = null;
}

function restoreParentModal() {
  if (!modalStateStack.length) {
    return false;
  }

  const state = modalStateStack.pop();

  const body = getModalBody();
  const popup = getModalPopup();

  if (!body) {
    return false;
  }

  body.innerHTML = state.html;

  popup.option(
    "title",
    state.title || t("modal_default_title")
  );

  // Restore the previous view's Save button state exactly as it was
  // (e.g. still disabled if the parent view was an employee sub-tab)
  // instead of assuming it should always be enabled.
  const toolbarItems = popup.option("toolbarItems");
  const saveItem = findSaveToolbarItem(toolbarItems);
  if (saveItem && saveItem.options) {
    saveItem.options.disabled = !!state.saveDisabled;
    saveItem.options.text = state.saveText || t("js_save");
    popup.option("toolbarItems", toolbarItems);
  }

  executeInjectedScripts(body);

  /*
   * Parent modalın içindəki form/tab eventlərini yenidən qoş.
   */
  const parentForm = body.querySelector("form");

  if (parentForm) {
    wireModalForm(state.onSavedCallback);
  }

  popup.show();

  return true;
}

function getFieldLabel(form, field) {
  if (!field.id) return null;
  return form.querySelector('label[for="' + CSS.escape(field.id) + '"]');
}

function syncNativeValue(field, value) {
  if (!field) return;

  if (field.type === "checkbox" || field.type === "radio") {
    field.checked = !!value;
  } else {
    field.value = value == null ? "" : value;
  }

  field.dispatchEvent(new Event("change", { bubbles: true }));
}

function upgradeSelect(field) {
  if (field.__dxEditor) return;

  const wrapper = document.createElement("div");
  wrapper.className = "dx-modal-editor-wrapper";
  field.parentNode.insertBefore(wrapper, field);
  wrapper.appendChild(field);

  const items = Array.from(field.options || []).map(function (option) {
    return {
      value: option.value,
      text: option.textContent
    };
  });

  field.style.display = "none";

  const editorHost = document.createElement("div");
  wrapper.appendChild(editorHost);

  $(editorHost).dxSelectBox({
    dataSource: items,
    valueExpr: "value",
    displayExpr: "text",
    value: field.value,
    searchEnabled: items.length > 8,
    showClearButton: !field.required,
    onValueChanged: function (e) {
      syncNativeValue(field, e.value);
    }
  });

  field.__dxEditor = $(editorHost).dxSelectBox("instance");
}

function upgradeText(field) {
  if (field.__dxEditor) return;

  const type = field.type;
  const options = {
    value: field.value || "",
    stylingMode: "outlined",
    onValueChanged: function (e) {
      syncNativeValue(field, e.value);
    }
  };

  if (type === "email") {
    options.mode = "email";
  }

  $(field).dxTextBox(options);
  field.__dxEditor = $(field).dxTextBox("instance");
}

function upgradeNumber(field) {
  if (field.__dxEditor) return;

  $(field).dxNumberBox({
    value: field.value === "" ? null : Number(field.value),
    min: field.min !== "" ? Number(field.min) : undefined,
    max: field.max !== "" ? Number(field.max) : undefined,
    step: field.step && field.step !== "any" ? Number(field.step) : 1,
    showSpinButtons: true,
    stylingMode: "outlined",
    onValueChanged: function (e) {
      syncNativeValue(field, e.value == null ? "" : e.value);
    }
  });

  field.__dxEditor = $(field).dxNumberBox("instance");
}

function upgradeDate(field) {
  if (field.__dxEditor) return;

  $(field).dxDateBox({
    type: "date",
    value: field.value || null,
    displayFormat: "yyyy-MM-dd",
    useMaskBehavior: true,
    stylingMode: "outlined",
    onValueChanged: function (e) {
      let value = "";
      if (e.value instanceof Date && !isNaN(e.value.getTime())) {
        const y = e.value.getFullYear();
        const m = String(e.value.getMonth() + 1).padStart(2, "0");
        const d = String(e.value.getDate()).padStart(2, "0");
        value = y + "-" + m + "-" + d;
      }
      syncNativeValue(field, value);
    }
  });

  field.__dxEditor = $(field).dxDateBox("instance");
}

function upgradeTextArea(field) {
  if (field.__dxEditor) return;

  // NOT `$(field).dxTextArea(...)` directly on the real <textarea> — see
  // the identical comment on upgradeSelect's wrapper/host pattern above.
  // A <textarea>'s content model is text-only (RCDATA): the HTML parser
  // stops at the very first literal "</textarea>" it sees, with no
  // concept of nested tags. DevExtreme's widget structure (a
  // ".dx-texteditor-container" wrapping its OWN inner <textarea>) was
  // being built as real DOM children of the ORIGINAL <textarea> node —
  // fine as long as nothing ever re-parses it from a string, but this
  // app's modal-tab navigation caches/restores `body.innerHTML` on
  // exactly this DOM (see modalStateStack.push/openEmployeeModalTab).
  // Serializing that structure back to a string, then reparsing it via
  // `innerHTML = ...`, hits the RCDATA rule above: the parser treats the
  // *inner* widget's own "</textarea>" as the OUTER textarea's closing
  // tag, so everything in between (including further nested markup) gets
  // swallowed as literal text into the outer textarea's value — and each
  // further tab switch re-serializes and re-escapes that text one layer
  // deeper, producing runaway nested "&lt;div..." content in the saved
  // note. Keeping the widget in a separate host <div> — never inside the
  // <textarea> itself — makes this structurally impossible.
  const wrapper = document.createElement("div");
  wrapper.className = "dx-modal-textarea-wrapper";
  field.parentNode.insertBefore(wrapper, field);
  wrapper.appendChild(field);

  field.style.display = "none";

  const editorHost = document.createElement("div");
  wrapper.appendChild(editorHost);

  $(editorHost).dxTextArea({
    value: field.value || "",
    width: "100%",
    minHeight: Math.max(80, Number(field.rows || 3) * 26),
    autoResizeEnabled: true,
    stylingMode: "outlined",
    onValueChanged: function (e) {
      syncNativeValue(field, e.value);
    }
  });

  field.__dxEditor = $(editorHost).dxTextArea("instance");
}

function upgradeRadioGroup(form) {
  if (!form || form.__dxModalRadioGroupUpgraded) return;
  const groups = {};
  form.querySelectorAll('input[type="radio"]').forEach(function (radio) {
    const key = radio.name || ("__radio_" + Math.random());
    (groups[key] ||= []).push(radio);
  });
  Object.keys(groups).forEach(function (name) {
    const radios = groups[name];
    if (radios.length < 2 || radios.some(function (r) { return r.__dxEditor; })) return;
    const first = radios[0];
    const host = document.createElement("div");
    host.className = "dx-modal-radio-group";
    first.parentNode.insertBefore(host, first);
    const items = radios.map(function (r) {
      return { value: r.value, text: (r.parentElement ? r.parentElement.textContent : r.value).trim() };
    });
    const selected = radios.find(function (r) { return r.checked; });
    radios.forEach(function (r) { r.style.display = "none"; });
    $(host).dxRadioGroup({
      items: items, valueExpr: "value", displayExpr: "text",
      value: selected ? selected.value : null, layout: "horizontal",
      onValueChanged: function (e) {
        radios.forEach(function (r) { r.checked = String(r.value) === String(e.value); r.dispatchEvent(new Event("change", { bubbles: true })); });
      }
    });
    radios.forEach(function (r) { r.__dxEditor = $(host).dxRadioGroup("instance"); });
  });
  form.__dxModalRadioGroupUpgraded = true;
}

function upgradeCheckbox(field) {
  if (field.__dxEditor) return;

  const label = getFieldLabel(field.form, field);
  const text = label ? label.textContent.trim() : "";
  // The dxCheckBox widget below renders `text` itself — without hiding the
  // original <label for="..."> too, its text would show a second time
  // right next to the widget.
  if (label) label.style.display = "none";

  const host = document.createElement("div");
  host.className = "dx-modal-checkbox";
  field.parentNode.insertBefore(host, field);
  field.style.display = "none";

  $(host).dxCheckBox({
    value: field.checked,
    text: text,
    onValueChanged: function (e) {
      field.checked = !!e.value;
      field.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  field.__dxEditor = $(host).dxCheckBox("instance");
}

function upgradeButtons(form) {
  form.querySelectorAll("button.btn:not([data-dx-upgraded])").forEach(function (button) {
    if (button.type === "submit") {
      $(button).dxButton({
        text: button.textContent.trim(),
        type: "default",
        stylingMode: "contained",
        useSubmitBehavior: true
      });
    } else {
      $(button).dxButton({
        text: button.textContent.trim(),
        stylingMode: "outlined"
      });
    }
    button.setAttribute("data-dx-upgraded", "1");
  });
}

function upgradeModalForm(form) {
  if (!form) return;

  form.classList.add("dx-modal-form");

  form.querySelectorAll("select").forEach(upgradeSelect);
  form.querySelectorAll('input[type="text"], input[type="email"], input[type="password"]').forEach(upgradeText);
  form.querySelectorAll('input[type="number"]').forEach(upgradeNumber);
  form.querySelectorAll('input[type="date"]').forEach(upgradeDate);
  form.querySelectorAll("textarea").forEach(upgradeTextArea);
  form.querySelectorAll('input[type="checkbox"]').forEach(upgradeCheckbox);
  upgradeRadioGroup(form);

  upgradeButtons(form);

  /*
   * The form is intentionally still a normal HTML form. This means Flask's
   * existing FormData/backend contract remains unchanged.
   */
}

function wireModalForm(onSavedCallback) {
  const body = getModalBody();
  const form = body ? body.querySelector("form") : null;
  if (!form) return;

  // Tracked globally so an unrelated in-place reload (e.g. after an
  // employee photo upload, see uploadEmployeePhoto() in app.js) can
  // re-wire the form without losing the original "list refresh" callback
  // the modal was opened with.
  window.__currentModalSavedCallback = onSavedCallback;

  upgradeModalForm(form);

  /* The form's own actions are hidden inside the popup; the popup footer
     provides Save/Cancel buttons. */
  form.querySelectorAll(".actions").forEach(function (el) {
    el.style.display = "none";
  });

  if (form.__modalSubmitWired) return;
  form.__modalSubmitWired = true;

  function submitModalForm() {
    /* Sync DevExtreme values into the original controls before FormData. */
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const actionUrl = form.getAttribute("action") || window.location.href;
    setLastAction(t("last_action_form_save_attempt", { url: actionUrl }));

    const formData = new FormData(form);

    /* Disable the footer Save button while the request is running. */
    const popup = getModalPopup();
    const saveButton = findSaveToolbarItem(popup.option("toolbarItems"));
    if (saveButton && saveButton.options) {
      saveButton.options.disabled = true;
      saveButton.options.text = t("js_saving");
      popup.option("toolbarItems", popup.option("toolbarItems"));
    }

    return fetch(actionUrl, {
      method: "POST",
      body: formData,
      headers: { "X-Requested-With": "XMLHttpRequest" }
    })
      .then(function (r) {
        if (!r.ok) {
          throw new Error(
            t("server_returned_status_url", { status: r.status, url: actionUrl })
          );
        }
        return r.json();
      })
      .then(function (data) {
        if (data.success) {

          if (data.keep_open && data.reload_url) {
            return fetch(data.reload_url, {
              headers: { "X-Requested-With": "XMLHttpRequest" }
            })
              .then(function (r) {
                if (!r.ok) {
                  throw new Error(
                    t("server_returned_status_url", { status: r.status, url: data.reload_url })
                  );
                }
                return r.text();
              })
              .then(function (html) {
                body.innerHTML = html;
                relocateModalFlash(body);

                const title = getModalTitleFromHtml(html);
                popup.option("title", title || t("js_form_title_default"));

                executeInjectedScripts(body);
                wireModalForm(onSavedCallback);

                // The save already happened server-side even though the
                // modal stays open (employee add/edit keeps editing after
                // the first save). The list grid behind the modal is now
                // stale, so refresh it now instead of only on close.
                if (onSavedCallback) {
                  onSavedCallback();
                }

                return data;
              });
          }

          if (modalStateStack.length) {
            const restored = restoreParentModal();

            if (restored && onSavedCallback) {
              onSavedCallback();
            }
          } else {
            hideModal();

            if (onSavedCallback) {
              onSavedCallback();
            }
          }

        } else {
          body.innerHTML = data.html;
          relocateModalFlash(body);
          executeInjectedScripts(body);
          wireModalForm(onSavedCallback);
        }
        return data;
      })
      .catch(function (err) {
        showErrorPopup(
          t("js_form_load_error") + err.message,
          err.stack || ""
        );
        throw err;
      })
      .finally(function () {
        const currentItems = popup.option("toolbarItems");
        const saveItem = findSaveToolbarItem(currentItems);
        if (saveItem && saveItem.options) {
          saveItem.options.disabled = false;
          saveItem.options.text = t("js_save");
          popup.option("toolbarItems", currentItems);
        }
      });
  }

  form.__submitModalForm = submitModalForm;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    submitModalForm();
  });
}

function executeInjectedScripts(container) {
  container.querySelectorAll("script").forEach(function (oldScript) {
    const newScript = document.createElement("script");
    Array.from(oldScript.attributes).forEach(function (attr) {
      newScript.setAttribute(attr.name, attr.value);
    });
    newScript.textContent = oldScript.textContent;
    oldScript.parentNode.replaceChild(newScript, oldScript);
  });
}

function getModalTitleFromHtml(html) {
  const temp = document.createElement("div");
  temp.innerHTML = html;
  const title = temp.querySelector("[data-form-title]");
  if (title) return title.getAttribute("data-form-title");
  const heading = temp.querySelector("h1, h2, h3");
  return heading ? heading.textContent.trim() : t("js_form_title_default");
}

const modalStateStack = [];

function openFormModal(url, onSavedCallback) {
  setLastAction(t("last_action_form_open_attempt", { url: url }));

  const popup = getModalPopup();
  const body = getModalBody();

  /*
   * Hazırkı modalı yadda saxla.
   */
  if (body && body.innerHTML.trim()) {
    const toolbarItemsNow = popup.option("toolbarItems");
    const saveItemNow = findSaveToolbarItem(toolbarItemsNow);
    modalStateStack.push({
      html: body.innerHTML,
      title: popup.option("title"),
      // BUG FIX: this must be the CURRENTLY OPEN (parent) form's own
      // saved-callback (e.g. "refresh the employees list"), not the
      // `onSavedCallback` parameter of *this* openFormModal() call — that
      // parameter belongs to the form we are about to open (the child,
      // e.g. "refresh the work-history sub-grid"). Storing the child's
      // callback here meant that after closing a nested modal (add/edit
      // work history, insurance, etc. from inside the employee tabs) and
      // returning to the parent employee form, saving the parent form
      // would incorrectly call the child's refresh function instead of
      // the parent's — so the employees list behind the modal never got
      // refreshed. window.__currentModalSavedCallback always holds the
      // callback the currently-visible form was wired with (set in
      // wireModalForm below), which is exactly what we need to restore.
      onSavedCallback: window.__currentModalSavedCallback,
      saveDisabled: !!(saveItemNow && saveItemNow.options && saveItemNow.options.disabled),
      saveText: (saveItemNow && saveItemNow.options && saveItemNow.options.text) || t("js_save")
    });
  }

  fetch(url, {
    headers: {
      "X-Requested-With": "XMLHttpRequest"
    }
  })
    .then(function (r) {
      if (!r.ok) {
        throw new Error(
          t("server_returned_status_url", { status: r.status, url: url })
        );
      }

      return r.text();
    })
    .then(function (html) {
      body.innerHTML = html;
      relocateModalFlash(body);

      const title = getModalTitleFromHtml(html);
      popup.option("title", title || "Forma");

      // A previous modal session (e.g. an employee sub-tab, or an
      // interrupted save) may have left the shared "Yadda saxla" button
      // disabled. Since the popup/toolbar instance is reused for every
      // form in the page session, that stale state otherwise carries
      // over into this new form. Always reset it for a freshly loaded form.
      const toolbarItems = popup.option("toolbarItems");
      const saveItem = findSaveToolbarItem(toolbarItems);
      if (saveItem && saveItem.options) {
        saveItem.options.disabled = false;
        saveItem.options.text = t("js_save");
        popup.option("toolbarItems", toolbarItems);
      }

      executeInjectedScripts(body);
      wireModalForm(onSavedCallback);

      popup.show();
    })
    .catch(function (err) {
      restoreParentModal();

      showErrorPopup(
        t("js_form_fetch_error") + err.message,
        err.stack || ""
      );
    });
}

function setEmployeeModalView(tabId) {
  const body = getModalBody();
  if (!body) return;

  const mainForm = body.querySelector("#modalFormContent");
  const subpage = body.querySelector("#employeeModalSubpage");

  if (!mainForm || !subpage) return;

  const popup = getModalPopup();
  const toolbarItems = popup.option("toolbarItems");

  const saveItem = findSaveToolbarItem(toolbarItems);

  if (tabId === "main") {
    mainForm.style.display = "";
    subpage.style.display = "none";
    subpage.innerHTML = "";

    if (saveItem) {
      saveItem.options.disabled = false;
    }

    popup.option("toolbarItems", toolbarItems);
    return;
  }

  mainForm.style.display = "none";
  subpage.style.display = "block";

  if (saveItem) {
    saveItem.options.disabled = true;
  }

  popup.option("toolbarItems", toolbarItems);
}


function loadEmployeeModalTab(link) {
  const body = getModalBody();

  if (!body) {
    return;
  }

  const subpage = body.querySelector("#employeeModalSubpage");

  if (!subpage) {
    return;
  }

  const url = link.getAttribute("data-tab-url");

  if (!url) {
    return;
  }

  setEmployeeModalView(
    link.getAttribute("data-employee-tab")
  );

  subpage.innerHTML = `
    <div style="
      padding:32px;
      text-align:center;
      color:var(--bs-secondary-color,#777);
    ">
      Yüklənir...
    </div>
  `;

  const separator = url.includes("?") ? "&" : "?";
  const embeddedUrl = url + separator + "embedded=1";

  fetch(embeddedUrl, {
    method: "GET",
    headers: {
      "X-Requested-With": "XMLHttpRequest"
    }
  })
    .then(function (response) {
      if (!response.ok) {
        throw new Error(
          t("server_returned_status", { status: response.status })
        );
      }

      return response.text();
    })
    .then(function (html) {
      subpage.innerHTML = html;
      relocateModalFlash(subpage);

      executeInjectedScripts(subpage);
    })
    .catch(function (error) {
      subpage.innerHTML = "";

      const slot = document.getElementById("modalFlashSlot");
      if (slot) {
        slot.innerHTML =
          '<div class="flash-wrap"><div class="flash flash-danger">' +
          t("js_tab_load_error") + error.message +
          "</div></div>";
      }
    });
}

function wireEmployeeModalTabs() {
  // Employee tabs use direct onclick handlers from form.html.
}

function openEmployeeModalTab(link) {
  const body = getModalBody();

  if (!body || !link) {
    return false;
  }

  if (link.classList.contains("disabled")) {
    return false;
  }

  body.querySelectorAll("[data-employee-tab]").forEach(function (item) {
    item.classList.remove("active");
  });

  link.classList.add("active");

  const tabId = link.getAttribute("data-employee-tab");

  if (tabId === "main") {
    setEmployeeModalView("main");
    return false;
  }

  loadEmployeeModalTab(link);

  return false;
}