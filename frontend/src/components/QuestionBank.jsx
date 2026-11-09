import React, { useEffect, useRef, useState } from "react";
import * as api from "../api.js";
import Prose from "./Prose.jsx";

const STYLES = [
  ["exam", "Exam style (intro, key points, conclusion)"],
  ["detailed", "Detailed"],
  ["short", "Short (2–4 sentences)"],
];

const STATUS = {
  pending: "Waiting",
  running: "Answering…",
  done: "From your documents",
  general: "General knowledge",
  not_found: "Not in documents",
  error: "Failed",
};

let keyCounter = 0;
const withKey = (q) => ({ ...q, key: ++keyCounter });

export default function QuestionBank({ docIds }) {
  const [fileName, setFileName] = useState("");
  const [questions, setQuestions] = useState([]);
  const [parsing, setParsing] = useState(false);
  const [style, setStyle] = useState("exam");
  const [instructions, setInstructions] = useState("");
  const [allowGeneral, setAllowGeneral] = useState(false);
  const [title, setTitle] = useState("Question bank answers");
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const running = job && (job.status === "queued" || job.status === "running");

  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(async () => {
      try {
        const fresh = await api.getJob(job.id);
        // keep rows that are being regenerated locally from flickering back
        setJob(fresh);
      } catch (e) {
        setError(e.message);
      }
    }, 1500);
    return () => clearInterval(t);
  }, [running, job?.id]);

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setParsing(true);
    setJob(null);
    try {
      const res = await api.parseQuestionBank(file);
      setQuestions(res.questions.map(withKey));
      setFileName(res.filename);
      setTitle(res.filename.replace(/\.[^.]+$/, "") + " answers");
    } catch (err) {
      setError(err.message);
    } finally {
      setParsing(false);
      e.target.value = "";
    }
  }

  const edit = (key, patch) => setQuestions((qs) => qs.map((q) => (q.key === key ? { ...q, ...patch } : q)));
  const remove = (key) => setQuestions((qs) => qs.filter((q) => q.key !== key));
  const add = () => setQuestions((qs) => [...qs, withKey({ number: String(qs.length + 1), text: "", marks: null })]);

  async function generate() {
    setError("");
    try {
      const payload = questions
        .filter((q) => q.text.trim().length > 1)
        .map(({ number, text, marks }) => ({ number, text, marks: marks || null }));
      setJob(
        await api.startAnswering({
          questions: payload,
          doc_ids: docIds,
          style,
          instructions,
          allow_general_knowledge: allowGeneral,
          title,
        })
      );
    } catch (err) {
      setError(err.message);
    }
  }

  async function redo(r) {
    setJob((j) => ({ ...j, results: j.results.map((x) => (x.id === r.id ? { ...x, status: "running" } : x)) }));
    try {
      const fresh = await api.regenerate(job.id, r.id);
      setJob((j) => ({ ...j, results: j.results.map((x) => (x.id === r.id ? fresh : x)) }));
    } catch (err) {
      setError(err.message);
    }
  }

  function reset() {
    setJob(null);
    setQuestions([]);
    setFileName("");
    setError("");
  }

  const noDocs = docIds.length === 0;
  const pct = job ? Math.round((job.done_count / Math.max(job.total, 1)) * 100) : 0;

  return (
    <div className="qb">
      {!job && (
        <>
          <div className="intro left">
            <h2>Answer a whole question bank</h2>
            <p>
              Tick your study documents on the left, upload a question bank (PDF, Word or text), check the questions we found, and get
              every answer in one PDF or Word file.
            </p>
          </div>

          <div className="row">
            <button className="btn primary" onClick={() => fileRef.current?.click()} disabled={parsing}>
              {parsing ? "Reading questions…" : questions.length ? "Upload a different file" : "Upload question bank"}
            </button>
            <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.txt,.md" onChange={onFile} />
            {fileName && <span className="hint">{fileName}</span>}
          </div>

          {questions.length > 0 && (
            <>
              <h3 className="sub">{questions.length} questions found</h3>
              <ol className="qlist">
                {questions.map((q) => (
                  <li key={q.key}>
                    <textarea
                      aria-label="Question text"
                      value={q.text}
                      rows={Math.min(5, Math.max(2, Math.ceil(q.text.length / 90)))}
                      onChange={(e) => edit(q.key, { text: e.target.value })}
                    />
                    <div className="qside">
                      <label className="marks">
                        Marks
                        <input
                          type="number"
                          min="1"
                          max="100"
                          value={q.marks ?? ""}
                          onChange={(e) => edit(q.key, { marks: e.target.value ? Number(e.target.value) : null })}
                        />
                      </label>
                      <button className="icon" aria-label="Remove question" title="Remove" onClick={() => remove(q.key)}>
                        ×
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
              <button className="btn small" onClick={add}>
                Add a question
              </button>

              <div className="options">
                <label>
                  <span className="label">Answer style</span>
                  <select value={style} onChange={(e) => setStyle(e.target.value)}>
                    {STYLES.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="label">Extra instructions (optional)</span>
                  <input
                    type="text"
                    value={instructions}
                    maxLength={500}
                    placeholder="e.g. keep each answer under 150 words"
                    onChange={(e) => setInstructions(e.target.value)}
                  />
                </label>
                <label>
                  <span className="label">Document title</span>
                  <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
                </label>
                <label className="check">
                  <input type="checkbox" checked={allowGeneral} onChange={(e) => setAllowGeneral(e.target.checked)} />
                  <span>If the documents don't cover a question, answer from general knowledge (clearly marked)</span>
                </label>
              </div>

              <button className="btn primary" onClick={generate} disabled={noDocs || !questions.some((q) => q.text.trim())}>
                {noDocs ? "Tick a document first" : "Generate answers"}
              </button>
            </>
          )}
        </>
      )}

      {error && <p className="alert">{error}</p>}

      {job && (
        <>
          <div className="jobhead">
            <div>
              <h2>{job.title}</h2>
              <p className="hint">
                {running ? `Answering ${job.done_count} of ${job.total}…` : job.status === "failed" ? "Stopped" : `${job.total} questions answered`}
              </p>
            </div>
            <button className="btn small" onClick={reset} disabled={running}>
              Start over
            </button>
          </div>

          <div className="bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${pct}%` }} />
          </div>

          {job.status === "failed" && job.error && <p className="alert">{job.error}</p>}

          <div className="exports">
            <span className="hint">Download</span>
            {[["pdf", "PDF"], ["docx", "Word"], ["md", "Markdown"]].map(([f, l]) => (
              <a key={f} className={`btn small ${running || job.done_count === 0 ? "disabled" : "primary"}`} href={running ? undefined : api.jobDownloadUrl(job.id, f)}>
                {l}
              </a>
            ))}
          </div>

          <ol className="results">
            {job.results.map((r) => (
              <li key={r.id} className={`result ${r.status}`}>
                <details open={r.status !== "pending"}>
                  <summary>
                    <span className="qtext">
                      {r.question}
                      {r.marks ? <em className="mk"> [{r.marks} marks]</em> : null}
                    </span>
                    <span className={`badge ${r.status}`}>{STATUS[r.status] || r.status}</span>
                  </summary>
                  {r.answer && <Prose text={r.answer} />}
                  {r.note && <p className={r.status === "error" ? "alert" : "hint warn"}>{r.note}</p>}
                  {r.sources?.length > 0 && <p className="hint">Sources: {r.sources.join("; ")}</p>}
                  {!["pending", "running"].includes(r.status) && (
                    <button className="btn small" onClick={() => redo(r)} disabled={running}>
                      Regenerate
                    </button>
                  )}
                </details>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
