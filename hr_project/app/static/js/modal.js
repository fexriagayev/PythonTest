/* ===========================================================================
   DevExtreme modal/form system
   ---------------------------------------------------------------------------
   - Uses DevExtreme dxPopup for every Add/Edit modal.
   - Uses DevExtreme editors for standard form controls.
   - Keeps the existing server-rendered <form> and FormData submission, so
     existing Flask routes and validation do not need to change.
   - Forms use a shared responsive layout defined by modal_form_base.html.
   =========================================================================== */

function ensureModalRoot() {
  let root = document.getElementById("appModal");
  if (root && root.__dxPopup) return root;

  if (root) {
    root.remove();
  }

  root = document.createElement("div");
  root.id = "appModal";
  document.body.appendChild(root);

  $(root).dxPopup({
    visible: false,
    deferRendering: false,
    dragEnabled: true,
    hideOnOutsideClick: false,
    showCloseButton: true,
    resizeEnabled: true,
    shading: true,
    width: "min(960px, 94vw)",
    height: "auto",
    maxHeight: "92vh",
    showTitle: true,
    title: "Forma",
    toolbarItems: [
      {
        toolbar: "bottom",
        location: "after",
        widget: "dxButton",
        options: {
          text: "Ləğv et",
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
        toolbar: "bottom",
        location: "after",
        widget: "dxButton",
        options: {
          text: "Yadda saxla",
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
    }
  });

  root.__dxPopup = $(root).dxPopup("instance");

  return root;
}

function getModalPopup() {
  return ensureModalRoot().__dxPopup;
}

function getModalBody() {
  ensureModalRoot();
  return document.getElementById("modalBody");
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
  }
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
    state.title || "Əməkdaş"
  );

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

  $(field).dxTextArea({
    value: field.value || "",
    minHeight: Math.max(80, Number(field.rows || 3) * 26),
    autoResizeEnabled: true,
    stylingMode: "outlined",
    onValueChanged: function (e) {
      syncNativeValue(field, e.value);
    }
  });

  field.__dxEditor = $(field).dxTextArea("instance");
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
    setLastAction("Formanı yadda saxlamağa çalışdı: " + actionUrl);

    const formData = new FormData(form);

    /* Disable the footer Save button while the request is running. */
    const popup = getModalPopup();
    const saveButton = popup.option("toolbarItems")[1];
    if (saveButton && saveButton.options) {
      saveButton.options.disabled = true;
      saveButton.options.text = "Yadda saxlanılır...";
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
            "Server " + r.status + " qaytardı (" + actionUrl + ")"
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
                    "Server " + r.status + " qaytardı (" + data.reload_url + ")"
                  );
                }
                return r.text();
              })
              .then(function (html) {
                body.innerHTML = html;

                const title = getModalTitleFromHtml(html);
                popup.option("title", title || "Forma");

                executeInjectedScripts(body);
                wireModalForm(onSavedCallback);

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
          executeInjectedScripts(body);
          wireModalForm(onSavedCallback);
        }
        return data;
      })
      .catch(function (err) {
        showErrorPopup(
          "Formanı yadda saxlamaq mümkün olmadı: " + err.message,
          err.stack || ""
        );
        throw err;
      })
      .finally(function () {
        const currentItems = popup.option("toolbarItems");
        if (currentItems && currentItems[1] && currentItems[1].options) {
          currentItems[1].options.disabled = false;
          currentItems[1].options.text = "Yadda saxla";
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
  return heading ? heading.textContent.trim() : "Forma";
}

const modalStateStack = [];

function openFormModal(url, onSavedCallback) {
  setLastAction("Forma açmağa çalışdı: " + url);

  const popup = getModalPopup();
  const body = getModalBody();

  /*
   * Hazırkı modalı yadda saxla.
   */
  if (body && body.innerHTML.trim()) {
    modalStateStack.push({
      html: body.innerHTML,
      title: popup.option("title"),
      onSavedCallback: onSavedCallback
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
          "Server " + r.status + " qaytardı (" + url + ")"
        );
      }

      return r.text();
    })
    .then(function (html) {
      body.innerHTML = html;

      const title = getModalTitleFromHtml(html);
      popup.option("title", title || "Forma");

      executeInjectedScripts(body);
      wireModalForm(onSavedCallback);

      popup.show();
    })
    .catch(function (err) {
      restoreParentModal();

      showErrorPopup(
        "Forma yüklənmədi: " + err.message,
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

  const saveItem = toolbarItems.find(function (item) {
    return item.options && item.options.text === "Yadda saxla";
  });

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
          "Server " + response.status + " qaytardı"
        );
      }

      return response.text();
    })
    .then(function (html) {
      subpage.innerHTML = html;

      executeInjectedScripts(subpage);
    })
    .catch(function (error) {
      subpage.innerHTML = `
        <div class="flash flash-danger">
          Bölmə yüklənmədi: ${error.message}
        </div>
      `;
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