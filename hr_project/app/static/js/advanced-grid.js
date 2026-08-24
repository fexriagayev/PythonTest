/* ===========================================================================
   Advanced DevExtreme DataGrid system
   ---------------------------------------------------------------------------
   This file keeps the public createAdvancedGrid(...) API used by the existing
   project pages, but the actual grid is DevExtreme DataGrid.

   Grid customisation is persisted in the DATABASE per user/per grid through:
       /core/grid-prefs/<key>

   Nothing is written automatically. Changes are marked dirty and are written
   only when the user selects "💾 Dəyişiklikləri yadda saxla".

   Native DevExtreme state stores:
     - column width
     - column order
     - column visibility
     - sorting
     - grouping
     - filtering

   The existing pages may continue to pass their old Tabulator-style column
   definitions. The converter below translates the common definitions.
   =========================================================================== */

function getCurrentLang() {
  return (window.CURRENT_LANG || "az");
}

const AGG_LABELS = {
  sum: t("grid_agg_sum"),
  avg: t("grid_agg_avg"),
  min: t("grid_agg_min"),
  max: t("grid_agg_max"),
  count: t("grid_agg_count"),
  count_distinct: t("grid_agg_count_distinct")
};

function defaultGridSettings() {
  return {
    titles: {},
    footerCalc: {},
    groupCalc: {},
    groupBy: [],
    columnOrder: null,
    hiddenFields: [],
    columnWidths: {},
    sorters: [],
    showFooter: true,
    showGroupFooter: true,
    devExtremeState: null
  };
}

function fetchGridSettingsFromServer(baseKey) {
  return fetch("/core/grid-prefs/" + encodeURIComponent(baseKey), {
    headers: { "X-Requested-With": "XMLHttpRequest" }
  })
    .then(function (r) {
      if (!r.ok) {
        throw new Error("GET grid-prefs failed with status " + r.status);
      }
      return r.json();
    })
    .then(function (data) {
      return data.settings || {};
    })
    .catch(function (err) {
      console.error(
        "Failed to load grid settings for '" + baseKey + "':",
        err
      );
      return {};
    });
}

function saveGridSettingsToServer(baseKey, settings) {

  if (!window._gridSaveQueues) {
    window._gridSaveQueues = {};
  }

  if (!window._gridSaveQueues[baseKey]) {
    window._gridSaveQueues[baseKey] = Promise.resolve();
  }

  const snapshot = JSON.parse(JSON.stringify(settings));

  window._gridSaveQueues[baseKey] =
    window._gridSaveQueues[baseKey]
      .catch(function () { })
      .then(function () {
        return fetch(
          "/core/grid-prefs/" + encodeURIComponent(baseKey),
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({ settings: snapshot })
          }
        );
      })
      .then(function (r) {
        if (!r.ok) {
          throw new Error(
            "POST grid-prefs failed with status " + r.status
          );
        }
        return r;
      })
      .catch(function (err) {
        console.error(
          "Failed to save grid settings for '" + baseKey + "':",
          err
        );
      });

  return window._gridSaveQueues[baseKey];
}

function aggregateOptionsForField(isNumericHint) {
  return isNumericHint
    ? ["sum", "avg", "min", "max", "count"]
    : ["count", "count_distinct"];
}


/* ---------------------------------------------------------------------------
   Old Tabulator formatter compatibility
   --------------------------------------------------------------------------- */

function makeCompatCell(options) {
  return {
    getValue: function () {
      return options.value;
    },
    getData: function () {
      return options.data;
    },
    getField: function () {
      return options.column && options.column.dataField;
    },
    getColumn: function () {
      return options.column;
    }
  };
}

function applyFormatterCompatibility(dx, original) {
  if (!original.formatter) {
    return;
  }

  if (original.formatter === "tickCross") {
    dx.cellTemplate = function (container, options) {
      const value = !!options.value;
      const el = container && container.jquery ? container[0] : container;
      if (el) {
        el.textContent = value ? "✓" : "✕";
        el.style.textAlign = "center";
      }
    };
    return;
  }

  if (typeof original.formatter === "function") {
    dx.cellTemplate = function (container, options) {
      const result = original.formatter(
        makeCompatCell(options),
        function () { },
        function () { }
      );

      if (result instanceof Node) {
        container.appendChild(result);
      } else {
        container.textContent = result == null ? "" : String(result);
      }
    };
  }
}


/* ---------------------------------------------------------------------------
   Tabulator-style column -> DevExtreme column
   --------------------------------------------------------------------------- */

