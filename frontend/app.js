const state = {
  token: window.localStorage.getItem("eai_access_token"),
  user: null,
  documents: [],
  polling: new Set(),
  authMode: "login",
  chatMessages: [],
  chatSessions: [],
  activeChatSessionId: null,
  chatPending: false,
  highlightEvidence: true,
};

const $ = (selector) => document.querySelector(selector);
const authView = $("#auth-view");
const appView = $("#app-view");
const authForm = $("#auth-form");
const authEmail = $("#auth-email");
const authPassword = $("#auth-password");
const authTitle = $("#auth-title");
const authSubtitle = $("#auth-subtitle");
const authSubmit = $("#auth-submit");
const authError = $("#auth-error");
const uploadForm = $("#upload-form");
const documentFile = $("#document-file");
const dropZone = $("#drop-zone");
const fileName = $("#file-name");
const uploadSubmit = $("#upload-submit");
const uploadMessage = $("#upload-message");
const documentsList = $("#documents-list");
const chatForm = $("#chat-form");
const chatInput = $("#chat-input");
const chatMode = $("#chat-mode");
const chatTopK = $("#chat-top-k");
const chatSubmit = $("#chat-submit");
const chatMessage = $("#chat-message");
const chatMessages = $("#chat-messages");
const chatSessionsList = $("#chat-sessions-list");
const newChatButton = $("#new-chat-button");
const evidenceHighlightToggle = $("#evidence-highlight-toggle");
const toastRegion = $("#toast-region");

const STATUS_LABELS = {
  pending: "等待处理",
  processing: "处理中",
  ready: "已就绪",
  failed: "处理失败",
};

