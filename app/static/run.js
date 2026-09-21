const runId = document.querySelector("#run-id").dataset.value;
let pollTimer = null;

async function getJSON(path) {
  const response = await fetch(path);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || "请求失败");
  return body;
}

function metric(label, value) {
  const item = document.createElement("div");
  item.className = "metric";
  const caption = document.createElement("span");
  caption.textContent = label;
  const number = document.createElement("strong");
  number.textContent = value;
  item.append(caption, number);
  return item;
}

function renderTrace(calls) {
  const target = document.querySelector("#trace-list");
  target.replaceChildren();
  if (!calls.length) { target.className = "empty-state"; target.textContent = "Agent 尚未调用工具。"; return; }
  target.className = "trace";
  calls.forEach((call) => {
    const item = document.createElement("div");
    item.className = `trace-item ${call.success ? "" : "failed"}`;
    const head = document.createElement("div");
    head.className = "trace-head";
    const title = document.createElement("strong");
    title.textContent = `${call.sequence}. ${call.tool_name}`;
    const latency = document.createElement("small");
    latency.textContent = `${call.duration_ms.toFixed(1)} ms · turn ${call.turn}`;
    head.append(title, latency);
    const detail = document.createElement("pre");
    detail.textContent = `arguments\n${JSON.stringify(call.arguments, null, 2)}\n\nresult\n${call.result_preview || call.error_message || "—"}`;
    item.append(head, detail);
    target.append(item);
  });
}

async function refresh() {
  try {
    const [run, calls] = await Promise.all([getJSON(`/api/runs/${runId}`), getJSON(`/api/runs/${runId}/tool-calls`)]);
    document.querySelector("#run-title").textContent = `运行 ${run.id.slice(0, 8)}`;
    const status = document.querySelector("#run-status");
    status.textContent = run.status;
    status.className = `badge ${run.status}`;
    const metrics = document.querySelector("#run-metrics");
    metrics.replaceChildren(metric("Turns", run.turn_count), metric("Tool calls", run.tool_call_count), metric("Input tokens", run.input_tokens), metric("Output tokens", run.output_tokens));
    renderTrace(calls);
    if (run.error_message) {
      const error = document.querySelector("#run-error");
      error.textContent = `${run.error_code}: ${run.error_message}`;
      error.classList.remove("hidden");
    }
    if (["completed", "failed"].includes(run.status)) {
      window.clearInterval(pollTimer);
      if (run.digest_id) {
        const link = document.createElement("a");
        link.className = "button primary";
        link.href = `/digests/${run.digest_id}/view`;
        link.textContent = "查看生成的简报";
        document.querySelector(".detail-header").append(link);
      }
    }
  } catch (error) {
    const panel = document.querySelector("#run-error");
    panel.textContent = error.message;
    panel.classList.remove("hidden");
    window.clearInterval(pollTimer);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  refresh();
  pollTimer = window.setInterval(refresh, 2000);
});

