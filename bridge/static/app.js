// Local AI Workspace • Frontend Application Logic
let appState = {
  models: [],
  activeModel: null,
  status: "STOPPED",
  chatHistory: [],
  abortController: null,
  activeTab: "chat"
};

// DOM Elements
const headerStatusDot = document.getElementById("headerStatusDot");
const headerModelSelect = document.getElementById("headerModelSelect");
const btnSwitchModel = document.getElementById("btnSwitchModel");
const ramText = document.getElementById("ramText");
const cpuText = document.getElementById("cpuText");
const btnUnload = document.getElementById("btnUnload");

const activeModelLabel = document.getElementById("activeModelLabel");
const statusMessage = document.getElementById("statusMessage");
const messagesContainer = document.getElementById("messagesContainer");
const chatInput = document.getElementById("chatInput");
const btnSend = document.getElementById("btnSend");
const btnStop = document.getElementById("btnStop");
const btnClearChat = document.getElementById("btnClearChat");

const systemPrompt = document.getElementById("systemPrompt");
const tempSlider = document.getElementById("temperature");
const tempVal = document.getElementById("tempVal");
const maxTokensSlider = document.getElementById("maxTokens");
const maxTokensVal = document.getElementById("maxTokensVal");
const topPSlider = document.getElementById("topP");
const topPVal = document.getElementById("topPVal");
const repeatPenaltySlider = document.getElementById("repeatPenalty");
const repeatPenaltyVal = document.getElementById("repeatPenaltyVal");

const modelsGrid = document.getElementById("modelsGrid");
const btnRefreshModels = document.getElementById("btnRefreshModels");
const logsConsole = document.getElementById("logsConsole");
const btnRefreshLogs = document.getElementById("btnRefreshLogs");
const autoScrollLogs = document.getElementById("autoScrollLogs");
const btnTestApi = document.getElementById("btnTestApi");
const testApiResult = document.getElementById("testApiResult");

// Presets
const presets = {
  coder: "You are an elite, highly capable coding assistant. Write clean, robust, well-tested code with concise explanations.",
  general: "You are a helpful, knowledgeable, and polite AI assistant.",
  analyst: "You are an expert data, financial, and option chain logic analyst. Provide rigorous, structured, and factual answers."
};

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupSliders();
  setupPresets();
  setupChatHandlers();
  setupModelActions();

  // Initial fetch and poll loop
  fetchStatus();
  setInterval(fetchStatus, 3000);
});

// Tab Management
function setupTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const tabName = tab.dataset.tab;
      appState.activeTab = tabName;

      document.querySelectorAll(".tab-pane").forEach(pane => {
        pane.classList.remove("active");
      });
      document.getElementById(`tab-${tabName}`).classList.add("active");

      if (tabName === "logs") {
        fetchLogs();
      }
    });
  });
}

// Sliders setup
function setupSliders() {
  tempSlider.addEventListener("input", (e) => tempVal.textContent = e.target.value);
  maxTokensSlider.addEventListener("input", (e) => maxTokensVal.textContent = e.target.value);
  topPSlider.addEventListener("input", (e) => topPVal.textContent = e.target.value);
  repeatPenaltySlider.addEventListener("input", (e) => repeatPenaltyVal.textContent = e.target.value);
}

// System Prompt presets
function setupPresets() {
  document.querySelectorAll(".preset-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const p = btn.dataset.preset;
      if (presets[p]) {
        systemPrompt.value = presets[p];
      }
    });
  });
}

// Fetch Status & Health
async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error("Status check failed");
    const data = await res.json();

    appState.status = data.status;
    appState.activeModel = data.active_model_file;
    appState.models = data.models || [];

    updateStatusUI(data);

    if (appState.activeTab === "logs") {
      fetchLogs();
    }
  } catch (err) {
    headerStatusDot.className = "status-dot";
    statusMessage.textContent = "Server unreachable";
  }
}

