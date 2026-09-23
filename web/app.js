let state = null;
let selectedAccount = "";
let busy = false;
let loginType = "official";
let officialLoginId = "";
let officialLoginPoll = null;
let modelCandidates = [];
let selectedModelIds = new Set();
let modelPreviewAccount = "";
let modelRefreshing = false;
let draftDefaultModel = "";
let modelDirty = false;
let modelApplyError = "";
let currentPage = "home";
let usage = null;
let usagePeriod = "today";
let usageRequest = 0;

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));

async function api(path, body) {
  const options = body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)};
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  if (payload.data) state = payload.data;
  return payload;
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast show${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.className = "toast", 3200);
}

function selected() {
  return state?.accounts.find((account) => account.name === selectedAccount) || null;
}

function connectionType(account) {
  if (account?.account_type === "official") return "official";
  return "openai_compatible";
}

function isOfficialAccount(account) {
  return connectionType(account) === "official";
}

function accountTypeLabel(account) {
  if (isOfficialAccount(account)) return "OpenAI 官方";
  return `${account.provider_id || "未命名 Provider"} · 兼容渠道`;
}

function render() {
  if (!state) return;
  const active = state.accounts.find((account) => account.active) || null;
  if (!selectedAccount || !state.accounts.some((account) => account.name === selectedAccount)) selectedAccount = active?.name || state.accounts[0]?.name || "";
  renderAccounts();
  renderHeader(active);
  ensureModelCandidates(active);
  renderModels();
  renderImageGeneration();
}

function renderImageGeneration() {
  const image = state.image_generation || {};
  const channel = image.provider === "official" ? "OpenAI 官方" : (image.mode === "responses" ? "Responses" : "Images");
  const version = image.installed_version ? `v${image.installed_version}` : "未安装";
  const summary = image.configured
    ? `${channel} · ${image.account_name || image.image_model || "已配置"} · ${version}${image.pending_apply ? " · 待应用" : ""}`
    : `尚未配置 · ${version}`;
  $("#imageGenerationSummary").textContent = summary;
  $("#configureImageGeneration").disabled = busy;
  $("#applyImageGeneration").disabled = busy || (!image.configured && image.enabled !== false);
}

function ensureModelCandidates(active) {
  const accountName = active?.name || "";
  if (modelPreviewAccount === accountName && modelDirty) return;
  modelPreviewAccount = accountName;
  modelCandidates = state.models.map((model) => ({...model}));
  selectedModelIds = new Set(state.models.filter((model) => model.visibility !== "hide").map((model) => model.slug));
  draftDefaultModel = state.current.model || "";
  modelDirty = false;
  modelApplyError = "";
}

let expandedQuota = "";
function renderAccounts() {
  const quotaNode = $("#accountQuota");
  $(".account-detail").append(quotaNode);
  $("#accountList").innerHTML = state.accounts.length ? state.accounts.map(account => `
    <article class="account-row ${account.active ? "is-active" : ""}">
      <div class="row-identity"><strong>${escapeHtml(account.name)}</strong><small>${escapeHtml(accountTypeLabel(account))}</small></div>
      <div class="row-connection" title="${escapeHtml(account.base_url || account.email || "")}">${escapeHtml(isOfficialAccount(account) ? (account.plan_type || "ChatGPT") : account.base_url)}</div>
      <span class="row-status">${account.active ? "使用中" : "未启用"}</span>
      <div class="row-actions">
        <button type="button" class="text-button" data-row-edit="${escapeHtml(account.name)}" ${busy ? "disabled" : ""}>${isOfficialAccount(account) ? "授权" : "编辑"}</button>
        ${isOfficialAccount(account) ? `<button type="button" class="text-button" data-row-quota="${escapeHtml(account.name)}" aria-expanded="${expandedQuota === account.name}">额度</button>` : `<button type="button" class="text-button" data-row-verify="${escapeHtml(account.name)}" ${busy ? "disabled" : ""}>验证</button>`}
        <button type="button" class="text-button row-delete" data-row-delete="${escapeHtml(account.name)}" ${busy ? "disabled" : ""} title="从管理器列表移除，保留 Codex 当前登录">移除</button>
        <button type="button" class="secondary-button" data-row-use="${escapeHtml(account.name)}" ${busy || account.active ? "disabled" : ""}>${account.active ? "已启用" : "使用"}</button>
      </div>
      ${isOfficialAccount(account) ? accountQuotaSummary(account) : ""}
      <div class="row-quota-slot" data-quota-slot="${escapeHtml(account.name)}"></div>
    </article>`).join("") : '<div class="empty-rail">还没有账号，点击“添加账号”开始。</div>';
  document.querySelectorAll("[data-row-edit]").forEach(button => button.onclick = () => {
    selectedAccount = button.dataset.rowEdit;
    openDialog(selected());
  });
  document.querySelectorAll("[data-row-delete]").forEach(button => button.onclick = () => {
    deleteAccount(state.accounts.find(item => item.name === button.dataset.rowDelete));
  });
  document.querySelectorAll("[data-row-use]").forEach(button => button.onclick = () => {
    const account = state.accounts.find(item => item.name === button.dataset.rowUse);
    activateAccount(account);
  });
  document.querySelectorAll("[data-row-verify]").forEach(button => button.onclick = async () => {
    if (busy) return;
    const account = state.accounts.find(item => item.name === button.dataset.rowVerify);
    busy = true; render();
    try {
      const response = await api("/api/accounts/verify", {...account, original_name: account.name});
      toast(response.message || "连接验证通过");
    } catch (error) { toast(error.message, true); }
    finally { busy = false; render(); }
  });
  document.querySelectorAll("[data-row-quota]").forEach(button => button.onclick = () => {
    selectedAccount = button.dataset.rowQuota;
    expandedQuota = expandedQuota === selectedAccount ? "" : selectedAccount;
    renderAccounts();
  });
  document.querySelectorAll("[data-row-refresh]").forEach(button => button.onclick = () => refreshAccountQuota(state.accounts.find(item => item.name === button.dataset.rowRefresh)));
  const account = selected();
  $("#detailName").textContent = account?.name || "添加第一个账号";
  $("#detailType").textContent = account ? accountTypeLabel(account) + (isOfficialAccount(account) && account.plan_type ? ` · ${account.plan_type.toUpperCase()}` : "") : "连接你的 Codex";
  $("#detailConnection").textContent = account ? (isOfficialAccount(account) ? account.email || "ChatGPT 官方授权" : account.base_url) : "—";
  $("#detailStatus").textContent = account ? (account.active ? "当前使用" : "未启用") : "尚无账号";
  $("#activateSelected").textContent = account?.active ? "正在使用" : "使用此账号";
  $("#activateSelected").disabled = !account || account.active || busy;
  $("#editSelected").disabled = !account || busy;
  $("#editSelected").textContent = isOfficialAccount(account) ? "管理授权" : "编辑";
  $("#verifySelected").hidden = !account || isOfficialAccount(account);
  $("#verifySelected").disabled = busy;
  renderAccountQuota(account);
  const slot = [...document.querySelectorAll("[data-quota-slot]")].find(node => node.dataset.quotaSlot === expandedQuota);
  if (slot && account?.name === expandedQuota) slot.append(quotaNode);
}

