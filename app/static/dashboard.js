const state = { users: [], selectedUserId: null };

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error?.message || `Request failed: ${response.status}`);
  return body;
}

function notice(message, isError = false) {
  const element = document.querySelector("#notice");
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.remove("hidden");
  window.setTimeout(() => element.classList.add("hidden"), 4500);
}

function terms(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

function renderList(target, rows, kind) {
  const container = document.querySelector(target);
  container.replaceChildren();
  if (!rows.length) {
    container.className = "empty-state";
    container.textContent = kind === "run" ? "还没有运行记录。" : "还没有生成简报。";
    return;
  }
  container.className = "list";
  rows.forEach((row) => {
    const link = document.createElement("a");
    link.className = "list-item";
    link.href = kind === "run" ? `/runs/${row.id}/view` : `/digests/${row.id}/view`;
    const text = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = kind === "run" ? `运行 ${row.id.slice(0, 8)}` : row.title;
    const date = document.createElement("small");
    date.textContent = formatDate(row.created_at);
    text.append(title, date);
    const badge = document.createElement("span");
    badge.className = `badge ${row.status}`;
    badge.textContent = row.status;
    link.append(text, badge);
    container.append(link);
  });
}

async function loadUsers(selectId = null) {
  state.users = await api("/api/users");
  const select = document.querySelector("#user-select");
  select.replaceChildren(new Option("选择用户", ""));
  state.users.forEach((user) => select.add(new Option(user.identity.slice(0, 35), user.id)));
  const queryUser = new URLSearchParams(location.search).get("user_id");
  const preferred = selectId || queryUser || localStorage.getItem("dailyBriefUser");
  if (preferred && state.users.some((user) => user.id === preferred)) {
    select.value = preferred;
    await selectUser(preferred);
  }
}

async function selectUser(userId) {
  state.selectedUserId = userId || null;
  document.querySelector("#run-button").disabled = !userId;
  document.querySelector("#subscription-form").querySelectorAll("input,button").forEach((node) => { node.disabled = !userId; });
  if (!userId) return;
  localStorage.setItem("dailyBriefUser", userId);
  history.replaceState({}, "", `/?user_id=${encodeURIComponent(userId)}`);
  const selectedUser = state.users.find((user) => user.id === userId);

  const form = document.querySelector("#subscription-form");
  try {
    const subscription = await api(`/api/users/${userId}/subscription`);
    form.topics.value = subscription.topics.join(", ");
    form.keywords.value = subscription.keywords.join(", ");
    form.excluded_keywords.value = subscription.excluded_keywords.join(", ");
    form.delivery_time.value = subscription.delivery_time.slice(0, 5);
    form.enabled.checked = subscription.enabled;
    document.querySelector("#schedule-badge").textContent = subscription.enabled ? `每天 ${subscription.delivery_time.slice(0, 5)} · ${selectedUser.timezone}` : "已停用";
  } catch (_) {
    form.reset();
    form.delivery_time.value = "09:00";
    form.enabled.checked = true;
    document.querySelector("#schedule-badge").textContent = "尚未配置";
  }
  const [runs, digests] = await Promise.all([
    api(`/api/users/${userId}/runs`),
    api(`/api/users/${userId}/digests`),
  ]);
  renderList("#runs-list", runs.slice(0, 8), "run");
  renderList("#digests-list", digests.slice(0, 8), "digest");
}

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelector("#run-button").disabled = true;
  document.querySelector("#subscription-form").querySelectorAll("input,button").forEach((node) => { node.disabled = true; });
  try { await loadUsers(); } catch (error) { notice(error.message, true); }

  document.querySelector("#user-select").addEventListener("change", (event) => {
    selectUser(event.target.value).catch((error) => notice(error.message, true));
  });

  document.querySelector("#user-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const user = await api("/api/users", {
        method: "POST",
        body: JSON.stringify({ identity: data.get("identity"), email: data.get("email"), timezone: data.get("timezone") }),
      });
      event.currentTarget.reset();
      event.currentTarget.timezone.value = "Asia/Shanghai";
      await loadUsers(user.id);
      notice("用户创建成功，请继续设置订阅偏好。");
    } catch (error) { notice(error.message, true); }
  });

  document.querySelector("#subscription-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selectedUserId) return;
    const data = new FormData(event.currentTarget);
    try {
      await api(`/api/users/${state.selectedUserId}/subscription`, {
        method: "PUT",
        body: JSON.stringify({
          topics: terms(data.get("topics")),
          keywords: terms(data.get("keywords")),
          excluded_keywords: terms(data.get("excluded_keywords")),
          delivery_time: `${data.get("delivery_time")}:00`,
          enabled: data.get("enabled") === "on",
        }),
      });
      await selectUser(state.selectedUserId);
      notice("订阅已保存，定时任务已同步。");
    } catch (error) { notice(error.message, true); }
  });

  document.querySelector("#run-button").addEventListener("click", async () => {
    if (!state.selectedUserId) return;
    const button = document.querySelector("#run-button");
    button.disabled = true;
    try {
      const run = await api(`/api/users/${state.selectedUserId}/digest-runs`, { method: "POST" });
      location.href = `/runs/${run.id}/view`;
    } catch (error) {
      notice(error.message, true);
      button.disabled = false;
    }
  });
});