function convertColumnsToDevExtreme(columns) {
  return (columns || []).map(function (original) {
    const dx = {};

    if (original.field != null) {
      dx.dataField = original.field;
    }

    if (original.title != null) {
      dx.caption = original.title;
    }

    if (original.width != null) {
      dx.width = original.width;
    }

    if (original.visible != null) {
      dx.visible = original.visible;
    }

    if (original.resizable != null) {
      dx.allowResizing = original.resizable;
    } else {
      dx.allowResizing = true;
    }

    dx.allowReordering =
      original.allowReordering !== undefined
        ? original.allowReordering
        : true;

    dx.allowHiding =
      original.allowHiding !== undefined
        ? original.allowHiding
        : true;

    dx.allowSorting =
      original.headerSort !== false &&
      original.allowSorting !== false;

    if (original.hozAlign === "center") {
      dx.alignment = "center";
    } else if (original.hozAlign === "right") {
      dx.alignment = "right";
    } else if (original.hozAlign === "left") {
      dx.alignment = "left";
    }

    switch (original.sorter) {
      case "number":
        dx.dataType = "number";
        break;
      case "date":
        dx.dataType = "date";
        break;
      case "datetime":
        dx.dataType = "datetime";
        break;
      case "boolean":
        dx.dataType = "boolean";
        break;
      default:
        dx.dataType = original.dataType || "string";
        break;
    }

    /*
     * Preserve DevExtreme-specific properties if a page already supplies them.
     */
    [
      "name",
      "cssClass",
      "format",
      "lookup",
      "calculateCellValue",
      "calculateDisplayValue",
      "calculateSortValue",
      "sortOrder",
      "sortIndex",
      "fixed",
      "fixedPosition",
      "showInColumnChooser",
      "allowFiltering",
      "allowGrouping",
      "filterOperations",
      "editorOptions"
    ].forEach(function (key) {
      if (original[key] !== undefined) {
        dx[key] = original[key];
      }
    });

    /*
     * Old Tabulator list header filters -> DevExtreme lookup/header filter.
     */
    if (
      original.headerFilter === "list" &&
      original.headerFilterParams &&
      original.headerFilterParams.values
    ) {
      dx.headerFilter = {
        visible: true,
        allowSearch: true
      };

      dx.lookup = {
        dataSource: Object.keys(original.headerFilterParams.values).map(
          function (key) {
            return {
              value: key,
              text: original.headerFilterParams.values[key]
            };
          }
        ),
        valueExpr: "value",
        displayExpr: "text"
      };
    }

    /*
     * Tabulator headerFilter: tickCross -> boolean header filter.
     */
    if (original.headerFilter === "tickCross") {
      dx.dataType = "boolean";
      dx.headerFilter = {
        visible: true
      };
    }

    /*
     * Tabulator explicit input filters are represented by DevExtreme's
     * filter row, which is enabled globally.
     */
    applyFormatterCompatibility(dx, original);

    /*
     * Old bottomCalc definitions.
     */
    if (original.bottomCalc) {
      dx.__initialBottomCalc = original.bottomCalc;
    }

    return dx;
  });
}


/* ---------------------------------------------------------------------------
   Data source
   --------------------------------------------------------------------------- */

function buildDevExtremeDataSource(options) {
  if (options.dataSource) {
    return options.dataSource;
  }

  if (options.data) {
    return options.data;
  }

  const url = options.ajaxURL || options.url;

  if (!url) {
    return [];
  }

  const params = options.ajaxParams || {};

  return new DevExpress.data.CustomStore({
    key: options.idField || "id",

    load: function () {
      const query = new URLSearchParams(params).toString();
      const requestUrl = query ? url + "?" + query : url;

      return fetch(requestUrl, {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      })
        .then(function (r) {
          if (!r.ok) {
            throw new Error(
              "Grid data request failed with status " + r.status
            );
          }
          return r.json();
        })
        .then(function (payload) {
          /*
           * Existing project APIs normally return a plain array.
           * Also accept {data: [...]}, {items: [...]}, or {results: [...]}.
           */
          if (Array.isArray(payload)) {
            return payload;
          }

          if (payload && Array.isArray(payload.data)) {
            return payload.data;
          }

          if (payload && Array.isArray(payload.items)) {
            return payload.items;
          }

          if (payload && Array.isArray(payload.results)) {
            return payload.results;
          }

          return [];
        });
    }
  });
}


/* ---------------------------------------------------------------------------
   Summary conversion
   --------------------------------------------------------------------------- */

function devExtremeSummaryType(type) {
  if (type === "avg") return "avg";
  if (type === "min") return "min";
  if (type === "max") return "max";
  if (type === "count") return "count";
  return "sum";
}