function renderHeader(active) {
  const official = isOfficialAccount(active);
  $("#activeTitle").textContent = active?.name || "尚未启用账号";
  $("#activeRoute").textContent = active ? accountTypeLabel(active) : "请先添加并启用账号";
  if (currentPage !== "accounts") $("#pageDescription").textContent = `当前账号：${active?.name || "未启用"}`;
  const sync = state.sync || {};
  $("#syncError").hidden = sync.status !== "error";
  $("#syncError").textContent = sync.status === "error" ? `同步失败：${sync.error || "请重试"}` : "";
  const status = $("#codexStatus");
  status.classList.toggle("running", state.codex.running);
  status.querySelector("span").textContent = state.codex.running ? "Codex 运行中" : "Codex 未运行";
  $("#syncLaunch").disabled = !active || busy;
  $("#claimHistory").disabled = !active || busy;
  $("#addAccount").disabled = busy;
  $("#submitAccount").disabled = busy || !!officialLoginId;
  $("#modelPanelTitle").textContent = official ? "官方模型" : "模型";
}

function renderModels() {
  const active = state.accounts.find((account) => account.active) || null;
  const official = isOfficialAccount(active);
  const select = $("#modelSelect");
  const visibleModels = modelCandidates.filter((model) => selectedModelIds.has(model.slug));
  if (!visibleModels.some(model => model.slug === draftDefaultModel)) draftDefaultModel = visibleModels[0]?.slug || "";
  select.innerHTML = visibleModels.length ? visibleModels.map((model) => `<option value="${escapeHtml(model.slug)}" ${model.slug === draftDefaultModel ? "selected" : ""}>${escapeHtml(model.display_name || model.slug)}</option>`).join("") : `<option value="">请先选择模型</option>`;
  select.disabled = !visibleModels.length || busy;
  $("#modelSelectionCount").textContent = official ? `${modelCandidates.length} 个官方模型` : `已选 ${selectedModelIds.size} / ${modelCandidates.length}`;
  $("#selectAllModels").disabled = official || busy || !modelCandidates.length;
  $("#clearModels").disabled = official || busy || !modelCandidates.length;
  $("#restoreOfficialModels").hidden = official || !active;
  $("#restoreOfficialModels").disabled = busy || official || !active;
  $("#refreshModels").disabled = busy || modelRefreshing || !active;
  $("#refreshModels").classList.toggle("loading", modelRefreshing);
  $("#modelGrid").classList.toggle("loading", modelRefreshing);
  $("#applyModels").disabled = busy || !active || !modelDirty || !selectedModelIds.size;
  $("#discardModels").hidden = !modelDirty;
  $("#discardModels").disabled = busy;
  $("#modelChangeState").textContent = modelApplyError || (modelDirty ? "有未应用的更改" : "已应用");
  const query = $("#modelSearch").value.trim().toLowerCase();
  const filtered = modelCandidates.filter(model => `${model.display_name || ""} ${model.slug}`.toLowerCase().includes(query));
  $("#modelGrid").innerHTML = filtered.length ? filtered.map((model) => `
    <label class="model-option ${selectedModelIds.has(model.slug) ? "selected" : ""}" title="${escapeHtml(model.slug)}">
      <input type="checkbox" data-model-id="${escapeHtml(model.slug)}" ${selectedModelIds.has(model.slug) ? "checked" : ""} ${official || busy ? "disabled" : ""}>
      <span><strong>${escapeHtml(model.display_name || model.slug)}</strong></span>
    </label>`).join("") : `<div class="model-empty">${query ? "没有匹配的模型" : "刷新列表以获取可用模型"}</div>`;
  document.querySelectorAll("[data-model-id]").forEach((input) => input.onchange = () => {
    if (input.checked) selectedModelIds.add(input.dataset.modelId); else selectedModelIds.delete(input.dataset.modelId);
    modelDirty = true;
    renderModels();
  });
}

