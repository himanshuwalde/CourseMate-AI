import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api.js";
import Sidebar from "./components/Sidebar.jsx";
import Chat from "./components/Chat.jsx";
import QuestionBank from "./components/QuestionBank.jsx";

export default function App() {
  const [tab, setTab] = useState("chat");
  const [docs, setDocs] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [models, setModels] = useState(null);
  const [backendDown, setBackendDown] = useState(false);
  const seenReady = useRef(new Set());

  const loadDocs = useCallback(async () => {
    try {
      const list = await api.listDocuments();
      setBackendDown(false);
      setDocs(list);
      setSelected((prev) => {
        const next = new Set([...prev].filter((id) => list.some((d) => d.id === id)));
        list.forEach((d) => {
          if (d.status === "ready" && !seenReady.current.has(d.id)) {
            seenReady.current.add(d.id); // newly ready documents are ticked automatically
            next.add(d.id);
          }
        });
        return next;
      });
    } catch {
      setBackendDown(true);
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      setModels(await api.getModels());
    } catch {
      setModels(null);
    }
  }, []);

  useEffect(() => {
    loadDocs();
    loadModels();
  }, [loadDocs, loadModels]);

  useEffect(() => {
    if (!docs.some((d) => d.status === "processing")) return undefined;
    const t = setInterval(loadDocs, 1500);
    return () => clearInterval(t);
  }, [docs, loadDocs]);

  const activeIds = useMemo(() => docs.filter((d) => d.status === "ready" && selected.has(d.id)).map((d) => d.id), [docs, selected]);

  return (
    <div className="app">
      <Sidebar
        docs={docs}
        selected={selected}
        setSelected={setSelected}
        reloadDocs={loadDocs}
        models={models}
        reloadModels={loadModels}
        backendDown={backendDown}
      />
      <main className="main">
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "chat"} className={tab === "chat" ? "tab on" : "tab"} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button role="tab" aria-selected={tab === "qb"} className={tab === "qb" ? "tab on" : "tab"} onClick={() => setTab("qb")}>
            Question bank
          </button>
        </nav>
        {/* both panels stay mounted so a running job or a chat is not lost when switching tabs */}
        <section hidden={tab !== "chat"}>
          <Chat docIds={activeIds} />
        </section>
        <section hidden={tab !== "qb"}>
          <QuestionBank docIds={activeIds} />
        </section>
      </main>
    </div>
  );
}
