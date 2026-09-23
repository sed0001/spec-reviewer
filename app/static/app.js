// spec-reviewer — веб-панель (vanilla JS, работает через REST API)
/* global document, fetch, location */
"use strict";

// ---------------------------------------------------------------------------
// Утилиты
// ---------------------------------------------------------------------------
async function api(path, options) {
  const resp = await fetch(path, options);
  let data = null;
  try {
    data = await resp.json();
  } catch (_e) {
    data = null;
  }
  if (!resp.ok) {
    const detail = data && data.detail;
    let message = "Ошибка запроса " + resp.status;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) {
      message = detail.map((d) => (d.msg || JSON.stringify(d))).join("; ");
    }
    throw new Error(message);
  }
  return data;
}

function esc(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtDate(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("ru-RU");
  } catch (_e) {
    return String(value);
  }
}

function showError(targetId, message) {
  const target = document.getElementById(targetId);
  if (target) {
    target.innerHTML = message
      ? '<div class="notice notice-error">' + esc(message) + "</div>"
      : "";
  }
}

// ---------------------------------------------------------------------------
// Навигация по вкладкам
// ---------------------------------------------------------------------------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
  });
});

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
async function refreshHealth() {
  const el = document.getElementById("health");
  try {
    const h = await api("/health");
    const llm = h.llm_configured ? "LLM: ключ есть" : "LLM: ключ не задан";
    el.textContent = "Сервис работает · " + llm;
    el.style.background = "var(--ok-bg)";
  } catch (_e) {
    el.textContent = "Сервис недоступен";
    el.style.background = "var(--danger-bg)";
  }
}
// ---------------------------------------------------------------------------
// Раздел «Документы»
// ---------------------------------------------------------------------------
async function loadDocuments() {
  const el = document.getElementById("doc-list");
  try {
    const data = await api("/documents");
    renderDocuments(el, data.documents || []);
  } catch (e) {
    el.innerHTML = '<p class="empty">' + esc(e.message) + "</p>";
  }
}

function renderDocuments(el, documents) {
  if (!documents.length) {
    el.innerHTML = '<p class="empty">Пока нет документов. Добавьте первый выше.</p>';
    return;
  }
  el.innerHTML = documents
    .map(
      (d) =>
        '<div class="row">' +
        '<div><div class="title">' + esc(d.title) + "</div>" +
        '<div class="meta">ID ' + d.id + " · " + fmtDate(d.created_at) + "</div></div>" +
        '<div class="actions"><button class="btn btn-sm btn-primary" data-action="review" data-id="' +
        d.id + '">Создать рецензию</button></div>' +
        "</div>"
    )
    .join("");
}

async function createDocument(form) {
  const title = document.getElementById("doc-title").value.trim();
  const text = document.getElementById("doc-text").value;
  try {
    await api("/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, text }),
    });
    form.reset();
    document.getElementById("doc-counter").textContent = "0 / 30000";
    await loadDocuments();
  } catch (e) {
    showError("doc-list", e.message);
  }
}

async function createReviewForDocument(id) {
  showError("doc-list", "Запускаю рецензирование документа " + id + "…");
  try {
    const data = await api("/documents/" + id + "/review", { method: "POST" });
    showError("doc-list", "Готово: рецензия #" + data.review_id + " — откройте раздел «Рецензии».");
    await loadReviews();
  } catch (e) {
    showError("doc-list", e.message);
  }
}

document.getElementById("doc-form").addEventListener("submit", (e) => {
  e.preventDefault();
  createDocument(e.target);
});

document.getElementById("doc-list").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action=review]");
  if (btn) createReviewForDocument(parseInt(btn.dataset.id, 10));
});

document.getElementById("doc-text").addEventListener("input", (e) => {
  document.getElementById("doc-counter").textContent = e.target.value.length + " / 30000";
});
// ---------------------------------------------------------------------------
// Раздел «Рецензии»
// ---------------------------------------------------------------------------
async function loadReviews() {
  const el = document.getElementById("review-list");
  try {
    const data = await api("/reviews");
    renderReviews(el, data.reviews || []);
  } catch (e) {
    el.innerHTML = '<p class="empty">' + esc(e.message) + "</p>";
  }
}

function renderReviews(el, reviews) {
  if (!reviews.length) {
    el.innerHTML = '<p class="empty">Пока нет рецензий. Создайте её из раздела «Документы».</p>';
    return;
  }
  el.innerHTML = reviews
    .map((r) => {
      const warning = r.needs_review ? ' <span class="badge badge-warning">требует проверки</span>' : "";
      const summary = r.summary ? esc(r.summary) : "Без сводки";
      const reason = r.error ? " · причина: " + esc(r.error) : "";
      return (
        '<div class="row">' +
        '<div><div class="title">#' + r.id +
        ' <span class="tag-confidence">' + esc(r.confidence || "—") + "</span>" + warning + "</div>" +
        '<div class="meta">' + summary + "</div>" +
        '<div class="meta">Документ #' + r.document_id + " · " + fmtDate(r.created_at) + reason + "</div></div>" +
        '<div class="actions"><button class="btn btn-sm btn-primary" data-action="open" data-id="' +
        r.id + '">Открыть</button></div>' +
        "</div>"
      );
    })
    .join("");
}

