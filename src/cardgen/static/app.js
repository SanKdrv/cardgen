(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  // --- примеры товаров -------------------------------------------------------

  const examplesNode = $("#examples-data");
  let examples = [];
  if (examplesNode) {
    try {
      examples = JSON.parse(examplesNode.textContent || "[]");
    } catch (error) {
      console.warn("Не удалось разобрать примеры", error);
    }
  }

  const specsContainer = $("#specs");

  function addSpecRow(key = "", value = "") {
    if (!specsContainer) return;
    const row = document.createElement("div");
    row.className = "spec-row";
    row.innerHTML =
      '<input type="text" name="spec_key" maxlength="80" placeholder="диапазон измерений">' +
      '<input type="text" name="spec_value" maxlength="300" placeholder="0–1,6 МПа">' +
      '<button type="button" class="icon-btn" data-remove-spec title="Удалить">×</button>';
    const inputs = row.querySelectorAll("input");
    inputs[0].value = key;
    inputs[1].value = value;
    specsContainer.appendChild(row);
    return row;
  }

  $("#add-spec")?.addEventListener("click", () => addSpecRow());

  specsContainer?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-spec]");
    if (!button) return;
    const rows = $$(".spec-row", specsContainer);
    if (rows.length > 1) {
      button.closest(".spec-row").remove();
    } else {
      rows[0].querySelectorAll("input").forEach((input) => {
        input.value = "";
      });
    }
  });

  $("#examples-select")?.addEventListener("change", (event) => {
    const index = event.target.value;
    if (index === "") return;
    const product = examples[Number(index)];
    if (!product) return;

    $("#name").value = product.name || "";
    $("#manufacturer").value = product.manufacturer || "";
    $("#category").value = product.category || "";
    $("#description").value = product.description || "";
    updateDescriptionCounter();

    if (specsContainer) {
      specsContainer.innerHTML = "";
      const specs = Object.entries(product.specs || {});
      if (specs.length === 0) {
        addSpecRow();
      } else {
        specs.forEach(([key, value]) => addSpecRow(key, value));
      }
    }
  });

  // --- счётчики и состояние отправки ---------------------------------------

  const description = $("#description");
  const descriptionCount = $("#description-count");

  function updateDescriptionCounter() {
    if (!description || !descriptionCount) return;
    descriptionCount.textContent = String(description.value.length);
  }

  description?.addEventListener("input", updateDescriptionCounter);
  updateDescriptionCounter();

  $("#card-form")?.addEventListener("submit", () => {
    const button = $("#submit-btn");
    if (!button) return;
    button.disabled = true;
    button.textContent = "Генерируем…";
  });

  // --- копирование и скачивание --------------------------------------------

  function readTarget(targetId) {
    const node = document.getElementById(targetId);
    if (!node) return "";
    if (node instanceof HTMLTextAreaElement || node instanceof HTMLInputElement) {
      return node.value;
    }
    return node.innerText;
  }

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    document.body.appendChild(helper);
    helper.select();
    try {
      document.execCommand("copy");
    } finally {
      helper.remove();
    }
  }

  function flash(button, text) {
    const original = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = original;
    button.textContent = text;
    setTimeout(() => {
      button.textContent = original;
      delete button.dataset.originalLabel;
    }, 1600);
  }

  document.addEventListener("click", async (event) => {
    const copyButton = event.target.closest("[data-copy-target]");
    if (copyButton) {
      const text = readTarget(copyButton.dataset.copyTarget);
      if (!text) return;
      try {
        await copyText(text);
        flash(copyButton, "Скопировано ✓");
      } catch (error) {
        console.error(error);
        flash(copyButton, "Не удалось");
      }
      return;
    }

    const downloadButton = event.target.closest("[data-download]");
    if (downloadButton) {
      const isJson = downloadButton.dataset.download === "json";
      const text = readTarget(isJson ? "json-data" : "markdown-data");
      if (!text) return;
      const blob = new Blob([text], {
        type: isJson ? "application/json;charset=utf-8" : "text/markdown;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = isJson ? "card.json" : "card.md";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      flash(downloadButton, "Скачано ✓");
    }
  });
})();