function openDialog(account = null) {
  if (busy) return;
  clearOfficialLogin();
  $("#importConfig").value = "";
  $("#importAuth").value = "";
  $("#importResult").textContent = "";
  $("#configImport").open = false;
  $("#dialogTitle").textContent = account ? "编辑账号" : "新增账号";
  $("#originalName").value = account?.name || "";
  $("#accountName").value = account?.name || "";
  $("#providerId").value = account?.provider_id || "";
  $("#baseUrl").value = account?.base_url || "";
  $("#apiKey").value = "";
  $("#apiKey").required = !account?.has_api_key;
  setDefaultModelOptions([], account?.default_model || "");
  $("#effort").value = account?.reasoning_effort || "high";
  $("#deleteAccount").hidden = !account;
  $("#deleteAccount").disabled = false;
  $("#deleteAccount").title = "从管理器列表移除";
  $("#loginTypePicker").hidden = !!account;
  setLoginType(account ? (isOfficialAccount(account) ? "official" : "custom") : "official");
  $("#officialAccountName").value = isOfficialAccount(account) ? account.name : "";
  $("#officialLoginState").textContent = isOfficialAccount(account) ? "官方账号已授权；重新登录会添加新的账号档案。" : "尚未开始授权";
  $("#accountDialog").showModal();
}

function updateImageGenerationFields() {
  const enabled = true;
  const separate = $("#imageSource").value === "separate";
  const account = state?.accounts.find(item => item.name === $("#imageAccount").value);
  const official = !separate && isOfficialAccount(account);
  $("#imageMode").value = "images";
  $("#imageGenerationFields").hidden = !enabled;
  document.querySelectorAll(".separate-image-field").forEach(node => node.hidden = !separate);
  document.querySelectorAll(".managed-image-field").forEach(node => node.hidden = separate);

  $("#imageAccount").required = enabled && !separate;
  $("#imageMode").disabled = true;
  $("#imageBaseUrl").required = enabled && separate;
  $("#imageApiKey").required = enabled && separate && !state.image_generation?.has_api_key;

  $("#imageCredentialHint").textContent = separate
    ? "仅用于生成和编辑图片，使用 Images API；对话主模型由 Codex 当前选择决定。凭据保存在 ~/.maolike/codex。"
    : official
      ? "MCP 使用该账号已保存的 OAuth 验证和账号 ID，请求 OpenAI Codex Responses 图片工具。"
      : "MCP 使用该账号保存的 Base URL 与 API Key；图片配置固定到所选账号。";
}

function openImageGenerationDialog() {
  if (busy) return;
  const image = state.image_generation || {};
  $("#imageSource").value = image.source === "active_account" ? "managed_account" : (image.source || "managed_account");
  $("#imageAccount").innerHTML = state.accounts.length
    ? state.accounts.map(account => `<option value="${escapeHtml(account.name)}">${escapeHtml(account.name)} · ${escapeHtml(accountTypeLabel(account))}</option>`).join("")
    : `<option value="">暂无已管理账号</option>`;
  $("#imageAccount").value = image.account_name && state.accounts.some(account => account.name === image.account_name)
    ? image.account_name
    : (state.accounts.find(account => account.active)?.name || state.accounts[0]?.name || "");
  $("#imageBaseUrl").value = image.base_url || "https://api.openai.com/v1";
  $("#imageApiKey").value = "";
  $("#imageMode").value = image.mode || "images";
  $("#imageModel").value = image.image_model || "gpt-image-2";

  $("#imageGenerationError").textContent = "";
  updateImageGenerationFields();
  $("#imageGenerationDialog").showModal();
}

function setDefaultModelOptions(modelIds, selectedModel = "") {
  const models = [...new Set(modelIds.filter((model) => typeof model === "string" && model.trim()).map((model) => model.trim()))];
  if (selectedModel && !models.includes(selectedModel)) models.unshift(selectedModel);
  $("#defaultModel").innerHTML = models.length
    ? models.map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("")
    : `<option value="">请先验证登录并获取模型</option>`;
  $("#defaultModel").value = selectedModel && models.includes(selectedModel) ? selectedModel : models[0] || "";
}

function setLoginType(type) {
  loginType = type;
  const external = type !== "official";
  document.querySelectorAll("[data-login-type]").forEach((button) => {
    const active = button.dataset.loginType === type;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", String(active));
  });
  $("#officialLoginPanel").hidden = type !== "official";
  $("#customAccountFields").hidden = !external;
  $("#connectionHelp").textContent = "验证会读取兼容渠道 /models，不会保存或切换账号。";
  $("#verifyAccount").hidden = !external;
  $("#submitAccount").textContent = type === "official" ? "登录并添加" : "保存账号";
  for (const input of $("#customAccountFields").querySelectorAll("input, select")) input.disabled = !external;
}

function clearOfficialLogin() {
  officialLoginId = "";
  clearInterval(officialLoginPoll);
  officialLoginPoll = null;
  $("#deviceActions").hidden = true;
}

async function closeAccountDialog() {
  const loginId = officialLoginId;
  clearOfficialLogin();
  $("#accountDialog").close();
  if (loginId) {
    try { await api("/api/accounts/official-login/cancel", {login_id:loginId}); } catch (_) {}
  }
}

async function mutate(path, body, pendingText) {
  if (busy) return;
  busy = true;
  render();
  try {
    const result = await api(path, body);
    toast(result.message || "操作完成");
    render();
    return result;
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy = false;
    render();
  }
}

async function syncAndLaunchCodex() {
  if (busy) return;
  const dialog = $("#launchDialog");
  busy = true;
  render();
  dialog.showModal();
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  try {
    const result = await api("/api/codex/launch", {restart:true});
    toast(result.message || "Codex 已启动");
    render();
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (dialog.open) dialog.close();
    busy = false;
    render();
  }
}