function applySummaries(grid, settings) {
  const totalItems = [];
  const groupItems = [];

  const firstColumn = grid
    .getVisibleColumns()
    .find(c => c && c.dataField);

  if (settings.showFooter !== false) {
    Object.keys(settings.footerCalc || {}).forEach(function (field) {
      const type = settings.footerCalc[field];

      if (!type || type === "count_distinct") {
        return;
      }

      totalItems.push({
        name: "footer_" + field,
        column: field,
        summaryType: devExtremeSummaryType(type),
        displayFormat: AGG_LABELS[type] + ": {0}"
      });
    });
  }

  if (settings.showGroupFooter !== false) {
    Object.keys(settings.groupCalc || {}).forEach(function (field) {
      const type = settings.groupCalc[field];

      if (!type || type === "count_distinct") {
        return;
      }

      groupItems.push({
        name: "group_" + field,
        column: field,
        summaryType: devExtremeSummaryType(type),
        displayFormat: AGG_LABELS[type] + ": {0}",
        showInGroupFooter: true,
        alignByColumn: true,
      });
    });
  }

  // Footer həmişə görünsün
  if (settings.showFooter !== false && totalItems.length === 0) {
    const firstColumn = grid.getVisibleColumns().find(
      c => c && c.dataField
    );

    if (firstColumn) {
      totalItems.push({
        column: firstColumn.dataField,
        summaryType: "count",
        customizeText: function () {
          return "\u00A0";
        }
      });
    }
  }

  if (settings.showGroupFooter !== false) {
    const firstColumn = grid.getVisibleColumns().find(
      function (c) {
        return c && c.dataField;
      }
    );

    if (firstColumn && groupItems.length === 0) {
      groupItems.push({
        column: firstColumn.dataField,
        summaryType: "count",
        showInGroupFooter: true,
        alignByColumn: true,
        customizeText: function () {
          return "\u00A0";
        }
      });
    }
  }

  grid.option("summary", {
    totalItems: totalItems,
    groupItems: groupItems,
    recalculateWhileEditing: false
  });

  const hasFooterItems = totalItems.length > 0;
  const hasGroupItems = groupItems.length > 0;

  grid.option("showColumnLines", true);

  if (!hasFooterItems && firstColumn) {
    totalItems.push({
      column: firstColumn.dataField,
      summaryType: "custom",
      customizeText: function () {
        return " ";
      }
    });
  }

  if (!hasGroupItems && firstColumn) {
    groupItems.push({
      column: firstColumn.dataField,
      summaryType: "custom",
      showInGroupFooter: true,
      customizeText: function () {
        return " ";
      }
    });
  }
}

/* ---------------------------------------------------------------------------
   Reliable best-fit helpers.
   Some DevExtreme builds do not expose bestFitColumn/bestFitColumns on the
   jQuery DataGrid instance. Measure rendered cells instead and assign an
   explicit pixel width. This also makes the resulting width persistable.
   --------------------------------------------------------------------------- */
function domElement(value) {
  if (!value) return null;
  if (value.jquery) return value[0] || null;
  return value.nodeType ? value : null;
}

function measureTextWidth(text, referenceElement) {
  const span = document.createElement("span");
  span.textContent = text == null ? "" : String(text);
  span.style.position = "absolute";
  span.style.visibility = "hidden";
  span.style.whiteSpace = "nowrap";
  span.style.width = "auto";
  span.style.height = "auto";

  if (referenceElement) {
    const cs = window.getComputedStyle(referenceElement);
    span.style.font = cs.font;
    span.style.fontFamily = cs.fontFamily;
    span.style.fontSize = cs.fontSize;
    span.style.fontWeight = cs.fontWeight;
    span.style.letterSpacing = cs.letterSpacing;
  }

  document.body.appendChild(span);
  const width = Math.ceil(span.getBoundingClientRect().width);
  span.remove();
  return width;
}

function bestFitOneColumn(grid, field) {
  if (!field) return;

  const visibleIndex = grid.getVisibleColumnIndex(field);
  if (visibleIndex == null || visibleIndex < 0) return;

  const column = grid.columnOption(field);
  if (!column) return;

  let maxWidth = measureTextWidth(
    column.caption || field,
    null
  ) + 36;

  /* Measure rendered data rows. */
  const items =
    grid.getDataSource()?.items?.() || [];

  const rowCount = Math.min(50, items.length);

  for (let rowIndex = 0; rowIndex < rowCount; rowIndex++) {
    const cell = domElement(
      grid.getCellElement(rowIndex, visibleIndex)
    );

    if (!cell) continue;

    const value = grid.cellValue(rowIndex, visibleIndex);
    const textWidth = measureTextWidth(value, cell) + 36;
    const scrollWidth = Number(cell.scrollWidth || 0) + 8;

    maxWidth = Math.max(maxWidth, textWidth, scrollWidth);
  }

  /* Reasonable limits prevent one long value from destroying the grid. */
  maxWidth = Math.max(60, Math.min(maxWidth, 600));

  grid.columnOption(field, "width", maxWidth);
}

function bestFitAllColumns(grid) {
  grid.beginUpdate();
  try {
    grid.getVisibleColumns().forEach(function (column) {
      if (column && column.dataField) {
        bestFitOneColumn(grid, column.dataField);
      }
    });
  } finally {
    grid.endUpdate();
    grid.updateDimensions();
  }
}

/* ---------------------------------------------------------------------------
   Header context menu
   ---------------------------------------------------------------------------
   IMPORTANT: keep DevExtreme's original header context menu intact.
   We only append the two custom actions requested by the application:
     - edit column caption
     - save grid changes
   --------------------------------------------------------------------------- */

/* ---------------------------------------------------------------------------
   Excel export
   ---------------------------------------------------------------------------
   Exports exactly what the grid currently shows: same visible columns (in
   their current order), same column captions as the header row, and the
   current sort/filter/grouping applied — via DevExtreme's own
   DevExpress.excelExporter.exportDataGrid, which reads all of that directly
   off the live grid instance. The synthetic row-number column added by
   createAdvancedGrid is skipped automatically (it's marked
   `allowExporting: false` when it's built).
   --------------------------------------------------------------------------- */