document.getElementById("review-list").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action=open]");
  if (btn) {
    const id = parseInt(btn.dataset.id, 10);
    document.querySelector('.tab[data-tab="view"]').click();
    openReview(id);
  }
});
// ---------------------------------------------------------------------------
// Раздел «Просмотр рецензии»
// ---------------------------------------------------------------------------
function copyBlock(button) {
  const block = button.closest(".block");
  const textEl = block.querySelector("ul, .copy-strip, .plain-line, .raw-block");
  const text = textEl ? textEl.innerText : "";
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      const old = button.textContent;
      button.textContent = "Скопировано ✓";
      setTimeout(() => (button.textContent = old), 1200);
    });
  }
}

function exportJson(review) {
  const payload = {
    id: review.id,
    document_id: review.document_id,
    created_at: review.created_at,
    needs_review: review.needs_review,
    confidence: review.confidence,
    error: review.error,
    summary: review.summary,
    risks: review.risks,
    missing_requirements: review.missing_requirements,
    questions_to_client: review.questions_to_client,
    acceptance_criteria: review.acceptance_criteria,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "review_" + review.id + ".json";
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderReviewDetail(review) {
  const el = document.getElementById("review-detail");
  const warning = review.needs_review
    ? '<div class="notice">⚠ Требует проверки' + (review.error ? " — " + esc(review.error) : "") + "</div>"
    : "";

  const risks = (review.risks || [])
    .map(
      (r) =>
        '<div class="risk-line"><span class="badge badge-severity severity-' + esc(r.severity) + '">' +
        esc(r.severity) + "</span><span>" + esc(r.description) + "</span></div>"
    )
    .join("");

  const ulList = (items) =>
    items && items.length
      ? "<ul>" + items.map((i) => "<li>" + esc(i) + "</li>").join("") + "</ul>"
      : '<p class="hint">—</p>';

  let rawHtml = "";
  try {
    if (review.review_json) {
      rawHtml +=
        '<h3>Сырой JSON шага B (review_json)</h3><pre>' +
        esc(JSON.stringify(JSON.parse(review.review_json), null, 2)) + "</pre>";
    }
    if (review.analysis_json) {
      rawHtml +=
        '<h3>Сырой JSON шага A (analysis_json)</h3><pre>' +
        esc(JSON.stringify(JSON.parse(review.analysis_json), null, 2)) + "</pre>";
    }
  } catch (_e) {
    rawHtml = '<h3>Сырые JSON</h3><p class="hint">—</p>';
  }

  el.innerHTML =
    warning +
    '<div class="card">' +
    '<div class="review-head">' +
    "<div><strong>Рецензия #" + review.id + "</strong> · Документ #" + review.document_id +
    '<div class="meta">' + fmtDate(review.created_at) + "</div>" +
    '<div class="meta">confidence: ' + esc(review.confidence || "—") + " · статус: " + esc(review.status || "—") +
    (review.error ? " · причина: " + esc(review.error) : "") + "</div></div>" +
    '<div class="actions"><button class="btn btn-sm" id="btn-export">Скачать JSON</button></div>' +
    "</div></div>" +
    '<div class="card"><div class="block"><h3>Сводка (summary)</h3>' +
    '<p class="plain-line">' + esc(review.summary || "—") + "</p></div></div>" +
    '<div class="card"><div class="block"><h3>Риски <button class="btn btn-sm" data-copy>Копировать</button></h3>' +
    (risks || '<p class="hint">—</p>') + "</div></div>" +
    '<div class="card"><div class="block"><h3>Чего не хватает <button class="btn btn-sm" data-copy>Копировать</button></h3>' +
    ulList(review.missing_requirements) + "</div></div>" +
    '<div class="card"><div class="block"><h3>Вопросы заказчику <button class="btn btn-sm" data-copy>Копировать</button></h3>' +
    ulList(review.questions_to_client) + "</div></div>" +
    '<div class="card"><div class="block"><h3>Критерии приёмки <button class="btn btn-sm" data-copy>Копировать</button></h3>' +
    ulList(review.acceptance_criteria) + "</div></div>" +
    '<div class="card raw-block"><div class="block">' + rawHtml + "</div></div>" +
    '<p class="disclaimer">Отчёт сгенерирован ИИ-цепочкой (A: разбор документа → B: формирование рецензии → C: решение о ручной проверке).</p>';

  el.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copyBlock(b)));
  document.getElementById("btn-export").addEventListener("click", () => exportJson(review));
}
async function openReview(id) {
  const el = document.getElementById("review-detail");
  el.innerHTML = '<p class="empty">Загрузка рецензии #' + id + "…</p>";
  try {
    const review = await api("/reviews/" + id);
    renderReviewDetail(review);
  } catch (e) {
    el.innerHTML = '<div class="notice notice-error">' + esc(e.message) + "</div>";
  }
}

// ---------------------------------------------------------------------------
// Инициализация
// ---------------------------------------------------------------------------
refreshHealth();
loadDocuments();
loadReviews();