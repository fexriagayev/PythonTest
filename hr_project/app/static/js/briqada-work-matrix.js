/*
 * "Obyektlər üzrə görülən işlər" matrisi — bax: app.services.briqada_work_service.
 *
 * ARTIQ DevExtreme dxDataGrid ÜZƏRİNDƏ QURULMUR — sadə (əl ilə qurulan)
 * <table> istifadə olunur. Səbəb: sol tərəfdəki "Müqavilə N" / "Full
 * Name" sütunları bir briqada rəhbərinin BÜTÜN BLOKU (öz sətri +
 * komanda üzvləri + "Cəmi" sətri) boyunca vizual olaraq BİRLƏŞDİRİLİR
 * (rowspan) — DevExtreme-in "cell" redaktə rejimi bunu dəstəkləmir.
 *
 * SƏTİR STRUKTURU (bax: matrix_row_structure() backend-də):
 *   - Sadə sətir (is_leader=false): 1 fiziki <tr> — Müqavilə N/Full
 *     Name/Briqada + obyekt xanaları birbaşa bu əməkdaşa aiddir.
 *   - Rəhbər bloku (is_leader=true): (üzv sayı + 1) fiziki <tr> —
 *     Müqavilə N/Full Name yalnız İLK sətirdə (rowspan ilə bütün
 *     bloku əhatə edir), "Briqada" sütununda hər üzvün adı öz sətrində,
 *     son sətirdə "Cəmi". Rəhbərin ÖZÜNÜN redaktə oluna bilən xanası
 *     YOXDUR.
 *
 * SÜTUN STRUKTURU əvvəlki kimi qalır: hər əsas obyekt öz qrupu
 * (alt-obyektlər + "Cəmi"), bütün qruplardan sonra ayrıca "Yekun".
 */

