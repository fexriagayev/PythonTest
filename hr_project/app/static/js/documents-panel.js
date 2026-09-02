/* ===========================================================================
   Generic 'Sənədlər' (documents) panel.
   ---------------------------------------------------------------------------
   One function used by EVERY module's documents tab (employee, tabel
   period, and anything added later) — see
   templates/partials/documents_panel.html and
   app/modules/documents/routes.py.
   =========================================================================== */

function initDocumentsPanel(gridId, ownerType, ownerId, opts) {
  opts = opts || {};
  const base = "/documents/" + ownerType + "/" + ownerId;

  const table = createAdvancedGrid(gridId, "documents_" + ownerType, {
    ajaxURL: base + "/api/records",
    pagination: true,
    paginationSize: 15,
    placeholder: t("doc_no_data"),
    columns: [
      { title: t("col_id"), field: "id", width: 60, sorter: "number" },
      { title: t("doc_col_filename"), field: "original_filename", headerFilter: "input" },
      { title: t("doc_col_type"), field: "document_type", headerFilter: "input" },
      { title: t("note_label"), field: "note", headerFilter: "input" },
      { title: t("doc_col_uploaded_at"), field: "uploaded_at", sorter: "string" },
    ],
  }, {
    idField: "id",
    addUrl: opts.canAdd ? base + "/add" : null,
    deleteUrlTemplate: opts.canDelete ? base + "/{id}/delete" : null,
    extraRowActions: function (data) {
      return [
        { label: t("doc_action_view"), action: function () { window.open(base + "/" + data.id + "/view", "_blank"); } },
        { label: t("doc_action_download"), action: function () { window.location.href = base + "/" + data.id + "/download"; } },
      ];
    },
  });

  const addBtn = opts.addBtnId ? document.getElementById(opts.addBtnId) : null;
  if (addBtn) {
    addBtn.addEventListener("click", function () {
      openFormModal(base + "/add", function () { table.setData(); });
    });
  }

  return table;
}
