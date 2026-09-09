/* ===========================================================================
   Tabel matrisi — əməkdaş × gün grid-i.
   createAdvancedGrid üzərində qurulub (əməkdaş siyahıları ilə EYNİ header/
   data/footer context menyuları, filter sətri, ixrac (Excel/PDF) burdan
   avtomatik gəlir). Yalnız gün sütunlarının rəngli/klikləmə davranışı
   Tabulator-uyğun `formatter` callback-i ilə xüsusi qurulur.

   Hələ heç bir dövr (TabelPeriod) yaradılmayıbsa (matrixUrl verilməyibsə),
   grid yenə DƏRHAL yaradılır — sadəcə BOŞ (sıfır sətir) — ki, istifadəçi
   "Generasiya et"-ə basmazdan əvvəl də cədvəlin necə görünəcəyini görsün.
   Ay/İl dəyişəndə setDaysInMonth() çağırılıb sütunlar yenidən qurula bilər.
   =========================================================================== */

function tabelCellStyle(code, hasKey) {
  if (!hasKey) return { bg: "#d9d9d9", color: "#666666" }; // aktiv olmayan gün — boz
  if (code === "İ" || code === "B" || code === "M") return { bg: "#e05353", color: "#ffffff" };
  if (code === "+") return { bg: "#8bc34a", color: "#1b3a00" };
  if (code === "-") return { bg: "#ffffff", color: "#000000" };
  return { bg: "#ffe066", color: "#5c4500" }; // İş buraxması kodları (X, NM, ÖM, ...)
}

function tabelCellIsEditable(code, hasKey) {
  return hasKey && (code === "+" || code === "-");
}