async function api(path, options = {}) {
  const { timeoutMs = 15000, ...requestOptions } = options;
  const headers = new Headers(requestOptions.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (requestOptions.body && !(requestOptions.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(path, { ...requestOptions, headers, signal: controller.signal });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }
    }

    if (!response.ok) {
      if (response.status === 401) {
        clearSession();
        showAuth();
      }
      const detail = data && typeof data.detail === "string" ? data.detail : `请求失败（${response.status}）`;
      throw new Error(detail);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(`请求超过 ${Math.round(timeoutMs / 1000)} 秒未完成；首次请求可能正在加载模型，请稍后重试。`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function clearSession() {
  state.token = null;
  state.user = null;
  window.localStorage.removeItem("eai_access_token");
}

function showAuth() {
  authView.classList.remove("hidden");
  appView.classList.add("hidden");
  authEmail.focus();
}

function showApp() {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  $("#user-email").textContent = state.user?.email || "";
}

function setMessage(element, text = "", type = "") {
  element.textContent = text;
  element.className = `form-message ${type ? `${type}-message` : ""}`.trim();
}

function setButtonBusy(button, busy, busyText) {
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.disabled = true;
    button.textContent = busyText;
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalText || button.textContent;
  }
}

function switchAuthMode(mode) {
  state.authMode = mode;
  document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
    const active = tab.dataset.authTab === mode;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  const registering = mode === "register";
  authTitle.textContent = registering ? "创建工作台账号" : "登录工作台";
  authSubtitle.textContent = registering ? "注册后即可开始构建你的知识库。" : "使用你的企业账号继续。";
  authSubmit.textContent = registering ? "创建账号" : "登录";
  authPassword.autocomplete = registering ? "new-password" : "current-password";
  setMessage(authError);
}

async function login(email, password) {
  const result = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  state.token = result.access_token;
  window.localStorage.setItem("eai_access_token", state.token);
  state.user = await api("/auth/me");
  showApp();
  await Promise.all([loadDocuments(), loadChatSessions()]);
}

async function handleAuth(event) {
  event.preventDefault();
  const email = authEmail.value.trim();
  const password = authPassword.value;
  setMessage(authError);
  setButtonBusy(authSubmit, true, state.authMode === "register" ? "创建中…" : "登录中…");

  try {
    if (state.authMode === "register") {
      await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      await login(email, password);
      showToast("账号创建成功，欢迎进入工作台");
    } else {
      await login(email, password);
    }
    authForm.reset();
  } catch (error) {
    setMessage(authError, error.message, "error");
  } finally {
    setButtonBusy(authSubmit, false);
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[character]);
}

function renderDocuments() {
  if (!state.documents.length) {
    documentsList.innerHTML = '<div class="empty-state">还没有文档，先上传一份资料吧。</div>';
    return;
  }

  documentsList.innerHTML = state.documents.map((doc) => {
    const status = STATUS_LABELS[doc.status] || doc.status;
    const error = doc.ingest_error
      ? `<p class="document-error">${escapeHtml(doc.ingest_error)}</p>`
      : "";
    return `
      <article class="document-card">
        <div class="document-main">
          <strong class="document-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</strong>
          <div class="document-meta">
            <span>${formatBytes(doc.size)}</span>
            <span>${formatDate(doc.uploaded_at)}</span>
          </div>
        </div>
        <span class="document-status status-${escapeHtml(doc.status)}">${escapeHtml(status)}</span>
        ${error}
        <button class="document-delete" type="button" data-delete-document="${escapeHtml(doc.id)}">删除文档</button>
      </article>
    `;
  }).join("");
}

function upsertDocument(document) {
  const index = state.documents.findIndex((item) => item.id === document.id);
  if (index === -1) state.documents.unshift(document);
  else state.documents[index] = document;
  state.documents.sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
  renderDocuments();
}

function sleep(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function watchDocument(documentId) {
  if (state.polling.has(documentId)) return;
  state.polling.add(documentId);
  try {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      await sleep(2000);
      const document = await api(`/documents/${encodeURIComponent(documentId)}`);
      upsertDocument(document);
      if (["ready", "failed"].includes(document.status)) {
        showToast(document.status === "ready" ? `${document.filename} 已完成入库` : `${document.filename} 入库失败`, document.status === "failed" ? "error" : "");
        return;
      }
    }
    showToast("文档处理时间较长，请稍后刷新查看", "error");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    state.polling.delete(documentId);
  }
}

async function loadDocuments() {
  documentsList.innerHTML = '<div class="loading-state">正在加载文档…</div>';
  try {
    state.documents = await api("/documents");
    renderDocuments();
    state.documents.filter((doc) => ["pending", "processing"].includes(doc.status)).forEach((doc) => watchDocument(doc.id));
  } catch (error) {
    documentsList.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderChatSessions() {
  if (!state.chatSessions.length) {
    chatSessionsList.innerHTML = '<span class="session-empty">还没有历史对话</span>';
    return;
  }

  chatSessionsList.innerHTML = state.chatSessions.map((session) => `
    <div class="chat-session-item ${session.id === state.activeChatSessionId ? "active" : ""}">
      <button class="chat-session-select" type="button" data-select-chat-session="${escapeHtml(session.id)}" title="${escapeHtml(session.title || "新对话")}">
        <span>${escapeHtml(session.title || "新对话")}</span>
        <small>${formatDate(session.updated_at)}</small>
      </button>
      <button class="chat-session-delete" type="button" data-delete-chat-session="${escapeHtml(session.id)}" aria-label="删除对话" title="删除对话">×</button>
    </div>
  `).join("");
}

async function loadChatSessions(selectLatest = true) {
  chatSessionsList.innerHTML = '<span class="session-empty">正在加载对话…</span>';
  try {
    state.chatSessions = await api("/chat/sessions");
    if (selectLatest && state.chatSessions.length) {
      await selectChatSession(state.chatSessions[0].id);
    } else {
      renderChatSessions();
    }
  } catch (error) {
    chatSessionsList.innerHTML = `<span class="session-empty">${escapeHtml(error.message)}</span>`;
  }
}

async function selectChatSession(sessionId) {
  if (state.chatPending) return;
  state.activeChatSessionId = sessionId;
  state.chatMessages = [];
  state.chatPending = false;
  renderChatSessions();
  chatMessages.innerHTML = '<div class="loading-state">正在加载聊天记录…</div>';

  try {
    const messages = await api(`/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
    if (state.activeChatSessionId !== sessionId) return;
    state.chatMessages = messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      sources: [],
      evidenceOpen: false,
    }));
    renderChatMessages();
  } catch (error) {
    if (state.activeChatSessionId !== sessionId) return;
    setMessage(chatMessage, error.message, "error");
    renderChatMessages();
  }
}

function startNewChat() {
  if (state.chatPending) return;
  state.activeChatSessionId = null;
  state.chatMessages = [];
  state.chatPending = false;
  renderChatSessions();
  renderChatMessages();
  setMessage(chatMessage);
  chatInput.focus();
}

async function createChatSession(title) {
  const session = await api("/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title: title.slice(0, 80) }),
  });
  state.chatSessions.unshift(session);
  state.activeChatSessionId = session.id;
  renderChatSessions();
  return session.id;
}

async function deleteChatSession(sessionId) {
  if (state.chatPending) return;
  const session = state.chatSessions.find((item) => item.id === sessionId);
  if (!session || !window.confirm(`确认删除对话“${session.title || "新对话"}”及其聊天记录吗？`)) return;
  try {
    await api(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    state.chatSessions = state.chatSessions.filter((item) => item.id !== sessionId);
    if (state.activeChatSessionId === sessionId) {
      state.activeChatSessionId = null;
      state.chatMessages = [];
      renderChatMessages();
    }
    renderChatSessions();
    showToast("对话及聊天记录已删除");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const file = documentFile.files[0];
  if (!file) {
    setMessage(uploadMessage, "请先选择一个文件。", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  setMessage(uploadMessage, "文件已发送，正在创建后台任务…");
  setButtonBusy(uploadSubmit, true, "提交中…");

  try {
    const document = await api("/documents/upload", { method: "POST", body: formData });
    upsertDocument(document);
    documentFile.value = "";
    fileName.textContent = "选择一个文件";
    setMessage(uploadMessage, "已进入队列，状态会自动更新。", "success");
    watchDocument(document.id);
  } catch (error) {
    setMessage(uploadMessage, error.message, "error");
  } finally {
    setButtonBusy(uploadSubmit, false);
  }
}

async function handleDelete(documentId) {
  const document = state.documents.find((item) => item.id === documentId);
  if (!document || !window.confirm(`确认删除“${document.filename}”吗？`)) return;
  try {
    await api(`/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
    state.documents = state.documents.filter((item) => item.id !== documentId);
    renderDocuments();
    showToast("文档已删除");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function highlightContent(content, highlightTerms) {
  const terms = [...new Set(
    (Array.isArray(highlightTerms) ? highlightTerms : [])
      .filter((term) => typeof term === "string" && term.length > 0),
  )].sort((left, right) => right.length - left.length);

  if (!terms.length) return escapeHtml(content);

  const expression = new RegExp(`(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return String(content).split(expression).map((part) => {
    if (terms.some((term) => term.toLocaleLowerCase() === part.toLocaleLowerCase())) {
      return `<mark>${escapeHtml(part)}</mark>`;
    }
    return escapeHtml(part);
  }).join("");
}

function newMessageId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function renderEvidence(message) {
  const sources = Array.isArray(message.sources) ? message.sources : [];
  if (!sources.length) return "";

  const buttonLabel = message.evidenceOpen
    ? "收起检索依据 ▴"
    : `查看 ${sources.length} 条检索依据 ▾`;
  const cards = message.evidenceOpen ? `
    <div class="evidence-drawer">
      ${sources.map((source) => `
        <article class="evidence-card">
          <div class="result-top">
            <span class="result-file" title="${escapeHtml(source.filename)}">${escapeHtml(source.filename)}</span>
            <span class="result-score">相关度 ${(Number(source.score) || 0).toFixed(3)}</span>
          </div>
          <p class="result-content">${highlightContent(
            source.content,
            state.highlightEvidence ? source.highlight_terms : [],
          )}</p>
          <div class="result-foot">第 ${Number(source.chunk_index) + 1} 段 · 文档 ID ${escapeHtml(source.document_id)}</div>
        </article>
      `).join("")}
    </div>
  ` : "";

  return `
    <div class="evidence-block">
      <button class="evidence-toggle" type="button" data-toggle-evidence="${escapeHtml(message.id)}" aria-expanded="${message.evidenceOpen}">${buttonLabel}</button>
      ${cards}
    </div>
  `;
}

function renderChatMessages() {
  if (!state.chatMessages.length && !state.chatPending) {
    chatMessages.innerHTML = '<div class="empty-chat"><span>✦</span><p>提出问题，我会先检索已完成入库的资料，再基于资料回答。</p></div>';
    return;
  }

  const messageMarkup = state.chatMessages.map((message) => {
    const isAssistant = message.role === "assistant";
    const metadata = isAssistant && message.model && message.model !== "none"
      ? `<span class="chat-model">${escapeHtml(message.model)}</span>`
      : "";
    return `
      <article class="chat-turn chat-turn-${escapeHtml(message.role)}">
        <div class="chat-turn-label">${isAssistant ? "AI 知识助手" : "你"}${metadata}</div>
        <div class="chat-bubble">${escapeHtml(message.content)}</div>
        ${isAssistant ? renderEvidence(message) : ""}
      </article>
    `;
  }).join("");

  const pendingMarkup = state.chatPending
    ? '<div class="chat-pending"><span></span><span></span><span></span>正在检索资料并生成回答…</div>'
    : "";
  chatMessages.innerHTML = `${messageMarkup}${pendingMarkup}`;
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function toggleEvidence(messageId) {
  const message = state.chatMessages.find((item) => item.id === messageId);
  if (!message || message.role !== "assistant" || !message.sources?.length) return;
  message.evidenceOpen = !message.evidenceOpen;
  renderChatMessages();
}

async function handleChat(event) {
  event.preventDefault();
  const content = chatInput.value.trim();
  if (!content || state.chatPending) return;

  const userMessageId = newMessageId();
  state.chatPending = true;
  chatInput.value = "";
  setMessage(chatMessage, "正在检索资料并生成回答…");
  setButtonBusy(chatSubmit, true, "回答中…");
  renderChatMessages();

  try {
    const sessionId = state.activeChatSessionId || await createChatSession(content);
    state.chatMessages.push({ id: userMessageId, role: "user", content });
    renderChatMessages();
    const response = await api("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: content,
        session_id: sessionId,
        top_k: Number(chatTopK.value),
        mode: chatMode.value,
      }),
      // 首次对话可能同时加载检索模型与 LM Studio 中的聊天模型。
      timeoutMs: 180000,
    });
    const sources = Array.isArray(response.sources) ? response.sources : [];
    state.chatMessages.push({
      id: newMessageId(),
      role: "assistant",
      content: response.reply,
      model: response.model,
      sources,
      evidenceOpen: false,
    });
    setMessage(
      chatMessage,
      sources.length ? `回答已生成，包含 ${sources.length} 条检索依据。` : "知识库中没有找到可用资料。",
      sources.length ? "success" : "",
    );
    await loadChatSessions(false);
  } catch (error) {
    state.chatMessages = state.chatMessages.filter((message) => message.id !== userMessageId);
    const detail = error.message.includes("503") || error.message.includes("LLM")
      ? "模型服务不可用，请确认 LM Studio 已启动且已加载模型。"
      : error.message;
    setMessage(chatMessage, detail, "error");
    showToast(detail, "error");
  } finally {
    state.chatPending = false;
    setButtonBusy(chatSubmit, false);
    renderChatMessages();
    chatInput.focus();
  }
}

function showToast(message, type = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;
  toastRegion.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

function bindDropZone() {
  ["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  }));
  dropZone.addEventListener("drop", (event) => {
    const [file] = event.dataTransfer.files;
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    documentFile.files = transfer.files;
    fileName.textContent = file.name;
  });
}

async function bootstrap() {
  document.querySelectorAll("[data-auth-tab]").forEach((tab) => tab.addEventListener("click", () => switchAuthMode(tab.dataset.authTab)));
  authForm.addEventListener("submit", handleAuth);
  uploadForm.addEventListener("submit", handleUpload);
  chatForm.addEventListener("submit", handleChat);
  chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });
  chatMessages.addEventListener("click", (event) => {
    const button = event.target.closest("[data-toggle-evidence]");
    if (button) toggleEvidence(button.dataset.toggleEvidence);
  });
  newChatButton.addEventListener("click", startNewChat);
  chatSessionsList.addEventListener("click", (event) => {
    const deleteButton = event.target.closest("[data-delete-chat-session]");
    if (deleteButton) {
      deleteChatSession(deleteButton.dataset.deleteChatSession);
      return;
    }
    const selectButton = event.target.closest("[data-select-chat-session]");
    if (selectButton) selectChatSession(selectButton.dataset.selectChatSession);
  });
  evidenceHighlightToggle.addEventListener("change", () => {
    state.highlightEvidence = evidenceHighlightToggle.checked;
    renderChatMessages();
  });
  documentFile.addEventListener("change", () => {
    fileName.textContent = documentFile.files[0]?.name || "选择一个文件";
  });
  $("#refresh-documents").addEventListener("click", loadDocuments);
  documentsList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-document]");
    if (button) handleDelete(button.dataset.deleteDocument);
  });
  $("#logout-button").addEventListener("click", () => {
    clearSession();
    state.documents = [];
    state.chatSessions = [];
    state.activeChatSessionId = null;
    state.chatMessages = [];
    state.chatPending = false;
    renderChatSessions();
    renderChatMessages();
    showAuth();
    showToast("已退出登录");
  });
  bindDropZone();

  if (!state.token) {
    showAuth();
    return;
  }

  try {
    state.user = await api("/auth/me");
    showApp();
    await Promise.all([loadDocuments(), loadChatSessions()]);
  } catch {
    showAuth();
  }
}

bootstrap();