function exportGridToExcel(grid, baseKey) {
  if (
    typeof ExcelJS === "undefined" ||
    typeof saveAs === "undefined" ||
    typeof DevExpress === "undefined" ||
    !DevExpress.excelExporter
  ) {
    console.error(
      "Excel export libraries (ExcelJS/FileSaver) are not loaded."
    );
    if (DevExpress && DevExpress.ui && DevExpress.ui.notify) {
      DevExpress.ui.notify(t("grid_export_error"), "error", 3000);
    }
    return;
  }

  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet(t("grid_export_sheet_name"));

  DevExpress.excelExporter
    .exportDataGrid({
      component: grid,
      worksheet: worksheet,
      autoFilterEnabled: true
    })
    .then(function () {
      return workbook.xlsx.writeBuffer();
    })
    .then(function (buffer) {
      saveAs(
        new Blob([buffer], { type: "application/octet-stream" }),
        (baseKey || "grid") + ".xlsx"
      );
    })
    .catch(function (err) {
      console.error("Excel export failed:", err);
      if (
        typeof DevExpress !== "undefined" &&
        DevExpress.ui &&
        DevExpress.ui.notify
      ) {
        DevExpress.ui.notify(t("grid_export_error"), "error", 3000);
      }
    });
}

function buildHeaderMenuItems(e, grid, settings, numericFields, persistNow, markDirty, defaultCaptions, baseKey) {
  const field = e.column && e.column.dataField;
  if (!field) return [];

  return [
    {
      beginGroup: true,
      text: t("grid_best_fit_column"),
      onItemClick: function () {
        bestFitOneColumn(grid, field);
        markDirty();
      }
    },
    {
      text: settings.showFooter === false ? t("grid_hide_footer") : t("grid_show_footer"),
      onItemClick: function () {
        settings.showFooter = settings.showFooter === false;
        applySummaries(grid, settings);
        markDirty();
      }
    },
    {
      text: settings.showGroupFooter === false ? t("grid_hide_group_footer") : t("grid_show_group_footer"),
      onItemClick: function () {
        settings.showGroupFooter = settings.showGroupFooter === false;
        applySummaries(grid, settings);
        markDirty();
      }
    },
    {
      beginGroup: true,
      text: t("grid_group_by_column"),
      onItemClick: function () {
        grid.columnOption(field, "groupIndex", 0);
        markDirty();
      }
    },
    {
      text: t("grid_clear_grouping"),
      onItemClick: function () {
        grid.clearGrouping();
        markDirty();
      }
    },
    {
      beginGroup: true,
      text: t("grid_rename_column"),
      onItemClick: function () {
        const currentLang = getCurrentLang();
        const existing = settings.titles[field];
        const existingForLang =
          existing && typeof existing === "object" ? existing[currentLang] : (existing || null);
        const current = existingForLang || grid.columnOption(field, "caption") || field;
        const newTitle = prompt(t("grid_rename_column_prompt"), current);
        if (newTitle === null) return;

        settings.titles[field] =
          settings.titles[field] && typeof settings.titles[field] === "object"
            ? settings.titles[field]
            : {};

        if (newTitle.trim()) {
          settings.titles[field][currentLang] = newTitle.trim();
          grid.columnOption(field, "caption", newTitle.trim());
        } else {
          // Empty input = revert this language back to the default
          // (server-translated) caption.
          delete settings.titles[field][currentLang];
          grid.columnOption(field, "caption", defaultCaptions[field] || field);
        }
        markDirty();
      }
    },
    {
      text: t("grid_save_changes"),
      onItemClick: persistNow
    },
    {
      beginGroup: true,
      text: t("grid_export_excel"),
      onItemClick: function () {
        exportGridToExcel(grid, baseKey);
      }
    }
  ];
}

/* ---------------------------------------------------------------------------
   Row context menu
   ---------------------------------------------------------------------------
   We intentionally handle data-row right click on the actual rendered row
   instead of relying on DevExtreme's content context-menu event. This avoids
   conflicts with the application's existing popup/menu system and makes the
   Add/Edit/Delete popup actions reliable.
   --------------------------------------------------------------------------- */