function initTabelMatrix(config) {
  /* config: {
       elementId, gridKey, matrixUrl (null = hələ dövr yoxdur, boş grid),
       cellUrl, daysInMonth, readOnly,
       onLoaded(data), onCellChanged(rowId, workDaysCount)
     } */
  let daysInMonth = config.daysInMonth || 30;
  let grid = null;

  function flattenRow(r) {
    const flat = {
      id: r.id,
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

  function paintCellElement(el, value, hasKey) {
    const style = tabelCellStyle(value, hasKey);
    el.textContent = hasKey && value ? value : "";
    el.style.backgroundColor = style.bg;
    el.style.color = style.color;
    el.style.textAlign = "center";
    el.style.fontWeight = "600";
    el.style.width = "100%";
    el.style.height = "100%";
    el.style.display = "flex";
    el.style.alignItems = "center";
    el.style.justifyContent = "center";
    el.style.cursor = (!config.readOnly && tabelCellIsEditable(value, hasKey)) ? "pointer" : "default";
  }

  function handleCellClick(rowId, day) {
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

        // DOM-u ƏL İLƏ boyamaq YOX — grid-in öz data mənbəyini yeniləyirik,
        // DevExtreme sətri özü yenidən render edir (formatter-i təzədən
        // çağırıb düzgün rənglə göstərir). Əvvəlki versiya birbaşa DOM-u
        // boyayırdı, amma work_days_count üçün edilən cellValue() çağırışı
        // bütün sətri yenidən render etdirdiyi üçün köhnə (data mənbəyindəki)
        // dəyərlə xananı yenidən "+" göstərirdi.
        if (grid) {
          const rowIndex = grid.getRowIndexByKey(rowId);
          if (rowIndex > -1) {
            grid.cellValue(rowIndex, "day_" + day, data.value);
            grid.cellValue(rowIndex, "work_days_count", data.work_days_count);
          }
        }

        if (typeof config.onCellChanged === "function") {
          config.onCellChanged(rowId, data.work_days_count);
        }
      });
  }

  function dayColumnDef(d) {
    return {
      field: "day_" + d,
      title: String(d),
      width: 34,
      hozAlign: "center",
      headerSort: false,
      allowFiltering: false,
      allowGrouping: false,
      formatter: function (cell) {
        const value = cell.getValue();
        const data = cell.getData();
        const hasKey = value !== null && value !== undefined;
        const el = document.createElement("div");
        paintCellElement(el, value, hasKey);
        if (!config.readOnly && tabelCellIsEditable(value, hasKey)) {
          el.onclick = function () {
            handleCellClick(data.id, d);
          };
        }
        return el;
      }
    };
  }

  function buildColumns() {
    const columns = [
      { field: "full_name", title: t("emp_col_full_name"), width: 190, fixed: true, fixedPosition: "left" },
      { field: "position", title: t("emp_col_position"), width: 150, fixed: true, fixedPosition: "left" },
      { field: "contract_number", title: t("tabel_col_contract_number"), width: 100, fixed: true, fixedPosition: "left" }
    ];
    for (let d = 1; d <= daysInMonth; d++) columns.push(dayColumnDef(d));
    columns.push({
      field: "work_days_count",
      title: t("tabel_col_work_days"),
      width: 90,
      sorter: "number",
      allowFiltering: false,
      fixed: true,
      fixedPosition: "right"
    });
    return columns;
  }

  // Excel/PDF ixracında da eyni rənglər saxlansın (bax: advanced-grid.js
  // exportGridToExcel/exportGridToPdf-ə ötürülən customizeCell hook-ları).
  function isDayField(field) {
    return typeof field === "string" && field.indexOf("day_") === 0;
  }

  function exportCustomizeCellExcel(options) {
    const gridCell = options.gridCell;
    const excelCell = options.excelCell;
    if (gridCell.rowType !== "data" || !gridCell.column || !isDayField(gridCell.column.dataField)) return;
    const value = gridCell.value;
    if (value === null || value === undefined) {
      excelCell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFD9D9D9" } };
    } else if (value !== "" && value !== "-") {
      const style = tabelCellStyle(value, true);
      excelCell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF" + style.bg.replace("#", "").toUpperCase() } };
    }
    excelCell.alignment = { horizontal: "center" };
  }

  function exportCustomizeCellPdf(options) {
    const gridCell = options.gridCell;
    const pdfCell = options.pdfCell;
    if (gridCell.rowType !== "data" || !gridCell.column || !isDayField(gridCell.column.dataField)) return;
    const value = gridCell.value;
    if (value === null || value === undefined) {
      pdfCell.backgroundColor = "#d9d9d9";
    } else if (value !== "" && value !== "-") {
      pdfCell.backgroundColor = tabelCellStyle(value, true).bg;
    }
  }

  // Modal təzəcə açılıb animasiya/reflow bitməmiş ola bilər — bir neçə
  // an sonra süni "resize" göndəririk ki, grid öz hündürlüyünü/enini
  // düzgün ölçüdə (klient sahəsinə tam uyğun) yenidən hesablasın. Bax:
  // advanced-grid.js-dəki toggleModalMaximize-in eyni texnikası.
  function kickResize() {
    setTimeout(function () {
      window.dispatchEvent(new Event("resize"));
    }, 60);
  }

  function createGrid() {
    grid = createAdvancedGrid(
      config.elementId,
      config.gridKey || "tabel_matrix",
      {
        data: [],
        pagination: true,
        paginationSize: 50,
        columns: buildColumns()
      },
      {
        idField: "id",
        exportCustomizeCellExcel: exportCustomizeCellExcel,
        exportCustomizeCellPdf: exportCustomizeCellPdf
      }
    );
    // QEYD: burada əlavə bir kickResize() ÇAĞIRMIRIQ — bu grid, adətən,
    // modalın öz maximize+resize ardıcıllığının (bax: tabel/period_modal.html)
    // İÇİNDƏ yaradılır; o, artıq öz resize siqnalını göndərir. Burada da
    // əlavə bir kick göndərsəydik, iki ayrı resize demək olar EYNİ anda
    // (fərqli gecikmələrlə) toqquşub bir-birinin ölçü hesablamasını "əzir"
    // və nəticədə hündürlük səhv (çox böyük/kiçik) çıxırdı.
  }

  function load() {
    if (!config.matrixUrl) {
      // Hələ heç bir dövr yaradılmayıb — boş grid onsuz da yaradılıb,
      // ediləcək başqa iş yoxdur.
      return Promise.resolve(null);
    }
    return fetch(config.matrixUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        daysInMonth = data.days_in_month || daysInMonth;
        const rows = (data.rows || []).map(flattenRow);
        grid.option("dataSource", rows);
        if (typeof config.onLoaded === "function") config.onLoaded(data);
        return data;
      });
  }

  function setDaysInMonth(newDays) {
    if (!newDays || newDays === daysInMonth) return;
    daysInMonth = newDays;
    if (grid) {
      grid.option("columns", buildColumns());
      kickResize();
    }
  }

  // Dövr hələ yaradılmayıbsa (Ay/İl sərbəst seçilə bilən "Yeni dövr"
  // forması), Ay/İl dəyişəndə matrisin MƏNBƏYİNİ (önizləmə <-> əsl
  // dövrün öz matrisi) DƏYİŞMƏK lazım gəlir — grid-i sıfırdan yaratmaq
  // əvəzinə (bu, DevExtreme instansını lazımsız dağıdıb-qurardı), sadəcə
  // `config`-i (bağlı closure-da) yeniləyib yenidən yükləyirik. `config`
  // obyekt REFERANSI dəyişmir — `handleCellClick`/formatter-lər onu HƏR
  // ÇAĞIRIŞDA təzədən oxuduğu üçün (yaradılış anında "yaddaşa
  // köçürülmür"), bu mutasiya avtomatik nəzərə alınır.
  function setSource(matrixUrl, cellUrl, readOnly) {
    config.matrixUrl = matrixUrl;
    config.cellUrl = cellUrl;
    config.readOnly = readOnly;
    return load();
  }

  createGrid();
  load();

  return {
    reload: load,
    setDaysInMonth: setDaysInMonth,
    setSource: setSource,
    getInstance: function () { return grid; }
  };
}
