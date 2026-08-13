/* ===========================================================================
   Global DevExtreme UI layer
   ---------------------------------------------------------------------------
   Upgrades application-level controls outside the DataGrid/modal system:
   buttons, text inputs, number/date inputs, selects, textareas and checkboxes.
   Original HTML controls remain in the DOM so existing Flask FormData posts
   continue to work.
   =========================================================================== */

(function () {
  "use strict";

  function sync(field, value) {
    if (!field) return;
    if (field.type === "checkbox" || field.type === "radio") {
      field.checked = !!value;
    } else {
      field.value = value == null ? "" : value;
    }
    field.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function upgradeText(field) {
    if (!field || field.__dxGlobalEditor || field.disabled) return;
    $(field).dxTextBox({
      value: field.value || "",
      stylingMode: "outlined",
      mode: field.type === "password" ? "password" : "text",
      onValueChanged: function (e) { sync(field, e.value); }
    });
    field.__dxGlobalEditor = true;
  }

  function upgradeNumber(field) {
    if (!field || field.__dxGlobalEditor || field.disabled) return;
    const min = field.min !== "" ? Number(field.min) : undefined;
    const max = field.max !== "" ? Number(field.max) : undefined;
    const step = field.step && field.step !== "any" ? Number(field.step) : 1;
    $(field).dxNumberBox({
      value: field.value === "" ? null : Number(field.value),
      min: min,
      max: max,
      step: step,
      showSpinButtons: true,
      stylingMode: "outlined",
      onValueChanged: function (e) { sync(field, e.value == null ? "" : e.value); }
    });
    field.__dxGlobalEditor = true;
  }

  function upgradeDate(field) {
    if (!field || field.__dxGlobalEditor || field.disabled) return;
    $(field).dxDateBox({
      type: "date",
      value: field.value || null,
      displayFormat: "yyyy-MM-dd",
      useMaskBehavior: true,
      stylingMode: "outlined",
      onValueChanged: function (e) {
        let value = "";
        if (e.value instanceof Date && !isNaN(e.value.getTime())) {
          value = e.value.getFullYear() + "-" +
            String(e.value.getMonth() + 1).padStart(2, "0") + "-" +
            String(e.value.getDate()).padStart(2, "0");
        }
        sync(field, value);
      }
    });
    field.__dxGlobalEditor = true;
  }

  function upgradeSelect(field) {
    if (!field || field.__dxGlobalEditor || field.disabled) return;
    const wrapper = document.createElement("div");
    wrapper.className = "dx-global-editor-wrapper";
    field.parentNode.insertBefore(wrapper, field);
    wrapper.appendChild(field);

    const host = document.createElement("div");
    wrapper.appendChild(host);
    const items = Array.from(field.options || []).map(function (o) {
      return { value: o.value, text: o.textContent };
    });

    field.style.display = "none";
    $(host).dxSelectBox({
      dataSource: items,
      valueExpr: "value",
      displayExpr: "text",
      value: field.value,
      searchEnabled: items.length > 8,
      showClearButton: !field.required,
      stylingMode: "outlined",
      onValueChanged: function (e) { sync(field, e.value); }
    });
    field.__dxGlobalEditor = true;
  }

  function upgradeTextArea(field) {
    if (!field || field.__dxGlobalEditor || field.disabled) return;
    $(field).dxTextArea({
      value: field.value || "",
      minHeight: Math.max(80, Number(field.rows || 3) * 26),
      autoResizeEnabled: true,
      stylingMode: "outlined",
      onValueChanged: function (e) { sync(field, e.value); }
    });
    field.__dxGlobalEditor = true;
  }

  function upgradeCheckbox(field) {
    if (!field || field.__dxGlobalEditor || field.disabled) return;
    const label = field.id ? document.querySelector('label[for="' + CSS.escape(field.id) + '"]') : null;
    const text = label ? label.textContent.trim() : "";
    const host = document.createElement("div");
    host.className = "dx-global-checkbox";
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
    field.__dxGlobalEditor = true;
  }

  function upgradeRadioGroup(form) {
    const groups = {};
    form.querySelectorAll('input[type="radio"]').forEach(function (radio) {
      if (radio.__dxGlobalEditor || radio.disabled) return;
      const key = radio.name || ("__radio_" + Math.random());
      (groups[key] ||= []).push(radio);
    });

    Object.keys(groups).forEach(function (name) {
      const radios = groups[name];
      if (radios.length < 2) return;
      const first = radios[0];
      const host = document.createElement("div");
      host.className = "dx-global-radio-group";
      first.parentNode.insertBefore(host, first);

      const items = radios.map(function (r) {
        const label = r.parentElement && r.parentElement.textContent.trim();
        return { value: r.value, text: label || r.value };
      });
      const selected = radios.find(function (r) { return r.checked; });

      radios.forEach(function (r) {
        r.style.display = "none";
        r.__dxGlobalEditor = true;
      });

      $(host).dxRadioGroup({
        items: items,
        valueExpr: "value",
        displayExpr: "text",
        value: selected ? selected.value : null,
        layout: "horizontal",
        onValueChanged: function (e) {
          radios.forEach(function (r) {
            r.checked = String(r.value) === String(e.value);
            r.dispatchEvent(new Event("change", { bubbles: true }));
          });
        }
      });
    });
  }

  function upgradeButtons(root) {
    root.querySelectorAll("button.btn:not([data-dx-global]), a.btn:not([data-dx-global])").forEach(function (el) {
      if (el.closest(".dx-datagrid")) return;
      const text = el.textContent.trim();
      const isSubmit = el.tagName === "BUTTON" && el.type === "submit";
      $(el).dxButton({
        text: text,
        type: isSubmit ? "default" : "normal",
        stylingMode: isSubmit ? "contained" : "outlined",
        useSubmitBehavior: isSubmit
      });
      el.setAttribute("data-dx-global", "1");
    });
  }

  function upgrade(root) {
    if (!root || !window.DevExpress) return;
    const forms = root.matches && root.matches("form") ? [root] : Array.from(root.querySelectorAll("form"));
    forms.forEach(function (form) {
      form.querySelectorAll('input[type="text"], input[type="email"], input[type="password"]').forEach(upgradeText);
      form.querySelectorAll('input[type="number"]').forEach(upgradeNumber);
      form.querySelectorAll('input[type="date"]').forEach(upgradeDate);
      form.querySelectorAll("select").forEach(upgradeSelect);
      form.querySelectorAll("textarea").forEach(upgradeTextArea);
      form.querySelectorAll('input[type="checkbox"]').forEach(upgradeCheckbox);
      upgradeRadioGroup(form);
    });
    upgradeButtons(root);
  }

  window.upgradeDevExtremeUI = upgrade;

  document.addEventListener("DOMContentLoaded", function () {
    upgrade(document.body);
  });
})();
