/**
 * Context Warehouse - Strict Monochrome Frontend Controller
 * Zero icons, zero gradients, zero slop - Pure metrics & data
 */

document.addEventListener("DOMContentLoaded", () => {
  // Core UI Elements
  const queryInput = document.getElementById("query-input");
  const btnSubmit = document.getElementById("btn-submit");
  const systemStatus = document.getElementById("system-status");
  const chips = document.querySelectorAll(".chip");

  // Metric Elements
  const completenessVal = document.getElementById("metric-completeness-val");
  const completenessBadge = document.getElementById("metric-completeness-badge");
  const completenessDesc = document.getElementById("metric-completeness-desc");
  const latencyVal = document.getElementById("metric-latency-val");
  const latencyDesc = document.getElementById("metric-latency-desc");
  const intentVal = document.getElementById("metric-intent-val");
  const entitiesVal = document.getElementById("metric-entities-val");
  const sourcesVal = document.getElementById("metric-sources-val");
  const sourcesDesc = document.getElementById("metric-sources-desc");

  // Answer & Alert Elements
  const aiAnswerBody = document.getElementById("ai-answer-body");
  const answerModelTag = document.getElementById("answer-model-tag");
  const btnCopyAnswer = document.getElementById("btn-copy-answer");
  const alertBanner = document.getElementById("alert-banner");
  const alertContent = document.getElementById("alert-content");

  // Sources Elements
  const sourceTabBtns = document.querySelectorAll(".tab-btn[data-source-tab]");
  const sourcePanes = document.querySelectorAll(".source-pane");
  const dbRecordsCount = document.getElementById("db-records-count");
  const policyCount = document.getElementById("policy-count");
  const dbRecordsContainer = document.getElementById("db-records-container");
  const policiesContainer = document.getElementById("policies-container");

  // Debug Elements
  const debugTimings = document.getElementById("debug-timings");
  const debugSchemaJson = document.getElementById("debug-schema-json");

  // Catalog Modal Elements
  const btnOpenCatalog = document.getElementById("btn-open-catalog");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const catalogModal = document.getElementById("catalog-modal");
  const modalTabs = document.querySelectorAll(".modal-tab");
  const modalPanes = document.querySelectorAll(".modal-pane");
  const modalTablesContent = document.getElementById("modal-tables-content");
  const modalPoliciesContent = document.getElementById("modal-policies-content");
  const modalGraphContent = document.getElementById("modal-graph-content");

  let catalogCache = null;

  // 1. Initial Health Check
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      if (data.database_connected) {
        systemStatus.className = "status-badge status-online";
        systemStatus.textContent = `ONLINE [${data.policy_files_count} Policies]`;
      } else {
        systemStatus.className = "status-badge status-error";
        systemStatus.textContent = "DB ERROR";
      }
    } catch {
      systemStatus.className = "status-badge status-error";
      systemStatus.textContent = "OFFLINE";
    }
  }
  checkHealth();

  // 2. Submit Action & Execution
  async function executeQuery() {
    const query = queryInput.value.trim();
    if (!query) {
      queryInput.focus();
      return;
    }

    // Set Loading State
    btnSubmit.disabled = true;
    btnSubmit.textContent = "Đang xử lý...";
    aiAnswerBody.innerHTML = `
      <div class="empty-state">
        <p>Đang thực thi Context Planning, Retrieval & Synthesis...</p>
      </div>
    `;
    alertBanner.classList.add("hidden");

    try {
      const startTime = performance.now();
      const res = await fetch("/api/pipeline/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Lỗi thực thi pipeline.");
      }

      const result = await res.json();
      const clientDurationSec = ((performance.now() - startTime) / 1000).toFixed(2);

      renderResult(result, clientDurationSec);
    } catch (err) {
      aiAnswerBody.innerHTML = `
        <div style="padding: 10px; border: 1px solid #ffffff; background: #171717;">
          <strong>[LỖI]</strong> ${err.message}
        </div>
      `;
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = "Gửi";
    }
  }

  // 3. Render Pipeline Results cleanly
  function renderResult(data, fallbackLatencySec) {
    const valReport = data.validation_report || {};
    const score = valReport.score !== undefined ? valReport.score : 100;
    const durationSec = data.total_duration_ms ? (data.total_duration_ms / 1000).toFixed(2) : fallbackLatencySec;

    // A. Metric 1: Quality / Completeness
    completenessVal.textContent = `${score}%`;
    if (score >= 90) {
      completenessBadge.className = "badge badge-success";
      completenessBadge.textContent = "ĐẦY ĐỦ";
      completenessDesc.textContent = "100% ngữ cảnh cần thiết";
    } else if (score >= 70) {
      completenessBadge.className = "badge badge-warning";
      completenessBadge.textContent = "TƯƠNG ĐỐI";
      completenessDesc.textContent = "Đủ để trả lời (có lưu ý)";
    } else {
      completenessBadge.className = "badge badge-danger";
      completenessBadge.textContent = "THIẾU";
      completenessDesc.textContent = "Cần bổ sung context";
    }

    // B. Metric 2: Latency
    latencyVal.textContent = `${durationSec}s`;
    latencyDesc.textContent = `Model: ${data.model_used || 'Gemini'}`;

    // C. Metric 3: Intent & Entity
    intentVal.textContent = data.intent || "Tra cứu chung";
    const entityList = [];
    if (data.entities) {
      if (typeof data.entities === "object") {
        for (const [k, v] of Object.entries(data.entities)) {
          if (v) entityList.push(`${k}: ${Array.isArray(v) ? v.join(", ") : v}`);
        }
      }
    }
    entitiesVal.textContent = entityList.length > 0 ? entityList.join(" | ") : "Không có entity";

    // D. Parse Retrieved Context (DB Tables vs Policy Documents)
    const rawRetrieved = data.retrieved_context;
    let dbItems = [];
    let policyItems = [];

    if (Array.isArray(rawRetrieved)) {
      rawRetrieved.forEach(item => {
        const ctx = String(item.context || "").toLowerCase();
        const sourceDoc = String(item.source_doc || "").toLowerCase();
        const isPolicy = ctx.includes("policy") || sourceDoc.endsWith(".md") || typeof item.data === "string";
        if (isPolicy) {
          policyItems.push(item);
        } else {
          dbItems.push(item);
        }
      });
    } else if (rawRetrieved && typeof rawRetrieved === "object") {
      for (const [k, v] of Object.entries(rawRetrieved)) {
        if (k === "markdown_policies" && typeof v === "object") {
          for (const [pk, pv] of Object.entries(v)) {
            policyItems.push({ context: pk, source_doc: `${pk}.md`, data: pv, section: "all" });
          }
        } else if (k.toLowerCase().includes("policy")) {
          policyItems.push({ context: k, source_doc: `${k}.md`, data: v, section: "all" });
        } else {
          dbItems.push({ context: k, source_doc: `table: ${k}`, data: v, section: ["all"] });
        }
      }
    }

    // Metric 4: Context Sources Count
    sourcesVal.textContent = `${dbItems.length} DB, ${policyItems.length} Policy`;
    const sourceNames = [...dbItems.map(i => i.context), ...policyItems.map(i => i.context)];
    sourcesDesc.textContent = sourceNames.join(", ") || "None";

    // E. AI Answer
    answerModelTag.textContent = data.model_used || "Gemini";
    if (data.answer) {
      if (typeof marked !== "undefined" && marked.parse) {
        aiAnswerBody.innerHTML = marked.parse(data.answer);
      } else {
        aiAnswerBody.innerHTML = `<p>${data.answer}</p>`;
      }
    } else {
      aiAnswerBody.innerHTML = `<p class="text-muted">Không có câu trả lời.</p>`;
    }

    // F. Warnings / Alerts
    const warnings = valReport.missing_fields || [];
    const valWarnings = valReport.warnings || [];
    const allAlerts = [...warnings, ...valWarnings];
    if (allAlerts.length > 0) {
      alertBanner.classList.remove("hidden");
      alertContent.textContent = allAlerts.join("; ");
    } else {
      alertBanner.classList.add("hidden");
    }

    // G. Context Sources Tabs: Database Records
    dbRecordsCount.textContent = dbItems.length;
    if (dbItems.length === 0) {
      dbRecordsContainer.innerHTML = `<div class="empty-hint">Không có bản ghi database.</div>`;
    } else {
      let dbHtml = "";
      dbItems.forEach(item => {
        const table = item.context || "Table";
        let records = [];
        if (Array.isArray(item.data)) {
          records = item.data;
        } else if (item.data && typeof item.data === "object" && Object.keys(item.data).length > 0) {
          records = [item.data];
        }

        if (records.length > 0) {
          records.forEach((row, idx) => {
            let rowKvs = "";
            for (const [k, v] of Object.entries(row)) {
              rowKvs += `
                <div class="record-k">${k}:</div>
                <div class="record-v">${v !== null && v !== undefined ? v : '-'}</div>
              `;
            }
            dbHtml += `
              <div class="data-record-card">
                <div class="record-card-head">
                  <span class="record-table-name">[Table] ${table}</span>
                  <span class="record-pill">#${idx + 1}</span>
                </div>
                <div class="record-kv">${rowKvs}</div>
              </div>
            `;
          });
        } else {
          dbHtml += `
            <div class="data-record-card">
              <div class="record-card-head">
                <span class="record-table-name">[Table] ${table}</span>
              </div>
              <div class="record-v text-muted">Không tìm thấy bản ghi.</div>
            </div>
          `;
        }
      });
      dbRecordsContainer.innerHTML = dbHtml;
    }

    // H. Context Sources Tabs: Policies
    policyCount.textContent = policyItems.length;
    if (policyItems.length === 0) {
      policiesContainer.innerHTML = `<div class="empty-hint">Không có chính sách nào.</div>`;
    } else {
      let pPolHtml = "";
      policyItems.forEach(item => {
        const pName = item.context || "Policy";
        const pData = item.data;
        const textPreview = typeof pData === "string" ? pData : JSON.stringify(pData, null, 2);
        const sectionInfo = item.section ? (Array.isArray(item.section) ? item.section.join(", ") : item.section) : "all";

        pPolHtml += `
          <div class="policy-extract-card">
            <div class="policy-card-title">
              <span>[Policy] ${pName}.md</span>
              <span class="record-pill">${sectionInfo}</span>
            </div>
            <div class="policy-snippet">${escapeHtml((textPreview || "").trim())}</div>
          </div>
        `;
      });
      policiesContainer.innerHTML = pPolHtml;
    }

    // I. Debug Section
    if (data.checkpoints && Array.isArray(data.checkpoints)) {
      debugTimings.innerHTML = data.checkpoints.map(cp => `
        <div class="timing-row">
          <span>Step ${cp.step}: ${cp.name}</span>
          <span class="font-mono">${cp.duration_ms.toFixed(1)}ms</span>
        </div>
      `).join("");
    }
    if (data.context_package) {
      debugSchemaJson.textContent = JSON.stringify(data.context_package, null, 2);
    }
  }

  // 4. Quick Chips Click Event
  chips.forEach(chip => {
    chip.addEventListener("click", () => {
      queryInput.value = chip.getAttribute("data-query");
      executeQuery();
    });
  });

  // 5. Input keydown handling
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      executeQuery();
    }
  });

  btnSubmit.addEventListener("click", executeQuery);

  // 6. Copy Answer Button
  btnCopyAnswer.addEventListener("click", () => {
    const rawText = aiAnswerBody.innerText;
    if (!rawText) return;
    navigator.clipboard.writeText(rawText).then(() => {
      btnCopyAnswer.textContent = "Đã chép";
      setTimeout(() => {
        btnCopyAnswer.textContent = "Sao chép";
      }, 1500);
    });
  });

  // 7. Source Tabs Switcher
  sourceTabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      sourceTabBtns.forEach(b => b.classList.remove("active"));
      sourcePanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetId = btn.getAttribute("data-source-tab");
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // 8. Catalog Modal
  btnOpenCatalog.addEventListener("click", openCatalogModal);
  btnCloseModal.addEventListener("click", () => catalogModal.classList.add("hidden"));
  catalogModal.addEventListener("click", (e) => {
    if (e.target === catalogModal) catalogModal.classList.add("hidden");
  });

  modalTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      modalTabs.forEach(t => t.classList.remove("active"));
      modalPanes.forEach(p => p.classList.remove("active"));

      tab.classList.add("active");
      const targetPane = document.getElementById(tab.getAttribute("data-mtab"));
      if (targetPane) targetPane.classList.add("active");
    });
  });

  async function openCatalogModal() {
    catalogModal.classList.remove("hidden");
    if (catalogCache) return;

    try {
      const res = await fetch("/api/catalog");
      const data = await res.json();
      catalogCache = data;

      // Render Tables
      if (data.tables && data.tables.length > 0) {
        modalTablesContent.innerHTML = data.tables.map(t => `
          <div class="catalog-item-card">
            <div class="catalog-item-name">[Table] ${t.name}</div>
            <div class="catalog-item-desc">${t.description || 'No description'}</div>
            <div class="catalog-item-meta">Columns: ${t.columns.join(", ")}</div>
          </div>
        `).join("");
      }

      // Render Policies
      if (data.policies && data.policies.length > 0) {
        modalPoliciesContent.innerHTML = data.policies.map(p => `
          <div class="catalog-item-card">
            <div class="catalog-item-name">[Policy] ${p.filename}</div>
            <div class="catalog-item-desc">${p.lines_count} lines • ${p.char_count} chars</div>
            <div class="catalog-item-meta" style="max-height: 80px; overflow: hidden;">${escapeHtml(p.raw_content.slice(0, 150))}...</div>
          </div>
        `).join("");
      }

      // Render Graph
      if (data.relationships && data.relationships.length > 0) {
        modalGraphContent.innerHTML = data.relationships.map(r => `
          <div class="graph-item-row">
            <span class="graph-tag">${r.source}</span>
            <span>-></span>
            <span class="graph-tag">${r.target}</span>
            <span class="text-secondary" style="margin-left: auto;">(${r.relationship_type})</span>
          </div>
        `).join("");
      }
    } catch {
      modalTablesContent.innerHTML = `<div class="empty-hint">Lỗi nạp catalog.</div>`;
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
});