$("#addAccount").onclick = () => openDialog();
document.querySelectorAll("[data-login-type]").forEach((button) => button.onclick = () => setLoginType(button.dataset.loginType));
$("#closeDialog").onclick = $("#cancelDialog").onclick = closeAccountDialog;
function accountPayload() {
  return {
    original_name: $("#originalName").value, name: $("#accountName").value, provider_id: $("#providerId").value,
    provider_name: $("#accountName").value, base_url: $("#baseUrl").value, api_key: $("#apiKey").value,
    default_model: $("#defaultModel").value, reasoning_effort: $("#effort").value, wire_api: "responses",
    connection_type: "openai_compatible",
    auth_mode: "legacy",
    transport: "http_sse"
  };
}
$("#accountForm").onsubmit = async (event) => {
  event.preventDefault();
  if (busy) return;
  if (loginType === "official") {
    if (officialLoginId) return;
    busy = true;
    render();
    try {
      const started = await api("/api/accounts/official-login/start", {});
      officialLoginId = started.result.login_id;
      $("#officialLoginState").className = "official-login-state pending";
      const code = started.result.user_code;
      $("#deviceActions").hidden = !code;
      $("#copyDeviceCode").onclick = async () => {
        try { await navigator.clipboard.writeText(code); toast("验证码已复制"); }
        catch (_) { toast("复制失败，请手动选择验证码复制", true); }
      };
      const verificationUrl = new URL(started.result.verification_url);
      if (verificationUrl.protocol !== "https:") throw new Error("授权地址必须使用 HTTPS");
      $("#verificationLink").href = verificationUrl.href;
      $("#officialLoginState").textContent = code
        ? `请在已打开的 OpenAI 页面输入设备验证码：${code}`
        : "等待浏览器完成 OpenAI 官方授权…";
      officialLoginPoll = setInterval(pollOfficialLogin, 1200);
    } catch (error) {
      $("#officialLoginState").className = "official-login-state failed";
      $("#officialLoginState").textContent = error.message;
      toast(error.message, true);
    } finally {
      busy = false;
      render();
    }
    return;
  }
  const payload = accountPayload();
  const result = await mutate("/api/accounts/save", payload);
  if (result) { selectedAccount = payload.name.trim(); $("#accountDialog").close(); }
};

async function pollOfficialLogin() {
  if (!officialLoginId) return;
  try {
    const result = await api(`/api/accounts/official-login/status?login_id=${encodeURIComponent(officialLoginId)}`);
    const login = result.result;
    if (login.status === "pending") return;
    clearInterval(officialLoginPoll);
    officialLoginPoll = null;
    if (login.status !== "completed") {
      $("#officialLoginState").className = "official-login-state failed";
      $("#officialLoginState").textContent = login.error || "官方登录失败";
      officialLoginId = "";
      return;
    }
    $("#officialLoginState").className = "official-login-state completed";
    $("#officialLoginState").textContent = `已验证 ${login.email || "OpenAI 官方账号"}，正在添加…`;
    busy = true;
    render();
    const completed = await api("/api/accounts/official-login/complete", {
      login_id: officialLoginId,
      name: $("#officialAccountName").value
    });
    selectedAccount = completed.account.name;
    clearOfficialLogin();
    $("#accountDialog").close();
    toast(completed.message || "官方账号已添加");
  } catch (error) {
    clearOfficialLogin();
    $("#officialLoginState").className = "official-login-state failed";
    $("#officialLoginState").textContent = error.message;
    toast(error.message, true);
  } finally {
    busy = false;
    render();
  }
}
$("#verifyAccount").onclick = async () => {
  if (busy) return;
  busy = true;
  render();
  try {
    const result = await api("/api/accounts/verify", accountPayload());
    const selectedModel = $("#defaultModel").value;
    const modelIds = result.result.model_ids;
    setDefaultModelOptions(modelIds, modelIds.includes(selectedModel) ? selectedModel : "");
    toast(result.message || ("验证通过，共 " + result.result.models + " 个模型"));
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy = false;
    render();
  }
};
async function deleteAccount(account, closeDialog = false) {
  if (busy || !account || !await confirmAction(`将“${account.name}”从管理器列表移除，并删除管理器保存的账号档案。Codex 当前配置和登录状态保持不变，不会注销账号、取消订阅或删除对话。`, "移除账号", "确认移除")) return;
  const result = await mutate("/api/accounts/delete", {name:account.name});
  if (result) {
    quotaCache.delete(account.name);
    if (expandedQuota === account.name) expandedQuota = "";
    selectedAccount = "";
    modelPreviewAccount = "";
    if (closeDialog && $("#accountDialog").open) $("#accountDialog").close();
  }
}
$("#deleteAccount").onclick = () => deleteAccount(selected(), true);
async function activateAccount(account) {
  if (busy || !account) return;
  if (modelDirty && !await confirmAction("模型更改尚未应用。切换账号将放弃这些更改，继续？")) return;
  const action = isOfficialAccount(account) ? "切换官方登录凭据并载入 Codex 官方模型（运行中的 Codex 需随后重启）" : "切换渠道并载入本地模型目录";
  if (!account || !await confirmAction(`${action}：“${account.name}”？`)) return;
  selectedAccount = account.name;
  await mutate("/api/accounts/activate", {name:account.name});
}

