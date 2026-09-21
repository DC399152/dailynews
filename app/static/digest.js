const digestId = document.querySelector("#digest-id").dataset.value;

document.addEventListener("DOMContentLoaded", async () => {
  const response = await fetch(`/api/digests/${digestId}`);
  const digest = await response.json();
  if (!response.ok) {
    document.querySelector("#digest-content").textContent = digest.error?.message || "简报加载失败";
    return;
  }
  document.querySelector("#digest-title").textContent = digest.title;
  document.querySelector("#digest-content").textContent = digest.content;
  const status = document.querySelector("#digest-status");
  status.textContent = digest.status;
  status.className = `badge ${digest.status}`;
  const sources = document.querySelector("#source-list");
  sources.replaceChildren();
  if (!digest.sources.length) { sources.className = "empty-state"; sources.textContent = "这份简报没有保存来源链接。"; return; }
  digest.sources.forEach((source) => {
    const link = document.createElement("a");
    link.className = "source-link";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = source.title || source.url;
    sources.append(link);
  });
});

