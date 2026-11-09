import React, { useRef, useState } from "react";
import * as api from "../api.js";

const fmtSize = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);

export default function Sidebar({ docs, selected, setSelected, reloadDocs, models, reloadModels, backendDown }) {
  const fileRef = useRef(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);

  async function onFiles(e) {
    const files = e.target.files;
    if (!files?.length) return;
    setError("");
    setUploading(true);
    try {
      await api.uploadDocuments(files);
      await reloadDocs();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function remove(id) {
    try {
      await api.deleteDocument(id);
      await reloadDocs();
    } catch (err) {
      setError(err.message);
    }
  }

  async function changeModel(e) {
    setError("");
    try {
      await api.setModel(e.target.value);
      await reloadModels();
    } catch (err) {
      setError(err.message);
    }
  }

  const toggle = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const options = models ? [...new Set([models.active, ...models.available])] : [];

  return (
    <aside className="side">
      <h1 className="brand">RAG Studio</h1>

      {backendDown && (
        <p className="alert">
          Can't reach the backend. Start it with <code>uvicorn app.main:app --reload</code> in the backend folder.
        </p>
      )}

      <section className="block">
        <label className="label" htmlFor="model">
          Language model
        </label>
        {models ? (
          <>
            <select id="model" value={models.active} onChange={changeModel} disabled={!models.available.length}>
              {options.map((m) => (
                <option key={m} value={m}>
                  {m}
                  {models.available.includes(m) ? "" : " (not installed)"}
                </option>
              ))}
            </select>
            {!models.ollama_ok ? (
              <p className="hint warn">Ollama isn't running. Start it with <code>ollama serve</code>.</p>
            ) : (
              <p className="hint">
                Want a stronger model? <code>ollama pull llama3.1:8b</code>, then pick it here.
              </p>
            )}
            <p className="hint">Embeddings: {models.embedding_model}</p>
          </>
        ) : (
          <p className="hint">Model info unavailable.</p>
        )}
      </section>

      <section className="block grow">
        <div className="row between">
          <span className="label">Documents</span>
          <button className="btn small" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Uploading…" : "Add files"}
          </button>
          <input ref={fileRef} type="file" multiple hidden accept=".pdf,.docx,.txt,.md" onChange={onFiles} />
        </div>

        {error && <p className="alert">{error}</p>}

        {docs.length === 0 ? (
          <p className="empty">Add PDFs, Word files or text notes. Answers will come only from the ones you tick.</p>
        ) : (
          <ul className="docs">
            {docs.map((d) => (
              <li key={d.id} className={`doc ${d.status}`}>
                <label className="doc-main">
                  <input type="checkbox" disabled={d.status !== "ready"} checked={selected.has(d.id)} onChange={() => toggle(d.id)} />
                  <span className="doc-text">
                    <span className="doc-name" title={d.filename}>
                      {d.filename}
                    </span>
                    <span className="doc-meta">
                      {d.status === "ready" && `${d.pages} ${d.pages === 1 ? "page" : "pages"} · ${d.chunks} passages · ${fmtSize(d.size)}`}
                      {d.status === "processing" && "Reading and indexing…"}
                      {d.status === "failed" && <span className="bad">{d.error || "Failed to process"}</span>}
                    </span>
                  </span>
                </label>
                <button className="icon" aria-label={`Remove ${d.filename}`} title="Remove" onClick={() => remove(d.id)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