// Update UI with status info
function updateStatusUI(data) {
  // Status dot
  headerStatusDot.className = "status-dot";
  if (data.status === "READY") {
    headerStatusDot.classList.add("ready");
    statusMessage.textContent = `Ready (Uptime: ${data.uptime_seconds}s)`;
  } else if (data.status === "STARTING") {
    headerStatusDot.classList.add("loading");
    statusMessage.textContent = "Loading model into memory...";
  } else {
    statusMessage.textContent = data.error_message ? `Error: ${data.error_message}` : "Stopped";
  }

  // Active Model Label
  activeModelLabel.textContent = data.active_model_file
    ? `Active: ${data.active_model_file}`
    : "No model loaded";

  // System Stats
  if (data.system && data.system.memory) {
    const mem = data.system.memory;
    ramText.textContent = `RAM: ${(mem.used_mb / 1024).toFixed(1)} / ${(mem.total_mb / 1024).toFixed(1)} GB (${mem.used_percent}%)`;
    cpuText.textContent = `CPU: ${data.system.cpu_cores} Cores (Load: ${data.system.load_avg[0]})`;
  }

  // Header Dropdown options
  const currentVal = headerModelSelect.value;
  headerModelSelect.innerHTML = "";
  if (data.models.length === 0) {
    headerModelSelect.innerHTML = '<option value="">No models detected</option>';
  } else {
    data.models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.filename;
      opt.textContent = `${m.is_active ? "● " : ""}${m.display_name} (${m.size_human})`;
      if (m.filename === data.active_model_file) {
        opt.selected = true;
      }
      headerModelSelect.appendChild(opt);
    });
  }

  // Render Models Grid if on Models Tab
  renderModelsGrid(data.models);
}

// Render Models Grid
function renderModelsGrid(models) {
  if (!modelsGrid) return;
  modelsGrid.innerHTML = "";

  models.forEach(m => {
    const card = document.createElement("div");
    card.className = `model-card ${m.is_active ? "active" : ""}`;

    card.innerHTML = `
      <div class="model-card-header">
        <div>
          <h3 class="model-title">${m.display_name}</h3>
          <span class="subtitle">${m.filename}</span>
        </div>
        <span class="model-pill ${m.is_active ? "active" : "inactive"}">
          ${m.is_active ? "ACTIVE" : "AVAILABLE"}
        </span>
      </div>

      <div class="model-meta-list">
        <div><strong>File Size:</strong> ${m.size_human}</div>
        <div><strong>Quantization:</strong> ${m.quantization}</div>
        <div><strong>Path:</strong> <code>${m.path}</code></div>
      </div>

      <div style="margin-top: auto; padding-top: 10px;">
        ${m.is_active
          ? `<button class="btn btn-sm btn-outline" style="width: 100%; border-color: var(--accent-emerald);" disabled>✓ Currently Loaded</button>`
          : `<button class="btn btn-sm btn-primary" style="width: 100%;" onclick="switchModel('${m.filename}')">Load & Switch</button>`
        }
      </div>
    `;
    modelsGrid.appendChild(card);
  });
}

// Switch Model
async function switchModel(modelFilename) {
  if (!modelFilename) return;
  headerStatusDot.className = "status-dot loading";
  statusMessage.textContent = `Starting ${modelFilename}...`;

  try {
    const res = await fetch("/api/models/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: modelFilename })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(`Error loading model: ${data.detail || "Unknown error"}`);
    } else {
      fetchStatus();
    }
  } catch (err) {
    alert(`Failed to request model switch: ${err.message}`);
  }
}

// Unload Model
async function unloadModel() {
  if (!confirm("Are you sure you want to unload the model to free RAM?")) return;
  try {
    await fetch("/api/models/unload", { method: "POST" });
    fetchStatus();
  } catch (err) {
    alert(`Error unloading model: ${err.message}`);
  }
}

// Setup Model Actions
function setupModelActions() {
  btnSwitchModel.addEventListener("click", () => {
    const selected = headerModelSelect.value;
    if (selected) switchModel(selected);
  });

  btnUnload.addEventListener("click", unloadModel);
  btnRefreshModels.addEventListener("click", fetchStatus);
  btnRefreshLogs.addEventListener("click", fetchLogs);

  // Test API Button
  if (btnTestApi) {
    btnTestApi.addEventListener("click", runApiTest);
  }
}

// Chat Handlers
function setupChatHandlers() {
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  btnSend.addEventListener("click", sendMessage);
  btnStop.addEventListener("click", stopGeneration);
  btnClearChat.addEventListener("click", clearChat);
}

function clearChat() {
  appState.chatHistory = [];
  messagesContainer.innerHTML = `
    <div class="message assistant welcome-card">
      <div class="message-sender">🤖 AI Assistant</div>
      <div class="message-body">
        <p>Chat cleared. Ready for your questions!</p>
      </div>
    </div>
  `;
}

