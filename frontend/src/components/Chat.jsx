import React, { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import Prose from "./Prose.jsx";

const FORMATS = [
  ["pdf", "PDF"],
  ["docx", "Word"],
  ["md", "Markdown"],
];

const SUGGESTIONS = [
  "Summarize the main ideas in these documents.",
  "List the key definitions with page references.",
  "What are the most likely exam questions from this material?",
];

function ExportRow({ msg, onExport, hint }) {
  return (
    <div className="exports">
      <span className="hint">{hint ? `You asked for ${hint.toUpperCase()}:` : "Save as"}</span>
      {FORMATS.map(([f, label]) => (
        <button key={f} className={`btn small ${hint === f ? "primary" : ""}`} onClick={() => onExport(f)}>
          {label}
        </button>
      ))}
    </div>
  );
}

export default function Chat({ docIds }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function send(text) {
    const question = text.trim();
    if (!question || busy) return;
    const history = messages.filter((m) => !m.error && m.content).slice(-6).map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: "user", content: question }, { role: "assistant", content: "", sources: [], question, pending: true }]);
    setInput("");
    setBusy(true);
    const update = (fn) =>
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = fn(copy[copy.length - 1]);
        return copy;
      });
    try {
      await api.streamChat(
        { question, history, doc_ids: docIds },
        {
          onSources: (sources) => update((b) => ({ ...b, sources })),
          onToken: (t) => update((b) => ({ ...b, content: b.content + t })),
          onHint: (hint) => update((b) => ({ ...b, hint })),
          onError: (error) => update((b) => ({ ...b, error })),
        }
      );
    } catch (e) {
      update((b) => ({ ...b, error: e.message }));
    } finally {
      update((b) => ({ ...b, pending: false }));
      setBusy(false);
    }
  }

  async function exportMessages(items, format, title) {
    setNote("");
    try {
      await api.exportItems(title, format, items);
    } catch (e) {
      setNote(e.message);
    }
  }

  const toItem = (m) => ({
    question: m.question,
    answer: api.stripCitations(m.content),
    sources: api.citedSources(m.content, m.sources),
  });
  const answered = messages.filter((m) => m.role === "assistant" && m.content && !m.error && !m.pending);
  const noDocs = docIds.length === 0;

  return (
    <div className="chat">
      {messages.length === 0 ? (
        <div className="intro">
          <h2>Ask your documents</h2>
          <p>
            {noDocs
              ? "Add and tick at least one document on the left to start."
              : "Answers come only from the documents you ticked, with page references. Add “as a PDF” or “in Word” to a question and the export buttons will be ready."}
          </p>
          {!noDocs && (
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="thread">
          {answered.length > 1 && (
            <div className="exports top">
              <span className="hint">Whole conversation</span>
              {FORMATS.map(([f, label]) => (
                <button key={f} className="btn small" onClick={() => exportMessages(answered.map(toItem), f, "Chat answers")}>
                  {label}
                </button>
              ))}
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="msg user">
                {m.content}
              </div>
            ) : (
              <div key={i} className="msg bot">
                {m.content ? <Prose text={m.content} sources={m.sources} /> : m.pending && !m.error && <p className="hint">Searching the documents…</p>}
                {m.pending && m.content && <span className="caret" />}
                {m.error && <p className="alert">{m.error}</p>}
                {!m.pending && m.sources?.length > 0 && m.content && (
                  <details className="sources">
                    <summary>{m.sources.length} passages used</summary>
                    <ol>
                      {m.sources.map((s) => (
                        <li key={s.index}>
                          <strong>
                            {s.filename}
                            {s.page ? `, p.${s.page}` : ""}
                          </strong>
                          <span>{s.snippet}…</span>
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
                {!m.pending && m.content && !m.error && (
                  <ExportRow msg={m} hint={m.hint} onExport={(f) => exportMessages([toItem(m)], f, m.question.slice(0, 50))} />
                )}
              </div>
            )
          )}
          <div ref={endRef} />
        </div>
      )}

      {note && <p className="alert">{note}</p>}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          rows={2}
          placeholder={noDocs ? "Tick a document first…" : "Ask a question…"}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
        />
        <button className="btn primary" disabled={busy || noDocs || !input.trim()}>
          {busy ? "Answering…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