function buildSimpleRowContextItems(data, meta, reloadGrid, grid, baseKey) {
  const idField = meta.idField || "id";
  const items = [];

  if (meta.addUrl) {
    items.push({
      label: t("grid_row_new"),
      action: function () {

        if (typeof meta.inlineAdd === "function") {
          meta.inlineAdd(meta.addUrl, reloadGrid);
          return;
        }

        if (typeof openFormModal === "function") {
          openFormModal(meta.addUrl, reloadGrid);
        }
      }
    });
  }

  if (meta.editUrlTemplate) {
    items.push({
      label: t("grid_row_edit"),
      action: function () {
        if (typeof openFormModal === "function") {
          const id = data[idField];
          const url =
            meta.editUrlTemplate.replace(
              "{id}",
              encodeURIComponent(id)
            );

          if (typeof meta.inlineEdit === "function") {
            meta.inlineEdit(url, reloadGrid, data);
            return;
          }

          if (typeof openFormModal === "function") {
            openFormModal(url, reloadGrid);
          }
        }
      }
    });
  }

  if (typeof meta.extraRowActions === "function") {
    const extraActions = meta.extraRowActions(data) || [];

    extraActions.forEach(function (extra) {
      if (!extra) return;

      const action = extra.action || extra.onItemClick;
      if (typeof action !== "function") return;

      items.push({
        label: extra.label || extra.text || t("grid_row_action_generic"),
        action: function () {
          action();
        }
      });
    });
  }

  if (meta.deleteUrlTemplate) {
    items.push({
      label: t("grid_row_delete"),
      action: function () {
        if (!confirm(t("grid_confirm_delete"))) return;

        fetch(
          meta.deleteUrlTemplate.replace(
            "{id}",
            encodeURIComponent(data[idField])
          ),
          {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" }
          }
        )
          .then(function (r) {
            if (!r.ok) {
              throw new Error("Delete failed with status " + r.status);
            }
            return r;
          })
          .then(function () {
            reloadGrid();
          })
          .catch(function (err) {
            console.error("Delete failed:", err);
            if (
              typeof DevExpress !== "undefined" &&
              DevExpress.ui &&
              DevExpress.ui.notify
            ) {
              DevExpress.ui.notify(
                t("grid_delete_error"),
                "error",
                3000
              );
            }
          });
      }
    });
  }

  if (items.length) {
    items.push({ separator: true });
  }

  items.push({
    label: t("grid_row_refresh"),
    action: reloadGrid
  });

  items.push({
    label: t("grid_export_excel"),
    action: function () {
      exportGridToExcel(grid, baseKey);
    }
  });

  return items;
}


function wireDataRowContextMenu(rowElement, data, meta, reloadGrid, grid, baseKey) {
  const el = domElement(rowElement);
  if (!el || el.__advancedRowContextMenuWired) return;

  el.__advancedRowContextMenuWired = true;

  el.addEventListener("contextmenu", function (event) {
    event.preventDefault();
    event.stopPropagation();

    const items = buildSimpleRowContextItems(
      data,
      meta,
      reloadGrid,
      grid,
      baseKey
    );

    if (typeof showContextMenu === "function") {
      showContextMenu(event.pageX, event.pageY, items);
    }
  });
}

/* ---------------------------------------------------------------------------
   Aggregate context-menu helpers
   --------------------------------------------------------------------------- */



/* ---------------------------------------------------------------------------
   Footer / group-footer context menu
   --------------------------------------------------------------------------- */

function buildFooterMenuItems(
  e,
  grid,
  settings,
  numericFields,
  persistNow,
  markDirty
) {
  const field = e.column && e.column.dataField;

  if (!field) {
    return [];
  }

  let targetStore;

  if (
    e.target === "groupFooter" ||
    (e.row && (
      e.row.rowType === "groupFooter" ||
      e.row.rowType === "group"
    ))
  ) {
    targetStore = settings.groupCalc;
  } else {
    targetStore = settings.footerCalc;
  }

  const isNumeric =
    numericFields.indexOf(field) !== -1;

  const aggOptions =
    aggregateOptionsForField(isNumeric);

  const items = [];

  aggOptions.forEach(function (type) {
    items.push({
      text:
        (targetStore[field] === type ? "✓ " : "") +
        "Σ " +
        AGG_LABELS[type],

      onItemClick: function () {
        targetStore[field] = type;
        applySummaries(grid, settings);
        markDirty();
      }
    });
  });

  items.push({
    text:
      (!targetStore[field] ? "✓ " : "") +
      t("grid_agg_none"),

    onItemClick: function () {
      delete targetStore[field];
      applySummaries(grid, settings);
      markDirty();
    }
  });

  items.push({
    beginGroup: true,
    text: t("grid_save_changes"),
    onItemClick: persistNow
  });

  return items;
}

/* ===========================================================================
   Main grid factory
   =========================================================================== */