function stopGeneration() {
  if (appState.abortController) {
    appState.abortController.abort();
    appState.abortController = null;
  }
  btnStop.classList.add("hidden");
  btnSend.classList.remove("hidden");
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  if (appState.status !== "READY") {
    alert("Model server is not ready yet. Please wait for model loading or select a model.");
    return;
  }

  // Append user message to UI
  appendMessage("user", text);
  chatInput.value = "";
  chatInput.style.height = "auto";

  appState.chatHistory.push({ role: "user", content: text });

  // Prepare assistant message in UI
  const assistantMsgElem = appendMessage("assistant", "");
  const bodyElem = assistantMsgElem.querySelector(".message-body");
  bodyElem.innerHTML = '<span class="status-dot loading" style="display:inline-block; margin-right:6px;"></span>Thinking...';

  // Toggle buttons
  btnSend.classList.add("hidden");
  btnStop.classList.remove("hidden");

  appState.abortController = new AbortController();

  const payload = {
    model: appState.activeModel || "local-model",
    messages: [
      { role: "system", content: systemPrompt.value.trim() },
      ...appState.chatHistory
    ],
    temperature: parseFloat(tempSlider.value),
    max_tokens: parseInt(maxTokensSlider.value),
    top_p: parseFloat(topPSlider.value),
    stream: true
  };

  let fullResponse = "";
  let isFirstToken = true;

  try {
    const res = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: appState.abortController.signal
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      bodyElem.textContent = `Error: ${err.detail || res.statusText}`;
      stopGeneration();
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep trailing incomplete line

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(":")) continue;

        if (trimmed.startsWith("data: ")) {
          const jsonStr = trimmed.slice(6).trim();
          if (jsonStr === "[DONE]") break;

          try {
            const parsed = JSON.parse(jsonStr);
            const delta = parsed.choices?.[0]?.delta?.content || "";
            if (delta) {
              if (isFirstToken) {
                bodyElem.innerHTML = "";
                isFirstToken = false;
              }
              fullResponse += delta;
              bodyElem.textContent = fullResponse; // safe text rendering
              messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
          } catch (e) {
            // Ignore parse errors on partial chunks
          }
        }
      }
    }

    // Format final markdown/code if any
    bodyElem.innerHTML = renderSimpleMarkdown(fullResponse);
    appState.chatHistory.push({ role: "assistant", content: fullResponse });

  } catch (err) {
    if (err.name !== "AbortError") {
      bodyElem.textContent = `Error: ${err.message}`;
    }
  } finally {
    stopGeneration();
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

function appendMessage(role, content) {
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${role}`;

  const senderDiv = document.createElement("div");
  senderDiv.className = "message-sender";
  senderDiv.textContent = role === "user" ? "👤 You" : "🤖 Assistant";

  const bodyDiv = document.createElement("div");
  bodyDiv.className = "message-body";
  bodyDiv.innerHTML = role === "user" ? escapeHtml(content) : renderSimpleMarkdown(content);

  msgDiv.appendChild(senderDiv);
  msgDiv.appendChild(bodyDiv);
  messagesContainer.appendChild(msgDiv);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  return msgDiv;
}

// Simple Markdown / code formatter
function renderSimpleMarkdown(text) {
  if (!text) return "";
  let out = escapeHtml(text);
  // Code blocks
  out = out.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code class="lang-${lang}">${code}</code></pre>`;
  });
  // Inline code
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Line breaks
  out = out.replace(/\n/g, '<br>');
  return out;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Fetch Server Logs
async function fetchLogs() {
  try {
    const res = await fetch("/api/logs?lines=80");
    if (!res.ok) return;
    const data = await res.json();
    if (data.logs && logsConsole) {
      logsConsole.textContent = data.logs.join("\n") || "No logs available yet.";
      if (autoScrollLogs.checked) {
        logsConsole.scrollTop = logsConsole.scrollHeight;
      }
    }
  } catch (err) {
    console.error("Error fetching logs:", err);
  }
}

// Run Quick API Test
async function runApiTest() {
  testApiResult.classList.remove("hidden");
  testApiResult.textContent = "Sending test request to /v1/chat/completions (model: Qwen2.5-3B-Instruct)...";

  try {
    const t0 = performance.now();
    const res = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "Qwen2.5-3B-Instruct-Q4_K_M",
        messages: [{ role: "user", content: "Reply with exactly: 'Bridge connection verified!'" }],
        max_tokens: 32,
        temperature: 0.1,
        stream: false
      })
    });
    const t1 = performance.now();
    const data = await res.json();
    testApiResult.textContent = `Status: ${res.status} OK (${Math.round(t1 - t0)}ms)\nResponse: ` + JSON.stringify(data, null, 2);
  } catch (err) {
    testApiResult.textContent = `API Test Failed: ${err.message}`;
  }
}

// Copy Code Snippet
window.copySnippet = function(elemId) {
  const el = document.getElementById(elemId);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {
    alert("Snippet copied to clipboard!");
  }).catch(() => {
    prompt("Copy snippet manually:", el.innerText);
  });
};
