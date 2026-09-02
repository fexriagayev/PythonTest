/* ===========================================================================
   Tabel matrisi — əməkdaş × gün grid-i.
   createAdvancedGrid-dən İSTİFADƏ ETMİR: bu, sabit sütunlu adi grid deyil,
   hər ay üçün fərqli sayda (28-31) dinamik gün sütunu olan, xanaları rəngli
   və klikləməklə "" -> "+" -> "-" -> "" dövr edən xüsusi bir grid-dir.
   =========================================================================== */

function tabelCellStyle(code, hasKey) {
  if (!hasKey) return { bg: "#ffffff", color: "#000000" };
  if (code === "İ") return { bg: "#e05353", color: "#ffffff" };
  if (code === "+") return { bg: "#8bc34a", color: "#1b3a00" };
  if (code === "-" || code === "") return { bg: "#ffffff", color: "#000000" };
  return { bg: "#ffe066", color: "#5c4500" }; // İş buraxması kodları (X, NM, ÖM, ...)
}

function tabelCellIsEditable(code, hasKey) {
  return hasKey && (code === "" || code === "+" || code === "-");
}

function initTabelMatrix(config) {
  /* config: {
       elementId, matrixUrl, cellUrl, daysInMonth, readOnly,
       onLoaded(data), onCellChanged(rowId, workDaysCount)
     } */
  let daysInMonth = config.daysInMonth;

  function flattenRow(r) {
    const flat = {
      id: r.id,
      row_no: r.row_no,
      full_name: r.full_name,
      position: r.position,
      contract_number: r.contract_number,
      work_days_count: r.work_days_count
    };
    for (let d = 1; d <= daysInMonth; d++) {
      const key = String(d);
      flat["day_" + d] = Object.prototype.hasOwnProperty.call(r.day_marks || {}, key)
        ? r.day_marks[key]
        : null;
    }
    return flat;
  }

  function paintCell(el, value, hasKey) {
    const style = tabelCellStyle(value, hasKey);
    el.textContent = hasKey && value ? value : "";
    el.style.backgroundColor = style.bg;
    el.style.color = style.color;
    el.style.textAlign = "center";
    el.style.fontWeight = "600";
    el.style.cursor = (!config.readOnly && tabelCellIsEditable(value, hasKey)) ? "pointer" : "default";
  }

  function handleCellClick(rowId, day, el) {
    fetch(config.cellUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({ row_id: rowId, day: day })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) {
          if (typeof DevExpress !== "undefined" && DevExpress.ui && DevExpress.ui.notify) {
            DevExpress.ui.notify(data.error || t("tabel_cell_error"), "error", 3000);
          } else {
            alert(data.error || t("tabel_cell_error"));
          }
          return;
        }
        paintCell(el, data.value, true);
        if (typeof config.onCellChanged === "function") {
          config.onCellChanged(rowId, data.work_days_count);
        }
      });
  }

  function dayColumn(d) {
    return {
      dataField: "day_" + d,
      caption: String(d),
      width: 34,
      alignment: "center",
      allowSorting: false,
      allowFiltering: false,
      allowEditing: false,
      allowExporting: true,
      cellTemplate: function (container, options) {
        const el = container && container.jquery ? container[0] : container;
        const value = options.value;
        const hasKey = value !== null && value !== undefined;
        paintCell(el, value, hasKey);
        if (!config.readOnly && tabelCellIsEditable(value, hasKey)) {
          el.onclick = function () { handleCellClick(options.data.id, d, el); };
        } else {
          el.onclick = null;
        }
      }
    };
  }

  const columns = [
    { dataField: "row_no", caption: t("tabel_col_no"), width: 50, allowEditing: false, fixed: true, fixedPosition: "left" },
    { dataField: "full_name", caption: t("emp_col_full_name"), width: 170, allowEditing: false, fixed: true, fixedPosition: "left" },
    { dataField: "position", caption: t("emp_col_position"), width: 150, allowEditing: false, fixed: true, fixedPosition: "left" },
    { dataField: "contract_number", caption: t("tabel_col_contract_number"), width: 60, allowEditing: false, fixed: true, fixedPosition: "left" }
  ];
  for (let d = 1; d <= daysInMonth; d++) columns.push(dayColumn(d));
  columns.push({
    dataField: "work_days_count",
    caption: t("tabel_col_work_days"),
    width: 90,
    allowEditing: false,
    fixed: true,
    fixedPosition: "right"
  });

  const instance = $("#" + config.elementId)
    .dxDataGrid({
      dataSource: [],
      keyExpr: "id",
      showBorders: true,
      columnAutoWidth: false,
      allowColumnResizing: true,
      scrolling: { mode: "standard", useNative: true, columnRenderingMode: "virtual" },
      columns: columns
    })
    .dxDataGrid("instance");

  function load() {
    return fetch(config.matrixUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        daysInMonth = data.days_in_month || daysInMonth;
        const rows = (data.rows || []).map(flattenRow);
        instance.option("dataSource", rows);
        if (typeof config.onLoaded === "function") config.onLoaded(data);
        return data;
      });
  }

  function excelFillForCode(value) {
    if (value === null || value === undefined || value === "" || value === "-") return null;
    const style = tabelCellStyle(value, true);
    return { type: "pattern", pattern: "solid", fgColor: { argb: "FF" + style.bg.replace("#", "").toUpperCase() } };
  }

  function exportExcel(fileName) {
    if (typeof ExcelJS === "undefined" || typeof saveAs === "undefined" || !DevExpress.excelExporter) {
      console.error("Excel export libraries are not loaded.");
      return;
    }
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet(t("tabel_export_sheet_name"));
    DevExpress.excelExporter
      .exportDataGrid({
        component: instance,
        worksheet: worksheet,
        customizeCell: function (options) {
          const gridCell = options.gridCell;
          const excelCell = options.excelCell;
          if (
            gridCell.rowType === "data" &&
            gridCell.column &&
            gridCell.column.dataField &&
            gridCell.column.dataField.indexOf("day_") === 0
          ) {
            const fill = excelFillForCode(gridCell.value);
            if (fill) excelCell.fill = fill;
            excelCell.alignment = { horizontal: "center" };
          }
        }
      })
      .then(function () { return workbook.xlsx.writeBuffer(); })
      .then(function (buffer) {
        saveAs(new Blob([buffer], { type: "application/octet-stream" }), (fileName || "tabel") + ".xlsx");
      })
      .catch(function (err) { console.error("Excel export failed:", err); });
  }

  function exportPdf(fileName) {
    /* DevExtreme-in öz pdf_exporter-i versiyalar arası uyğunsuzluqlar
       yaradır (customizeCell forması dəyişkəndir), ona görə burada
       rəngləri qoruyan ən etibarlı üsul: grid-in görünən sahəsini
       html2canvas ilə "şəkil" kimi çəkib jsPDF-ə yerləşdirmək — istifadəçi
       ekranda nə görürsə, PDF-də də tam eynisi olur. */
    const gridElement = document.getElementById(config.elementId);
    if (typeof html2canvas === "undefined" || !window.jspdf) {
      console.error("PDF export libraries are not loaded.");
      return;
    }
    html2canvas(gridElement, { scale: 2 }).then(function (canvas) {
      const imgData = canvas.toDataURL("image/png");
      const jsPDF = window.jspdf.jsPDF;
      const pdf = new jsPDF({
        orientation: "landscape",
        unit: "pt",
        format: [canvas.width * 0.75 + 40, canvas.height * 0.75 + 40]
      });
      pdf.addImage(imgData, "PNG", 20, 20, canvas.width * 0.75, canvas.height * 0.75);
      pdf.save((fileName || "tabel") + ".pdf");
    });
  }

  load();

  return { instance: instance, reload: load, exportExcel: exportExcel, exportPdf: exportPdf };
}