function initBriqadaWorkMatrix(config) {
  // config: { elementId, matrixUrl, cellUrl, readOnly }
  let matrixData = null;
  let loadSeq = 0;
  let root = null;

  function fmt(value) {
    const n = Number(value || 0);
    return n.toLocaleString("az-AZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function parseAmount(raw) {
    if (raw === null || raw === undefined) return 0;
    const cleaned = String(raw).trim().replace(",", ".").replace(/\s/g, "");
    if (cleaned === "" || cleaned === "-") return 0;
    const n = parseFloat(cleaned);
    return isNaN(n) ? 0 : n;
  }

  // Sütun "planı": hər əsas obyekt üçün onun yarpaq (redaktə oluna
  // bilən) obyekt ID-ləri + qrupun öz "Cəmi" sütunu.
  function buildColumnPlan(data) {
    return data.columns.map(function (col) {
      const leafIds = col.sub.length ? col.sub.map(function (s) { return s.obyekt_id; }) : [col.obyekt_id];
      const leafCaptions = col.sub.length ? col.sub.map(function (s) { return s.name; }) : [col.name];
      return { name: col.name, obyekt_id: col.obyekt_id, leafIds: leafIds, leafCaptions: leafCaptions };
    });
  }

  function groupCemi(cellsOrTotals, group) {
    let sum = 0;
    group.leafIds.forEach(function (oid) {
      sum += Number((cellsOrTotals && cellsOrTotals[oid]) || 0);
    });
    return Math.round(sum * 100) / 100;
  }

  function buildHeader(table, plan) {
    const thead = document.createElement("thead");
    const row1 = document.createElement("tr");
    const row2 = document.createElement("tr");

    ["briqada_work_col_contract", "briqada_work_col_fullname", "briqada_work_col_briqada"].forEach(function (key) {
      const th = document.createElement("th");
      th.rowSpan = 2;
      th.className = "briqada-work-row-header-col";
      th.textContent = t(key);
      row1.appendChild(th);
    });

    plan.forEach(function (group) {
      const th = document.createElement("th");
      th.colSpan = group.leafIds.length + 1;
      th.textContent = group.name;
      th.className = "briqada-work-group-sep";
      row1.appendChild(th);

      group.leafCaptions.forEach(function (caption) {
        const sub = document.createElement("th");
        sub.textContent = caption;
        row2.appendChild(sub);
      });
      const cemiTh = document.createElement("th");
      cemiTh.textContent = "Cəmi";
      cemiTh.className = "briqada-work-cemi-col briqada-work-group-sep";
      row2.appendChild(cemiTh);
    });

    const yekunTh = document.createElement("th");
    yekunTh.rowSpan = 2;
    yekunTh.className = "briqada-work-yekun-col";
    yekunTh.textContent = "Yekun";
    row1.appendChild(yekunTh);

    thead.appendChild(row1);
    thead.appendChild(row2);
    table.appendChild(thead);
  }

  function amountCell(value, keyType, keyId, obyektId, opts) {
    opts = opts || {};
    const td = document.createElement("td");
    td.className = "briqada-work-cell" + (opts.cssClass ? " " + opts.cssClass : "");
    const nonzero = Number(value || 0) !== 0;

    if (config.readOnly || !keyType) {
      td.textContent = fmt(value);
      if (nonzero) td.classList.add("briqada-work-nonzero");
      return td;
    }

    const input = document.createElement("input");
    input.type = "text";
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.className = "briqada-work-amount-input";
    input.value = fmt(value);
    if (nonzero) input.classList.add("briqada-work-nonzero");

    input.addEventListener("focus", function () {
      input.value = value ? String(value) : "";
      input.select();
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") input.blur();
    });
    input.addEventListener("focusout", function () {
      const amount = parseAmount(input.value);
      input.value = fmt(amount);
      input.classList.toggle("briqada-work-nonzero", amount !== 0);
      if (amount === Number(value || 0)) return; // dəyişməyib
      saveCell(keyType, keyId, obyektId, amount);
    });

    td.appendChild(input);
    return td;
  }

  function labelCell(text, opts) {
    opts = opts || {};
    const td = document.createElement("td");
    td.className = "briqada-work-row-label" + (opts.cssClass ? " " + opts.cssClass : "");
    if (opts.rowSpan) td.rowSpan = opts.rowSpan;
    if (opts.indent) td.style.paddingLeft = "16px";
    td.textContent = text || "";
    return td;
  }

  function buildRowCells(tr, plan, cellsSource, keyType, keyId) {
    plan.forEach(function (group) {
      group.leafIds.forEach(function (oid) {
        tr.appendChild(amountCell((cellsSource && cellsSource[oid]) || 0, keyType, keyId, oid));
      });
      tr.appendChild(amountCell(
        groupCemi(cellsSource, group), null, null, null,
        { cssClass: "briqada-work-cemi-col briqada-work-group-sep" }
      ));
    });
  }

  function buildBody(table, data, plan) {
    const tbody = document.createElement("tbody");

    data.rows.forEach(function (row, blockIdx) {
      // Hər briqada (əməkdaş bloku) arasında qalın xətt — birinci blokdan
      // ƏVVƏL yox (cədvəlin öz üst kənarı artıq var).
      const blockStartClass = blockIdx > 0 ? " briqada-work-block-start" : "";

      if (row.is_leader) {
        const blockRows = row.members.length + 1; // (rəhbər + üzvlər) + "Cəmi" sətri
        row.members.forEach(function (m, idx) {
          const tr = document.createElement("tr");
          if (idx === 0) {
            tr.className = blockStartClass.trim();
            tr.appendChild(labelCell(row.contract_number, { rowSpan: blockRows }));
            tr.appendChild(labelCell(row.full_name, { rowSpan: blockRows }));
          }
          const label = (m.is_freeform ? "* " : "") + m.name;
          const labelOpts = { indent: true };
          if (m.is_leader_self) labelOpts.cssClass = "briqada-work-leader-self";
          tr.appendChild(labelCell(label, labelOpts));
          const keyType = m.is_leader_self ? "employee" : "briqada";
          const keyId = m.is_leader_self ? m.employee_id : m.briqada_id;
          buildRowCells(tr, plan, m.cells, keyType, keyId);
          tr.appendChild(amountCell(m.row_total, null, null, null, { cssClass: "briqada-work-yekun-col" }));
          tbody.appendChild(tr);
        });

        const totalTr = document.createElement("tr");
        totalTr.classList.add("briqada-work-total-row");
        totalTr.appendChild(labelCell("Cəmi"));
        buildRowCells(totalTr, plan, row.group_totals, null, null);
        totalTr.appendChild(amountCell(row.group_total, null, null, null, { cssClass: "briqada-work-yekun-col" }));
        tbody.appendChild(totalTr);
      } else {
        const tr = document.createElement("tr");
        tr.className = blockStartClass.trim();
        tr.appendChild(labelCell(row.contract_number, { rowSpan: 1 }));
        tr.appendChild(labelCell(row.full_name, { rowSpan: 1 }));
        tr.appendChild(labelCell(""));
        buildRowCells(tr, plan, row.cells, "employee", row.employee_id);
        tr.appendChild(amountCell(row.row_total, null, null, null, { cssClass: "briqada-work-yekun-col" }));
        tbody.appendChild(tr);
      }
    });

    const yekunTr = document.createElement("tr");
    yekunTr.classList.add("briqada-work-total-row", "briqada-work-block-start");
    const yekunLabel = labelCell("Yekun");
    yekunLabel.colSpan = 3;
    yekunTr.appendChild(yekunLabel);
    buildRowCells(yekunTr, plan, data.yekun_by_obyekt, null, null);
    yekunTr.appendChild(amountCell(data.yekun_total, null, null, null, { cssClass: "briqada-work-yekun-col" }));
    tbody.appendChild(yekunTr);

    table.appendChild(tbody);
  }

  function render(data) {
    const container = document.getElementById(config.elementId);
    container.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "briqada-work-table-wrap";

    const table = document.createElement("table");
    table.className = "briqada-work-table";

    const plan = buildColumnPlan(data);
    buildHeader(table, plan);
    buildBody(table, data, plan);

    wrap.appendChild(table);
    container.appendChild(wrap);
    root = wrap;
  }

  function load() {
    const mySeq = ++loadSeq;
    if (!config.matrixUrl) return Promise.resolve(null);
    return fetch(config.matrixUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (mySeq !== loadSeq) return null;
        matrixData = data;
        config.readOnly = data.is_approved;
        render(data);
        if (typeof config.onLoaded === "function") config.onLoaded(data);
        return data;
      });
  }

  function saveCell(keyType, keyId, obyektId, amount) {
    const body = { obyekt_id: obyektId, amount: amount };
    body[keyType === "briqada" ? "briqada_id" : "employee_id"] = keyId;
    return fetch(config.cellUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) {
          if (typeof DevExpress !== "undefined" && DevExpress.ui && DevExpress.ui.notify) {
            DevExpress.ui.notify(data.error || "Xəta baş verdi.", "error", 4000);
          }
        }
        return load();
      });
  }

  return {
    load: load,
    setSource: function (matrixUrl, cellUrl) {
      config.matrixUrl = matrixUrl;
      config.cellUrl = cellUrl;
      return load();
    },
    saveCell: saveCell,
    getGrid: function () { return root; }
  };
}
