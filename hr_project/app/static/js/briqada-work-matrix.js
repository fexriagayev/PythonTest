/*
 * "Obyektlər üzrə görülən işlər" matrisi — bax: app.services.briqada_work_service.
 *
 * Sütunlar: hər əsas obyekt öz QRUPU (DevExtreme-in native "grouped
 * columns" — bir sütun tərifinin öz DAXİLİNDƏ `columns: [...]` siyahısı
 * olması) kimi qurulur: [alt-obyektlər..., "Cəmi"]. Bütün qruplardan
 * sonra ayrıca (qrupsuz) "Yekun" sütunu.
 *
 * Sətirlər: DevExtreme-in group/master-detail xüsusiyyətlərindən İSTİFADƏ
 * OLUNMUR — sadəcə DÜZ (flat) sətir siyahısı qurulur, hər sətrin öz
 * `rowType`-ı var ("member" | "group_total" | "grand_total"),
 * `rowClass`-a görə fərqli stillə göstərilir (bax: app.css
 * .briqada-work-total-row).
 *
 * Redaktə: YALNIZ "member" sətirlərinin YARPAQ (Cəmi/Yekun olmayan)
 * xanaları redaktə oluna bilər — bax: onEditingStart.
 */

function initBriqadaWorkMatrix(config) {
  // config: { elementId, matrixUrl, cellUrl, readOnly }
  let grid = null;
  let matrixData = null;
  let loadSeq = 0;

  function fmt(value) {
    const n = Number(value || 0);
    return n.toLocaleString("az-AZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function buildColumns(data) {
    const columns = [
      {
        dataField: "row_label",
        caption: "",
        width: 220,
        fixed: true,
        fixedPosition: "left",
        allowEditing: false,
        cellTemplate: function (container, options) {
          const div = document.createElement("div");
          div.textContent = options.data.row_label;
          if (options.data.rowType !== "member") {
            div.style.fontWeight = "bold";
          } else if (options.data.indent) {
            div.style.paddingLeft = "16px";
          }
          container.appendChild(div);
        }
      }
    ];

    data.columns.forEach(function (col) {
      const subCols = col.sub.map(function (s) {
        return {
          dataField: "obj_" + s.obyekt_id,
          caption: s.name,
          width: 110,
          alignment: "right",
          format: { type: "fixedPoint", precision: 2 },
          allowEditing: true,
        };
      });
      // Əsas obyektin özü də (alt-obyekti olsun-olmasın) birbaşa iş
      // yazıla bilən bir "yarpaq" sütundur — alt-obyektlərdən ƏVVƏL göstərilir.
      subCols.unshift({
        dataField: "obj_" + col.obyekt_id,
        caption: col.sub.length ? "(əsas)" : col.name,
        width: 110,
        alignment: "right",
        format: { type: "fixedPoint", precision: 2 },
        allowEditing: true,
      });
      subCols.push({
        dataField: "cemi_" + col.obyekt_id,
        caption: "Cəmi",
        width: 110,
        alignment: "right",
        allowEditing: false,
        format: { type: "fixedPoint", precision: 2 },
        cssClass: "briqada-work-cemi-col",
      });
      columns.push({
        caption: col.name,
        columns: subCols,
      });
    });

    columns.push({
      dataField: "yekun",
      caption: "Yekun",
      width: 120,
      alignment: "right",
      allowEditing: false,
      format: { type: "fixedPoint", precision: 2 },
      cssClass: "briqada-work-yekun-col",
    });

    return columns;
  }

  function buildDataSource(data) {
    const rows = [];
    let rowSeq = 0;
    data.rows.forEach(function (grp) {
      grp.members.forEach(function (m) {
        const row = {
          id: "row_" + (++rowSeq),
          rowType: "member", briqada_id: m.briqada_id,
          row_label: m.name, indent: true,
          yekun: m.row_total,
        };
        data.columns.forEach(function (col) {
          row["obj_" + col.obyekt_id] = m.cells[col.obyekt_id] || 0;
          let groupSum = m.cells[col.obyekt_id] || 0;
          col.sub.forEach(function (s) {
            row["obj_" + s.obyekt_id] = m.cells[s.obyekt_id] || 0;
            groupSum += m.cells[s.obyekt_id] || 0;
          });
          row["cemi_" + col.obyekt_id] = Math.round(groupSum * 100) / 100;
        });
        rows.push(row);
      });
      const totalRow = {
        id: "row_" + (++rowSeq),
        rowType: "group_total", briqada_id: null,
        row_label: (grp.header_name || "—") + " — Cəmi",
        yekun: grp.group_total,
      };
      data.columns.forEach(function (col) {
        let groupSum = data.rows === undefined ? 0 : (grp.group_totals[col.obyekt_id] || 0);
        totalRow["obj_" + col.obyekt_id] = grp.group_totals[col.obyekt_id] || 0;
        col.sub.forEach(function (s) {
          totalRow["obj_" + s.obyekt_id] = grp.group_totals[s.obyekt_id] || 0;
        });
        totalRow["cemi_" + col.obyekt_id] = grp.group_totals[col.obyekt_id] || 0;
      });
      rows.push(totalRow);
    });

    const yekunRow = {
      id: "row_" + (++rowSeq),
      rowType: "grand_total", briqada_id: null,
      row_label: "Yekun", yekun: data.yekun_total,
    };
    data.columns.forEach(function (col) {
      yekunRow["obj_" + col.obyekt_id] = data.yekun_by_obyekt[col.obyekt_id] || 0;
      col.sub.forEach(function (s) {
        yekunRow["obj_" + s.obyekt_id] = data.yekun_by_obyekt[s.obyekt_id] || 0;
      });
      yekunRow["cemi_" + col.obyekt_id] = data.yekun_by_obyekt[col.obyekt_id] || 0;
    });
    rows.push(yekunRow);

    return rows;
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
        const columns = buildColumns(data);
        const dataSource = buildDataSource(data);
        if (!grid) {
          createGrid(columns, dataSource);
        } else {
          grid.option("editing.allowUpdating", !config.readOnly);
          grid.option("columns", columns);
          grid.option("dataSource", dataSource);
        }
        if (typeof config.onLoaded === "function") config.onLoaded(data);
        return data;
      });
  }

  function createGrid(columns, dataSource) {
    // DevExtreme-in "cell" redaktə rejimi Store-suz (sadə massiv) data
    // source üçün belə işləyir, amma hər sətrin öz UNİKAL açarı (key)
    // olmalıdır — məhz bunun üçün hər sətrə sintetik `id` (sıra nömrəsi)
    // əlavə edirik (bax: buildDataSource).
    grid = $("#" + config.elementId).dxDataGrid({
      dataSource: dataSource,
      columns: columns,
      keyExpr: "id",
      showBorders: true,
      columnAutoWidth: false,
      allowColumnResizing: true,
      scrolling: { mode: "standard", useNative: true },
      paging: { enabled: false },
      editing: {
        mode: "cell",
        allowUpdating: !config.readOnly,
        selectTextOnEditStart: true,
      },
      onEditingStart: function (e) {
        // YALNIZ "member" sətirlərinin yarpaq (Cəmi/Yekun olmayan)
        // xanaları redaktə oluna bilər.
        if (config.readOnly || e.data.rowType !== "member" || !e.column.allowEditing) {
          e.cancel = true;
        }
      },
      onRowUpdating: function (e) {
        // `e.newData` YALNIZ DƏYİŞƏN sahələri ehtiva edir (tək bir "obj_"
        // sahəsi) — bax: DevExtreme sənədləri. Dəyəri serverə göndəririk,
        // sonra (Cəmi/Yekun HƏMİŞƏ server-hesablanmış, doğru qalsın deyə)
        // BÜTÜN matrisi yenidən yükləyirik.
        const changedField = Object.keys(e.newData).find(function (k) {
          return k.indexOf("obj_") === 0;
        });
        if (!changedField) {
          e.cancel = true;
          return;
        }
        const obyektId = parseInt(changedField.slice(4), 10);
        const briqadaId = e.oldData.briqada_id;
        const amount = e.newData[changedField];
        // Lokal (dərhal görünən) yeniləmədən sonra serverə göndəririk;
        // server cavabı gələndə bütün grid (düzgün Cəmi/Yekun ilə)
        // yenidən qurulur.
        saveCell(briqadaId, obyektId, amount);
      },
      onCellPrepared: function (e) {
        if (e.rowType !== "data") return;
        if (e.data.rowType !== "member") {
          e.cellElement.classList.add("briqada-work-total-row");
        }
      }
    }).dxDataGrid("instance");
  }

  function saveCell(briqadaId, obyektId, amount) {
    return fetch(config.cellUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify({ briqada_id: briqadaId, obyekt_id: obyektId, amount: amount })
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
    getGrid: function () { return grid; }
  };
}
