/*
 * Minimal custom context-menu system.
 * Supports:
 *   - Header context menus
 *   - Row context menus
 *   - Nested submenus
 *   - Re-opening the menu repeatedly
 *   - Prevents the browser's native context menu
 */

function closeContextMenu() {
  const menu = window._activeCtxMenu;

  if (menu) {
    menu.remove();
    window._activeCtxMenu = null;
  }
}


function showContextMenu(x, y, items) {
  // Always remove an existing custom menu first.
  closeContextMenu();

  const menu = document.createElement("div");
  menu.className = "ctx-menu";

  // Prevent clicks/right-clicks inside our menu from reaching
  // the document handlers.
  menu.addEventListener("click", function (e) {
    e.stopPropagation();
  });

  menu.addEventListener("contextmenu", function (e) {
    e.preventDefault();
    e.stopPropagation();
  });


  function renderItems(container, list) {

    list.forEach(function (item) {

      // Separator
      if (item.separator) {
        const sep = document.createElement("div");
        sep.className = "ctx-menu-separator";
        container.appendChild(sep);
        return;
      }


      const row = document.createElement("div");

      row.className =
        "ctx-menu-item" +
        (item.checked ? " checked" : "") +
        (item.disabled ? " disabled" : "") +
        (item.menu && item.menu.length ? " has-submenu" : "");


      row.textContent =
        (item.checked ? "✓ " : "") +
        item.label;


      /*
       * Nested submenu
       */
      if (item.menu && item.menu.length) {

        const sub = document.createElement("div");

        sub.className = "ctx-menu ctx-submenu";

        renderItems(sub, item.menu);

        row.appendChild(sub);

      }


      /*
       * Normal menu action
       */
      if (!item.disabled && item.action) {

        row.addEventListener("click", function (e) {

          e.preventDefault();
          e.stopPropagation();

          // Close BEFORE executing the action.
          closeContextMenu();

          // Execute the selected action.
          item.action();

        });

      }


      container.appendChild(row);

    });

  }


  renderItems(menu, items);

  document.body.appendChild(menu);


  /*
   * Position menu.
   */
  let left = x;
  let top = y;

  menu.style.left = left + "px";
  menu.style.top = top + "px";


  /*
   * Make sure the menu stays inside the viewport.
   */
  const rect = menu.getBoundingClientRect();

  if (rect.right > window.innerWidth) {
    left = Math.max(0, window.innerWidth - rect.width - 5);
  }

  if (rect.bottom > window.innerHeight) {
    top = Math.max(0, window.innerHeight - rect.height - 5);
  }

  menu.style.left = left + "px";
  menu.style.top = top + "px";


  /*
   * Store active menu.
   */
  window._activeCtxMenu = menu;
}


/*
 * Clicking anywhere outside the custom menu closes it.
 */
document.addEventListener("click", function (e) {

  if (!e.target.closest(".ctx-menu")) {
    closeContextMenu();
  }

}, true);


/*
 * IMPORTANT:
 *
 * Always prevent the browser's native context menu unless the
 * right-click happened inside our custom menu.
 *
 * The capture phase is intentional. It runs before Tabulator
 * and before most other contextmenu handlers.
 */
document.addEventListener("contextmenu", function (e) {

  if (e.target.closest(".ctx-menu")) {
    return;
  }

  /*
   * If this is anywhere on the grid, suppress the browser menu.
   * The grid's own header/row handler will then open our menu.
   */
  if (
    e.target.closest(".tabulator") ||
    e.target.closest(".tabulator-header") ||
    e.target.closest(".tabulator-row")
  ) {
    e.preventDefault();
  }

}, true);