async function refreshModels({silent = false} = {}) {
  if (busy || modelRefreshing) return;
  if (modelDirty && !await confirmAction("刷新列表将替换尚未应用的选择，继续？")) return;
  modelRefreshing = true;
  busy = true;
  render();
  try {
    const response = await api("/api/models/preview", {});
    const known = new Map(state.models.map((model) => [model.slug, model]));
    modelCandidates = response.result.model_ids.map((slug) => known.get(slug) || {slug, display_name:slug});
    const available = new Set(response.result.model_ids);
    const saved = response.result.selected_model_ids.filter((slug) => available.has(slug));
    selectedModelIds = new Set(saved.length ? saved : response.result.model_ids);
    modelPreviewAccount = response.result.account;
    modelDirty = true;
    if (!silent) toast(response.message || `已获取 ${modelCandidates.length} 个模型`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    modelRefreshing = false;
    busy = false;
    render();
  }
}

const pageInfo = {home: ["使用概览", "查看当前账号的使用情况。"], accounts: ["账号", "管理连接，选择当前使用的账号。"], models: ["模型", "选择模型后统一应用。"], tools: ["工具", "维护操作仅在确认后执行。"]};
const pageScrollPositions = new Map();
document.querySelectorAll("[data-page]").forEach(button => button.onclick = () => {
  if (currentPage === button.dataset.page) return;
  const content = $(".page-content");
  pageScrollPositions.set(currentPage, content.scrollTop);
  currentPage = button.dataset.page;
  document.querySelectorAll("[data-page]").forEach(item => {
    if (item === button) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  for (const name of Object.keys(pageInfo)) $("#" + name + "Page").hidden = name !== currentPage;
  $("#pageTitle").textContent = pageInfo[currentPage][0];
  $("#pageDescription").textContent = pageInfo[currentPage][1];
  if (state) renderHeader(state.accounts.find(account => account.active));
  content.scrollTop = pageScrollPositions.get(currentPage) || 0;
  if (currentPage === "home") refreshUsage();
});
const exactTokens = value => Number(value || 0).toLocaleString("zh-CN");
const tokenNumber = value => {
  const number = Number(value || 0);
  if (number >= 99995000) return `${(number / 1e8).toLocaleString("zh-CN", {maximumFractionDigits: 2})} 亿`;
  if (number >= 10000) return `${(number / 1e4).toLocaleString("zh-CN", {maximumFractionDigits: 2})} 万`;
  return exactTokens(number);
};
const costText = (value, unit) => unit === "credits" ? `${Number(value || 0).toFixed(3)} credits` : `$${Number(value || 0).toFixed(4)}`;
function renderUsage() {
  if (!usage) return;
  const totals = usage.totals;
  const dates = usage.date === usage.end_date ? usage.date : `${usage.date} 至 ${usage.end_date}`;
  $("#usageScope").textContent = `${dates} · ${usage.provider_id}${usage.unit === "credits" ? " · 官方账号共用 Provider" : ""}`;
  $("#usageTotal").textContent = tokenNumber(totals.input_tokens + totals.output_tokens);
  $("#usageTotal").title = `${exactTokens(totals.input_tokens + totals.output_tokens)} Token`;
  $("#usageInput").textContent = tokenNumber(totals.input_tokens);
  $("#usageInput").title = `${exactTokens(totals.input_tokens)} Token`;
  $("#usageCached").textContent = tokenNumber(totals.cached_input_tokens);
  $("#usageCached").title = `${exactTokens(totals.cached_input_tokens)} Token`;
  $("#usageOutput").textContent = tokenNumber(totals.output_tokens);
  $("#usageOutput").title = `${exactTokens(totals.output_tokens)} Token`;
  $("#usageReasoning").textContent = tokenNumber(totals.reasoning_output_tokens);
  $("#usageReasoning").title = `${exactTokens(totals.reasoning_output_tokens)} Token`;
  $("#usageCostLabel").textContent = usage.unit === "credits" ? "估算 credits" : "估算 API 费用";
  $("#usageCost").textContent = `${totals.unpriced_tokens ? "≥ " : ""}${costText(totals.estimated_cost, usage.unit)}`;
  $("#usageRows").innerHTML = usage.models.length ? usage.models.map(row => `<tr><td data-label="模型">${escapeHtml(row.model)}</td><td data-label="输入" title="${exactTokens(row.input_tokens)} Token">${tokenNumber(row.input_tokens)}</td><td data-label="缓存" title="${exactTokens(row.cached_input_tokens)} Token">${tokenNumber(row.cached_input_tokens)}</td><td data-label="输出" title="${exactTokens(row.output_tokens)} Token">${tokenNumber(row.output_tokens)}</td><td data-label="其中思考" title="${exactTokens(row.reasoning_output_tokens)} Token">${tokenNumber(row.reasoning_output_tokens)}</td><td data-label="估算费用">${row.unpriced_tokens ? "≥ " : ""}${costText(row.estimated_cost, usage.unit)}</td></tr>`).join("") : '<tr><td colspan="6">所选时间暂无用量记录</td></tr>';
  const totalTokens = totals.input_tokens + totals.output_tokens;
  $("#usageDistribution").innerHTML = usage.models.length ? [...usage.models]
    .sort((a, b) => (b.input_tokens + b.output_tokens) - (a.input_tokens + a.output_tokens))
    .map(row => {
      const share = totalTokens > 0 ? Math.min(100, Math.max(0, (row.input_tokens + row.output_tokens) / totalTokens * 100)) : 0;
      return `<div class="distribution-row"><span>${escapeHtml(row.model)}</span><progress class="distribution-track" max="100" value="${share}" aria-label="${escapeHtml(row.model)} Token 占比"></progress><strong>${share.toFixed(1)}%</strong></div>`;
    }).join("") : '<p class="distribution-empty">所选时间暂无用量记录</p>';
  $("#usageModelCount").textContent = `${usage.models.length} 个模型`;
  const notes = ["思考 Token 按本地记录上报值统计，已包含在输出中，不重复计费", "按官方 Standard 价格估算，不代表渠道账单或订阅扣费"];
  if (totals.unpriced_tokens) notes.push(`${tokenNumber(totals.unpriced_tokens)} token 未计价`);
  if (usage.skipped_files) notes.push(`${usage.skipped_files} 个记录文件未能读取`);
  $("#usageNote").textContent = notes.join(" · ");
  $("#usagePriceSource").href = usage.price_source;
}
async function refreshUsage() {
  if (!state?.active_account) { $("#usageNote").textContent = "请先启用账号"; return; }
  const request = ++usageRequest;
  const date = $("#usageDate").value;
  const query = new URLSearchParams({period: usagePeriod});
  if (usagePeriod === "date") query.set("date", date);
  $("#refreshUsage").disabled = true;
  try {
    const result = (await api(`/api/usage?${query}`)).result;
    if (request === usageRequest && JSON.stringify(usage) !== JSON.stringify(result)) {
      usage = result;
      renderUsage();
    }
  } catch (error) {
    if (request === usageRequest) {
      usage = null;
      $("#usageNote").textContent = error.message;
    }
  }
  finally { if (request === usageRequest) $("#refreshUsage").disabled = false; }
}
$("#refreshUsage").onclick = refreshUsage;
document.querySelectorAll("[data-usage-period]").forEach(button => button.onclick = () => {
  usagePeriod = button.dataset.usagePeriod;
  document.querySelectorAll("[data-usage-period]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
  $("#usageDate").value = "";
  refreshUsage();
});
$("#usageDate").onchange = event => {
  if (!event.target.value) return;
  usagePeriod = "date";
  document.querySelectorAll("[data-usage-period]").forEach(item => item.setAttribute("aria-pressed", "false"));
  refreshUsage();
};
$("#activateSelected").onclick = () => activateAccount(selected());
$("#editSelected").onclick = () => openDialog(selected());
$("#verifySelected").onclick = async () => {
  const account = selected();
  if (!account || busy) return;
  busy = true;
  $("#accountResult").textContent = "正在验证连接…";
  render();
  try {
    const response = await api("/api/accounts/verify", {...account, original_name: account.name});
    $("#accountResult").textContent = response.message || "连接验证通过";
  } catch (error) { $("#accountResult").textContent = `验证失败：${error.message}`; }
  finally { busy = false; render(); }
};
$("#refreshModels").onclick = () => refreshModels();
$("#modelSearch").oninput = renderModels;
$("#restoreOfficialModels").onclick = async () => {
  if (busy || !await confirmAction("恢复指定的 6 个官方模型（GPT-5.6 Luna / Sol / Terra、GPT-6 Astra / Luna / Sol）？将替换当前模型目录并保存到 Codex 配置；当前默认模型不在列表中时改为 GPT-5.6 Luna。")) return;
  const result = await mutate("/api/models/restore-official", {});
  if (result) { modelDirty = false; modelPreviewAccount = ""; render(); }
};
$("#selectAllModels").onclick = () => { selectedModelIds = new Set(modelCandidates.map(model => model.slug)); modelDirty = true; renderModels(); };
$("#clearModels").onclick = () => { selectedModelIds.clear(); modelDirty = true; renderModels(); };
$("#modelSelect").onchange = event => { draftDefaultModel = event.target.value; modelDirty = true; renderModels(); };
$("#discardModels").onclick = () => { modelDirty = false; modelPreviewAccount = ""; render(); };
$("#applyModels").onclick = async () => {
  const account = state?.accounts.find(item => item.active);
  if (busy || !account || !modelDirty || !selectedModelIds.size) return;
  const defaultModel = draftDefaultModel;
  modelApplyError = "";
  busy = true;
  $("#operationLoadingTitle").textContent = "正在应用模型";
  $("#injectionLoadingText").textContent = "保存模型目录和默认模型，请稍候…";
  $("#injectionLoading").hidden = false;
  render();
  let stage = "模型目录";
  try {
    if (!isOfficialAccount(account)) await api("/api/accounts/post-switch", {name: account.name, sync_models: true, model_ids: [...selectedModelIds], claim_history: false});
    stage = "默认模型";
    await api("/api/models/select", {model: defaultModel});
    modelDirty = false;
    modelPreviewAccount = "";
    toast("模型设置已应用；默认模型在下次启动或新任务中使用");
  } catch (error) {
    modelApplyError = `${stage}应用失败：${error.message}。已完成的步骤可能已生效，请重试或放弃更改后查看当前状态。`;
    toast(modelApplyError, true);
  } finally { busy = false; $("#injectionLoading").hidden = true; render(); }
};
async function runTool(title, description, path, body) {
  if (busy || !await confirmAction(description, title, "确认执行")) return;
  busy = true;
  $("#operationLoadingTitle").textContent = title;
  $("#injectionLoadingText").textContent = "执行中，请勿关闭管理器…";
  $("#injectionLoading").hidden = false;
  $("#toolResult").textContent = `${title}，请稍候…`;
  render();
  try {
    const response = await api(path, body);
    $("#toolResult").textContent = `${title}完成。${response.message || ""}`;
    toast(`${title}完成`);
  } catch (error) {
    $("#toolResult").textContent = `${title}失败：${error.message}`;
    toast(error.message, true);
  } finally { busy = false; $("#injectionLoading").hidden = true; render(); }
}
$("#claimHistory").onclick = () => {
  const account = state?.accounts.find(item => item.active);
  if (account) runTool("归纳历史会话", `将全部本地会话归属到“${account.name}”？该操作不保留备份。`, "/api/history/claim-all", {name: account.name});
};
$("#configureImageGeneration").onclick = openImageGenerationDialog;
$("#applyImageGeneration").onclick = () => runTool("应用图片工具", "比较插件版本并安装或更新图片插件，同时应用当前图片配置？", "/api/image-generation/apply", {});
$("#imageSource").onchange = updateImageGenerationFields;
$("#imageAccount").onchange = updateImageGenerationFields;
$("#imageMode").onchange = updateImageGenerationFields;
$("#closeImageGeneration").onclick = () => $("#imageGenerationDialog").close();
$("#cancelImageGeneration").onclick = () => $("#imageGenerationDialog").close();
$("#imageGenerationForm").onsubmit = async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  $("#imageGenerationError").textContent = "";
  $("#saveImageGeneration").disabled = true;
  try {
    const response = await api("/api/image-generation/configure", {
      enabled: true,
      source: $("#imageSource").value,
      account_name: $("#imageAccount").value,
      base_url: $("#imageBaseUrl").value,
      api_key: $("#imageApiKey").value,
      mode: $("#imageMode").value,
      image_model: $("#imageModel").value,

    });
    $("#imageGenerationDialog").close();
    toast(response.message);
  } catch (error) {
    $("#imageGenerationError").textContent = error.message;
    $("#imageGenerationError").focus();
  } finally {
    busy = false;
    $("#saveImageGeneration").disabled = false;
    render();
  }
};
$("#syncLaunch").onclick = syncAndLaunchCodex;
$("#launchDialog").addEventListener("cancel", event => event.preventDefault());

async function initialize() {
  try {
    const result = await api("/api/state");
    state = result.data;
    render();
    const today = new Date();
    $("#usageDate").max = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    refreshUsage();
  } catch (error) {
    $("#activeTitle").textContent = "配置读取失败";
    $("#activeRoute").textContent = "请重新打开应用后再试";
    toast(error.message, true);
  } finally {
    $("#configLoading").hidden = true;
  }
}
initialize();
setInterval(async () => {
  if (busy || document.hidden) return;
  try {
    const previousAccount = state?.active_account;
    const previousState = JSON.stringify(state);
    const result = await api("/api/state");
    state = result.data;
    if (previousState !== JSON.stringify(state)) render();
    if (currentPage === "home") {
      if (previousAccount !== state.active_account) usage = null;
      if (usagePeriod === "today" || previousAccount !== state.active_account) await refreshUsage();
    }
  } catch (_) {}
}, 10000);

$("#parseConfig").onclick = async () => {
  const button = $("#parseConfig");
  button.disabled = true;
  $("#importResult").textContent = "正在识别…";
  try {
    let key = $("#importAuth").value.trim();
    if (key.startsWith("```")) key = key.split("\n").slice(1, -1).join("\n").trim();
    if (key.startsWith("{")) {
      let auth;
      try { auth = JSON.parse(key); } catch (_) { throw new Error("auth.json 格式不正确，请复制完整 JSON"); }
      if (typeof auth.OPENAI_API_KEY !== "string" || !auth.OPENAI_API_KEY.trim()) throw new Error("auth.json 中缺少 OPENAI_API_KEY；官方账号请使用授权登录");
      key = auth.OPENAI_API_KEY.trim();
    }
    if (key && (/\s/.test(key) || /你的|your.*key|API.?Key/i.test(key))) throw new Error("请填写真实 API Key，不要使用教程中的占位文字");
    const result = (await api("/api/accounts/parse-config", {config_text: $("#importConfig").value})).result;
    if (!$("#accountName").value.trim()) $("#accountName").value = result.name;
    $("#providerId").value = result.provider_id;
    $("#baseUrl").value = result.base_url;
    setDefaultModelOptions([], result.default_model);
    $("#effort").value = result.reasoning_effort;
    if (key) $("#apiKey").value = key;
    $("#importAuth").value = "";
    $("#importConfig").value = "";
    $("#configImport").open = false;
    toast("已填入，请检查后保存。" + (result.ignored_fields.length ? "其他全局配置未导入。" : ""));
    $("#accountName").focus();
  } catch (error) { $("#importResult").textContent = error.message; }
  finally { button.disabled = false; }
};
$("#accountDialog").addEventListener("close", () => {
  $("#importAuth").value = "";
  $("#importConfig").value = "";
  $("#apiKey").value = "";
});

const quotaCache = new Map();
const quotaPending = new Set();
function renderAccountQuota(account) {
  const official = isOfficialAccount(account);
  $("#accountQuota").hidden = !official;
  if (!official) return;
  const result = quotaCache.get(account.name);
  $("#refreshQuota").disabled = quotaPending.has(account.name);
  $("#quotaStatus").textContent = quotaPending.has(account.name) ? "正在向官方查询…" : result ? `${result.limits || result.usage ? "更新" : "查询"}于 ${new Date(result.fetched_at).toLocaleTimeString()} · ${result.limits || result.usage ? "官方数据" : "未获取到数据"}` : "点击刷新读取官方数据，不切换账号。";
  if (!result) { $("#quotaContent").innerHTML = '<div class="quota-unavailable quota-idle"><strong>查看这个账号的剩余额度</strong><p>读取 5 小时、每周使用进度，以及账号累计 Token。</p><small>点击右上方“刷新额度”，无需切换当前账号。</small></div>'; return; }
  if (!result.limits && !result.usage) {
    const errors = [...new Set(Object.values(result.errors || {}))];
    $("#quotaContent").innerHTML = `<div class="quota-unavailable"><strong>暂时无法读取官方用量</strong><p>${errors.map(escapeHtml).join("；") || "官方未返回数据，请重试。"}</p><small>查询成功后显示累计 Token、5 小时和每周剩余额度。</small></div>`;
    return;
  }
  const limits = result.limits || {};
  const snapshots = limits.rateLimitsByLimitId && Object.keys(limits.rateLimitsByLimitId).length ? Object.entries(limits.rateLimitsByLimitId) : [["Codex", limits.rateLimits || {}]];
  const lifetime = result.usage?.summary?.lifetimeTokens;
  let html = `<div class="quota-total"><span>账号累计 Token</span><strong title="${lifetime == null ? "官方未提供" : exactTokens(lifetime)}">${lifetime == null ? "—" : tokenNumber(lifetime)}</strong><small>官方累计统计，不是已扣订阅额度</small></div>`;
  for (const [id, snapshot] of (result.limits ? snapshots : [])) {
    html += `<div class="quota-heading"><strong>${escapeHtml(snapshot.limitName || id)}</strong><span>${escapeHtml(snapshot.planType || account.plan_type || "")}</span></div><div class="quota-windows">`;
    for (const key of ["primary", "secondary"]) {
      const window = snapshot[key];
      const minutes = window?.windowDurationMins;
      const label = minutes === 300 ? "5 小时额度" : minutes === 10080 ? "每周额度" : minutes ? `${minutes} 分钟额度` : key === "primary" ? "短周期额度（周期未提供）" : "长周期额度（周期未提供）";
      const known = typeof window?.usedPercent === "number";
      const used = known ? Math.min(100, Math.max(0, window.usedPercent)) : 0;
      html += `<div class="quota-window"><span>${label}</span><strong>${known ? `${(100-used).toFixed(0)}% <small>剩余</small>` : "未提供"}</strong>${known ? `<progress max="100" value="${used}" aria-label="${label}已使用比例"></progress><small>已用 ${used}%</small>` : ""}<small>${window?.resetsAt ? `${new Date(window.resetsAt*1000).toLocaleString()} 重置` : "重置时间未提供"}</small></div>`;
    }
    html += '</div>';
    const credits = snapshot.credits;
    if (credits) html += `<p class="quota-note">额外 credits：${credits.unlimited ? "不限额" : credits.balance != null ? escapeHtml(credits.balance) : credits.hasCredits ? "有余额（数值未提供）" : "无可用 credits"}</p>`;
  }
  if (limits.ordinaryUsageAllowed === false) html += '<p class="quota-error">官方当前不允许使用套餐内额度。</p>';
  html += [...new Set(Object.values(result.errors || {}))].map(error=>`<p class="quota-error">${escapeHtml(error)}</p>`).join("");
  $("#quotaContent").innerHTML = html;
}
async function refreshAccountQuota(account) {
  if (!isOfficialAccount(account) || quotaPending.has(account.name)) return;
  quotaPending.add(account.name); renderAccounts();
  try {
    const result = (await api(`/api/accounts/quota?name=${encodeURIComponent(account.name)}`)).result;
    quotaCache.set(account.name, result);
  } catch (error) {
    quotaCache.set(account.name, {fetched_at:new Date().toISOString(), errors:{request:error.message}});
  } finally { quotaPending.delete(account.name); renderAccounts(); }
}
$("#refreshQuota").onclick = () => refreshAccountQuota(selected());

function confirmAction(message, title = "确认操作", action = "确认继续") {
  const dialog = $("#confirmDialog");
  if (dialog.open) return Promise.resolve(false);
  $("#confirmTitle").textContent = title;
  $("#confirmMessage").textContent = message;
  $("#confirmAccept").textContent = action;
  const previous = document.activeElement;
  dialog.returnValue = "cancel";
  return new Promise(resolve => {
    dialog.addEventListener("close", () => {
      previous?.focus();
      resolve(dialog.returnValue === "accept");
    }, {once:true});
    dialog.showModal();
    $("#confirmCancel").focus();
  });
}

function accountQuotaSummary(account) {
  const result = quotaCache.get(account.name);
  const limits = result?.limits;
  const buckets = limits?.rateLimitsByLimitId;
  // Do not merge independent model quota buckets into a fictitious account total.
  const snapshot = buckets?.codex || limits?.rateLimits;
  const windows = [snapshot?.primary, snapshot?.secondary];
  const error = [...new Set(Object.values(result?.errors || {}))].join("；");
  const status = quotaPending.has(account.name) ? "查询中…" : error ? error : result ? `官方数据 · ${new Date(result.fetched_at).toLocaleTimeString()} 更新` : "尚未查询官方数据";
  const metric = (minutes, title) => {
    const window = windows.find(value => value?.windowDurationMins === minutes);
    const used = typeof window?.usedPercent === "number" ? Math.min(100,Math.max(0,window.usedPercent)) : null;
    return `<div class="row-usage-metric"><span>${title}</span><strong>${used == null ? "—" : `${used}%`}<small> 已用</small></strong>${used == null ? '<small>等待官方返回</small>' : `<small>剩余 ${(100-used).toFixed(0)}%${window.resetsAt ? ` · ${new Date(window.resetsAt*1000).toLocaleString("zh-CN",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})} 重置` : ""}</small>`}</div>`;
  };
  const total = result?.usage?.summary?.lifetimeTokens;
  return `<div class="row-usage">
    ${metric(300,"5 小时额度")}${metric(10080,"每周额度")}
    <div class="row-usage-metric"><span>累计消耗 Token</span><strong title="${total == null ? "未提供" : exactTokens(total)}">${total == null ? "—" : tokenNumber(total)}</strong><small>官方账号累计 · 非订阅扣费</small></div>
    <div class="row-usage-foot"><span>${escapeHtml(status)}</span><button class="text-button" type="button" data-row-refresh="${escapeHtml(account.name)}" ${quotaPending.has(account.name) ? "disabled" : ""}>刷新数据</button></div>
  </div>`;
}