function createAdvancedGrid(elementId, baseKey, tabulatorOptions, meta) {
  meta = meta || {};
  tabulatorOptions = tabulatorOptions || {};

  if (
    typeof DevExpress === "undefined" ||
    !DevExpress.ui ||
    !DevExpress.ui.dxDataGrid
  ) {
    throw new Error(
      "DevExtreme DataGrid is not loaded. Load DevExtreme before advanced-grid.js."
    );
  }

  const numericFields = meta.numericFields || [];
  const settings = defaultGridSettings();

  let applyingLoadedSettings = true;
  let gridSettingsLoaded = false;
  let gridSettingsDirty = false;

  const columns = convertColumnsToDevExtreme(
    tabulatorOptions.columns || []
  );

  // Every grid gets a leading row-number column by default (independent of
  // which page/module calls createAdvancedGrid) — plain sequential "1, 2,
  // 3, ..." across the whole dataset, not just the current page, and not
  // to be confused with a data "ID" column some grids also show. Opt out
  // per-grid with `meta.showRowNumber = false`.
  if (meta.showRowNumber !== false) {
    columns.unshift({
      caption: t("grid_row_number"),
      width: 50,
      alignment: "center",
      allowSorting: false,
      allowFiltering: false,
      allowGrouping: false,
      allowReordering: false,
      allowResizing: false,
      allowHiding: false,
      allowExporting: false,
      showInColumnChooser: false,
      fixed: true,
      fixedPosition: "left",
      cellTemplate: function (container, options) {
        const grid = options.component;
        const pageIndex = grid.pageIndex();
        const pageSize = grid.pageSize();
        container.text(String(pageIndex * pageSize + options.rowIndex + 1));
      }
    });
  }

  // Snapshot of the server-translated (current-language) default caption
  // per field, captured BEFORE any saved custom title is restored onto
  // the grid. Used to revert a column back to its default caption when
  // the user clears a custom rename for the current language.
  const defaultCaptions = {};
  columns.forEach(function (col) {
    if (col.dataField) {
      defaultCaptions[col.dataField] = col.caption;
    }
  });

  /*
   * Preserve the initial grouping used by existing pages.
   * The saved database state will override this when present.
   */
  if (tabulatorOptions.groupBy) {
    const initialGroupField = tabulatorOptions.groupBy;

    columns.forEach(function (col) {
      if (
        col.dataField === initialGroupField
      ) {
        col.groupIndex = 0;
      }
    });
  }

  const initialBottomCalcs = {};

  columns.forEach(function (col) {
    if (col.dataField && col.__initialBottomCalc) {
      initialBottomCalcs[col.dataField] =
        col.__initialBottomCalc;
      delete col.__initialBottomCalc;
    }
  });

  Object.keys(initialBottomCalcs).forEach(function (field) {
    settings.footerCalc[field] =
      initialBottomCalcs[field];
  });

  /*
   * Existing pages may still pass layout:"fitColumns", which was a Tabulator
   * setting. DevExtreme deliberately ignores it.
   */
  const dataSource = buildDevExtremeDataSource(tabulatorOptions);

  const pageSize =
    Number(tabulatorOptions.paginationSize) > 0
      ? Number(tabulatorOptions.paginationSize)
      : 15;

  const pagingEnabled =
    tabulatorOptions.pagination !== false;

  const options = {
    dataSource: dataSource,

    keyExpr:
      meta.idField ||
      tabulatorOptions.idField ||
      "id",

    // Fit the grid to the available viewport height on every page.
    // Pages with an explicit height still keep their requested height.
    width: "100%",
    height: function () {
      if (meta.height || tabulatorOptions.height) {
        return meta.height || tabulatorOptions.height;
      }

      var el = document.getElementById(elementId);
      if (!el) return Math.max(300, window.innerHeight - 280);

      var top = el.getBoundingClientRect().top;
      return Math.max(300, Math.floor(window.innerHeight - top - 16));
    },

    showBorders: true,
    columnAutoWidth: false,

    allowColumnResizing: true,
    columnResizingMode: "widget",

    allowColumnReordering: true,

    columnChooser: {
      enabled: true,
      mode: "select",
      title: t("grid_column_chooser_title"),
      search: {
        enabled: true
      }
    },

    sorting: {
      mode: "multiple"
    },

    selection: {
      mode: "single",
      showCheckBoxesMode: "none",
      allowSelectAll: false
    },

    filterRow: {
      visible: true,
      applyFilter: "auto"
    },

    headerFilter: {
      visible: true
    },

    searchPanel: {
      visible: false,
      searchVisibleColumnsOnly: false
    },

    groupPanel: {
      visible: true,
      emptyPanelText:
        t("grid_group_panel_empty")
    },

    grouping: {
      autoExpandAll: false
    },

    scrolling: {
      mode: "standard",
      showScrollbar: "always",
      useNative: true
    },

    paging: {
      enabled: pagingEnabled,
      pageSize: pageSize
    },

    pager: {
      visible: pagingEnabled,
      showPageSizeSelector: true,
      allowedPageSizes: [10, 15, 20, 30, 50, 100],
      showInfo: true,
      showNavigationButtons: true
    },

    remoteOperations: false,

    noDataText:
      tabulatorOptions.placeholder ||
      t("grid_no_data"),

    columns: columns,

    onContextMenuPreparing: function (e) {
      /*
       * Keep DevExtreme's original menu. Only append our small custom
       * header/footer actions. Data rows are handled by onRowPrepared below.
       */
      if (!e.items) {
        e.items = [];
      }

      try {
        if (e.target === "header" && e.column && e.column.dataField) {
          e.items.push.apply(
            e.items,
            buildHeaderMenuItems(
              e,
              grid,
              settings,
              numericFields,
              persistNow,
              markDirty,
              defaultCaptions,
              baseKey
            )
          );
          return;
        }

        const isFooter =
          e.target === "footer";

        const isGroupFooter =
          e.target === "groupFooter" ||
          (e.row && e.row.rowType === "groupFooter");

        if (
          (isFooter || isGroupFooter) &&
          e.column &&
          e.column.dataField
        ) {
          e.items.push.apply(
            e.items,
            buildFooterMenuItems(
              e,
              grid,
              settings,
              numericFields,
              persistNow,
              markDirty
            )
          );
        }
      } catch (err) {
        console.error("Grid context-menu failed:", err);
      }
    },

    onRowPrepared: function (e) {
      if (e.rowType !== "data" || !e.rowElement || !e.data) {
        return;
      }

      wireDataRowContextMenu(
        e.rowElement,
        e.data,
        meta,
        reloadGrid,
        e.component,
        baseKey
      );
    },

    onOptionChanged: function (e) {
      if (applyingLoadedSettings || !gridSettingsLoaded) {
        return;
      }

      /*
       * DevExtreme emits option changes for:
       *   columns[n].width
       *   columns[n].visible
       *   columns[n].visibleIndex
       *   columns[n].sortOrder
       *   columns[n].sortIndex
       *   columns[n].groupIndex
       *   filterValue / columns[n].filterValue
       *
       * All of these simply mark the grid dirty.
       * Nothing is POSTed automatically.
       */
      const fullName = e.fullName || "";

      if (
        fullName.indexOf("columns[") === 0 ||
        fullName.indexOf("sorting") === 0 ||
        fullName.indexOf("grouping") === 0 ||
        fullName.indexOf("filterValue") === 0
      ) {
        markDirty();
      }
    },

    onDisposing: function () {
      window.removeEventListener(
        "resize",
        resizeHandler
      );
    }

  };

  const grid =
    $("#" + elementId)
      .dxDataGrid(options)
      .dxDataGrid("instance");

  function reloadGrid() {
    return grid.refresh();
  }

  window.currentGridTable = grid;
  window.currentDevExtremeGrid = grid;

  /*
   * Compatibility with existing pages:
   * old code calls currentGridTable.setData() after modal add/edit/delete.
   */
  grid.setData = function () {
    return grid.refresh();
  };

  /*
   * Compatibility helpers for app.js.
   */
  grid.setGroupBy = function (field) {
    grid.clearGrouping();

    if (field) {
      grid.columnOption(field, "groupIndex", 0);
    }

    markDirty();
  };

  function markDirty() {
    if (applyingLoadedSettings || !gridSettingsLoaded) {
      return;
    }

    gridSettingsDirty = true;
  }


  /*
   * Capture DevExtreme's native state.
   */
  function getCurrentState() {
    const state =
      JSON.parse(
        JSON.stringify(
          grid.state()
        )
      );


    settings.devExtremeState = state;

    settings.columnWidths = {};
    settings.columnOrder = [];
    settings.hiddenFields = [];
    settings.sorters = [];

    (state.columns || []).forEach(function (col) {
      if (!col.dataField) {
        return;
      }

      if (col.width != null) {
        settings.columnWidths[col.dataField] =
          col.width;
      }

      if (col.visible === false) {
        settings.hiddenFields.push(
          col.dataField
        );
      }

      settings.columnOrder.push({
        field: col.dataField,
        visibleIndex:
          col.visibleIndex != null
            ? col.visibleIndex
            : 999999
      });

      if (col.sortOrder) {
        settings.sorters.push({
          field: col.dataField,
          dir: col.sortOrder
        });
      }
    });

    settings.columnOrder.sort(function (a, b) {
      return a.visibleIndex - b.visibleIndex;
    });

    settings.columnOrder =
      settings.columnOrder.map(function (x) {
        return x.field;
      });

    const columns = grid.option("columns") || [];

    settings.groupBy = [];

    columns.forEach(function (col) {
      if (
        col.groupIndex != null &&
        col.groupIndex >= 0
      ) {
        settings.groupBy.push({
          field: col.dataField,
          index: col.groupIndex
        });
      }
    });

    return state;
  }


  /*
   * Explicit manual database save.
   */
  function persistNow() {
    if (applyingLoadedSettings || !gridSettingsLoaded) {
      return;
    }

    try {
      getCurrentState();

      // NOTE: we deliberately do NOT re-capture every column's current
      // "caption" into settings.titles here. Captions are built fresh from
      // the server's t()-translated column titles on every page load, so
      // they always match the user's current language (app/i18n.py). If we
      // snapshotted whatever caption happened to be showing at persist
      // time (e.g. resizing a column, changing a footer option), that
      // snapshot would get restored on every future load — permanently
      // freezing the grid's column headers in whichever language was
      // active the last time anything was persisted, even after the user
      // switches language. settings.titles is populated ONLY by the
      // explicit "✎ Sütunun adını dəyiş" (rename column) action below,
      // which is a genuine, intentional user override that should persist
      // across languages.

      return saveGridSettingsToServer(
        baseKey,
        settings
      ).then(function () {
        gridSettingsDirty = false;
      });

    } catch (e) {
      console.error(
        "DevExtreme grid persistNow() failed:",
        e
      );
      return Promise.reject(e);
    }
  }


  /*
   * Convert the old database format to DevExtreme state when necessary.
   */
  function buildLegacyState(loaded) {
    const state = {
      columns: []
    };

    const currentColumns =
      grid.option("columns") || [];

    currentColumns.forEach(function (col, index) {
      if (!col.dataField) {
        return;
      }

      const field = col.dataField;

      const item = {
        dataField: field,
        visible:
          (loaded.hiddenFields || []).indexOf(
            field
          ) === -1,
        visibleIndex:
          loaded.columnOrder &&
            loaded.columnOrder.indexOf(field) !== -1
            ? loaded.columnOrder.indexOf(field)
            : index
      };

      if (
        loaded.columnWidths &&
        loaded.columnWidths[field] != null
      ) {
        item.width = Number(
          loaded.columnWidths[field]
        );
      }

      const sorter =
        (loaded.sorters || []).find(
          function (s) {
            return s.field === field;
          }
        );

      if (sorter) {
        item.sortOrder = sorter.dir;
        item.sortIndex =
          loaded.sorters.indexOf(sorter);
      }

      state.columns.push(item);
    });

    return state;
  }


  function applyLoadedSettings(loaded) {
    applyingLoadedSettings = true;

    try {
      Object.assign(
        settings,
        defaultGridSettings(),
        loaded || {}
      );

      if (settings.devExtremeState) {
        grid.state(
          settings.devExtremeState
        );
      } else if (
        Object.keys(settings.columnWidths || {}).length ||
        (settings.columnOrder || []).length ||
        (settings.hiddenFields || []).length ||
        (settings.sorters || []).length
      ) {
        grid.state(
          buildLegacyState(settings)
        );
      }

      /*
       * Restore custom titles — per-language. A title renamed while the
       * grid was in English only applies when English is active; switching
       * language falls back to the server's freshly-translated default
       * caption (already set on the column) unless THIS language also has
       * its own custom title saved.
       *
       * Backward compatible with old data saved before this fix, where
       * settings.titles[field] was a plain string (not a {lang: title}
       * object) — those are treated as an "az" title, since "az" was the
       * only language in use at that time.
       */
      const currentLang = getCurrentLang();
      Object.keys(settings.titles || {})
        .forEach(function (field) {
          let entry = settings.titles[field];
          if (typeof entry === "string") {
            entry = { az: entry };
          }
          const customTitle = entry && entry[currentLang];
          if (customTitle && grid.columnOption(field)) {
            grid.columnOption(
              field,
              "caption",
              customTitle
            );
          }
        });

      /*
       * Restore grouping from the old format if no native state existed.
       */
      if (
        !settings.devExtremeState &&
        Array.isArray(settings.groupBy)
      ) {
        grid.clearGrouping();

        settings.groupBy.forEach(function (g) {
          grid.columnOption(
            g.field,
            "groupIndex",
            g.index
          );
        });
      }

      applySummaries(
        grid,
        settings
      );

      gridSettingsDirty = false;

    } catch (e) {
      console.error(
        "Failed to apply grid settings for '" +
        baseKey +
        "':",
        e
      );
    } finally {
      /*
       * DevExtreme may emit several optionChanged events while applying
       * state. Keep persistence disabled until those events are finished.
       */
      setTimeout(function () {
        applyingLoadedSettings = false;
        gridSettingsLoaded = true;
        gridSettingsDirty = false;
      }, 400);
    }
  }


  fetchGridSettingsFromServer(baseKey)
    .then(function (loaded) {
      applyLoadedSettings(loaded);
    })
    .catch(function (err) {
      console.error(
        "Failed to initialize grid settings for '" +
        baseKey +
        "':",
        err
      );

      applyingLoadedSettings = false;
      gridSettingsLoaded = true;
    });


  // Keep the grid fitted to the visible page when the browser size changes.
  // DevExtreme recalculates its internal dimensions after the height changes.
  var resizeHandler = function () {
    if (meta.height || tabulatorOptions.height) return;

    try {
      var el = document.getElementById(elementId);
      if (!el) return;

      var top = el.getBoundingClientRect().top;
      var newHeight = Math.max(300, Math.floor(window.innerHeight - top - 16));
      grid.option("height", newHeight);
      grid.updateDimensions();
    } catch (err) {
      console.warn("Grid resize update failed for '" + baseKey + "':", err);
    }
  };

  window.addEventListener(
    "resize",
    resizeHandler
  );

  /*
   * Public helpers for external buttons/code.
   */
  grid._advancedGridPersist = persistNow;

  grid._advancedGridMarkDirty = markDirty;

  grid._advancedGridIsDirty = function () {
    return gridSettingsDirty;
  };

  return grid;
}


/* ---------------------------------------------------------------------------
   Native DevExtreme column chooser compatibility
   --------------------------------------------------------------------------- */
function openColumnChooser(table) {
  if (
    table &&
    typeof table.showColumnChooser === "function"
  ) {
    table.showColumnChooser();
  }
}


/* ---------------------------------------------------------------------------
   Explicit external save helper
   --------------------------------------------------------------------------- */
function saveAdvancedGrid(grid) {
  if (
    grid &&
    typeof grid._advancedGridPersist ===
    "function"
  ) {
    return grid._advancedGridPersist();
  }
}