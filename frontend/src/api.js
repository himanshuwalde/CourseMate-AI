const BASE = import.meta.env.VITE_API_URL || "";

async function fail(r) {
  let msg = r.statusText || `HTTP ${r.status}`;
  try {
    const j = await r.json();
    const d = j.detail ?? j;
    msg = Array.isArray(d) ? d.map((x) => x.msg || JSON.stringify(x)).join("; ") : typeof d === "string" ? d : JSON.stringify(d);
  } catch {
    /* keep status text */
  }
  throw new Error(msg);
}

async function json(path, opts = {}) {
  const r = await fetch(BASE + path, opts);
  if (!r.ok) await fail(r);
  return r.json();
}

const post = (path, body) =>
  json(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const listDocuments = () => json("/api/documents");
export const deleteDocument = (id) => json(`/api/documents/${id}`, { method: "DELETE" });
export function uploadDocuments(files) {
  const fd = new FormData();
  [...files].forEach((f) => fd.append("files", f));
  return json("/api/documents", { method: "POST", body: fd });
}

export const getModels = () => json("/api/models");
export const setModel = (model) => post("/api/models/active", { model });

export function parseQuestionBank(file) {
  const fd = new FormData();
  fd.append("file", file);
  return json("/api/question-bank/parse", { method: "POST", body: fd });
}
export const startAnswering = (body) => post("/api/question-bank/answer", body);
export const getJob = (id) => json(`/api/jobs/${id}`);
export const regenerate = (jobId, qid, instructions) =>
  post(`/api/jobs/${jobId}/questions/${qid}/regenerate`, { instructions: instructions || null });
export const jobDownloadUrl = (jobId, format) => `${BASE}/api/jobs/${jobId}/download?format=${format}`;

export async function exportItems(title, format, items) {
  const r = await fetch(BASE + "/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, format, items }),
  });
  if (!r.ok) await fail(r);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${title.replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_") || "answers"}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** POST /api/chat and read the server-sent events as they arrive. */
export async function streamChat(body, h) {
  const r = await fetch(BASE + "/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) await fail(r);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  const dispatch = (raw) => {
    let event = "message";
    let data = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7).trim();
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (!data) return;
    const payload = JSON.parse(data);
    if (event === "sources") h.onSources?.(payload);
    else if (event === "token") h.onToken?.(payload.text);
    else if (event === "export_hint") h.onHint?.(payload.format);
    else if (event === "error") h.onError?.(payload.message);
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) !== -1) {
      dispatch(buf.slice(0, i));
      buf = buf.slice(i + 2);
    }
  }
}

export const stripCitations = (text) => text.replace(/\s*(?:\[\d+\])+/g, "").trim();

export function citedSources(content, sources = []) {
  const idx = new Set([...content.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1])));
  const used = sources.filter((s) => idx.has(s.index));
  const list = used.length ? used : sources;
  return [...new Set(list.map((s) => (s.page ? `${s.filename}, p.${s.page}` : s.filename)))];
}
