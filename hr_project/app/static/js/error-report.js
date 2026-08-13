/* ===========================================================================
   DevExtreme error reporting popup.
   =========================================================================== */

window._lastAction = "Səhifə açıldı: " + window.location.pathname;

function setLastAction(description) {
  window._lastAction = description + " (" + new Date().toLocaleString() + ")";
}

function ensureErrorModalRoot() {
  let root = document.getElementById("errorModal");
  if (root && root.__dxPopup) return root;

  if (root) root.remove();
  root = document.createElement("div");
  root.id = "errorModal";
  document.body.appendChild(root);

  $(root).dxPopup({
    visible: false,
    width: "min(560px, 92vw)",
    maxHeight: "90vh",
    showTitle: true,
    title: "⚠ Xəta baş verdi",
    showCloseButton: true,
    dragEnabled: true,
    shading: true,
    hideOnOutsideClick: true,
    contentTemplate: function (container) {
      const wrap = document.createElement("div");
      wrap.className = "dx-error-popup-content";
      wrap.innerHTML =
        '<div id="errorModalMessage" class="error-modal-message"></div>' +
        '<div id="errorModalStatus" class="error-modal-status"></div>' +
        '<div class="dx-error-actions">' +
        '  <div id="errorModalSendBtn"></div>' +
        '  <div id="errorModalCloseBtn"></div>' +
        '</div>';
      container.append(wrap);

      $(wrap.querySelector("#errorModalSendBtn")).dxButton({
        text: "🐞 Developerə göndər",
        type: "danger",
        stylingMode: "contained"
      });
      $(wrap.querySelector("#errorModalCloseBtn")).dxButton({
        text: "Bağla",
        stylingMode: "outlined",
        onClick: hideErrorPopup
      });
    }
  });

  root.__dxPopup = $(root).dxPopup("instance");
  return root;
}

function hideErrorPopup() {
  const root = document.getElementById("errorModal");
  if (root && root.__dxPopup) root.__dxPopup.hide();
}

function showErrorPopup(message, stack) {
  const root = ensureErrorModalRoot();
  const popup = root.__dxPopup;
  const messageEl = document.getElementById("errorModalMessage");
  const statusEl = document.getElementById("errorModalStatus");
  const sendEl = document.getElementById("errorModalSendBtn");

  if (messageEl) messageEl.textContent = message || "Naməlum xəta baş verdi.";
  if (statusEl) statusEl.textContent = "";

  const sendButton = sendEl ? $(sendEl).dxButton("instance") : null;
  if (sendButton) {
    sendButton.option("disabled", false);
    sendButton.option("onClick", function () {
      sendButton.option("disabled", true);
      if (statusEl) statusEl.textContent = "Ekran şəkli çəkilir və göndərilir...";

      const finish = function (screenshotDataUrl) {
        fetch("/core/report-error", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
          },
          body: JSON.stringify({
            message: message || "",
            stack: stack || "",
            url: window.location.href,
            lastAction: window._lastAction || "",
            screenshot: screenshotDataUrl || ""
          })
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (statusEl) {
              statusEl.textContent = data.email_sent
                ? "✓ Göndərildi. Developer məlumatlandırıldı."
                : "✓ Qeydə alındı (email tənzimlənməyib, amma məlumat sistemdə saxlanıldı).";
            }
          })
          .catch(function () {
            if (statusEl) {
              statusEl.textContent = "Göndərmək mümkün olmadı. Zəhmət olmasa admin ilə əlaqə saxlayın.";
            }
            sendButton.option("disabled", false);
          });
      };

      if (window.html2canvas) {
        html2canvas(document.body, { logging: false, useCORS: true })
          .then(function (canvas) { finish(canvas.toDataURL("image/png")); })
          .catch(function () { finish(""); });
      } else {
        finish("");
      }
    });
  }

  popup.show();
}

window.addEventListener("error", function (e) {
  showErrorPopup(e.message, e.error && e.error.stack ? e.error.stack : "");
});

window.addEventListener("unhandledrejection", function (e) {
  const reason = e.reason || {};
  showErrorPopup(reason.message || String(reason), reason.stack || "");
});
