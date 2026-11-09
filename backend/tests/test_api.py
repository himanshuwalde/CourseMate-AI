import json
import time
from io import BytesIO

from docx import Document
from reportlab.pdfgen import canvas


def make_pdf(lines_per_page):
    buf = BytesIO()
    c = canvas.Canvas(buf)
    for lines in lines_per_page:
        y = 800
        for line in lines:
            c.drawString(50, y, line)
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


def wait_ready(client, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        docs = client.get("/api/documents").json()
        if docs and all(d["status"] != "processing" for d in docs):
            return docs
        time.sleep(0.2)
    raise AssertionError("ingestion timed out")


def upload_notes(client):
    pdf = make_pdf([
        ["Dropout is a regularization technique.", "It randomly disables neurons during training.", "This reduces overfitting."],
        ["Batch normalization normalizes layer inputs.", "It speeds up training and stabilizes gradients."],
    ])
    r = client.post("/api/documents", files=[("files", ("notes.pdf", pdf, "application/pdf"))])
    assert r.status_code == 202
    return wait_ready(client)


def test_models_and_switching(client):
    info = client.get("/api/models").json()
    assert "llama3.1:8b" in info["available"]
    assert client.post("/api/models/active", json={"model": "llama3.1:8b"}).json()["active"] == "llama3.1:8b"
    assert client.get("/api/models").json()["active"] == "llama3.1:8b"
    assert client.post("/api/models/active", json={"model": "nope:1b"}).status_code == 400
    client.post("/api/models/active", json={"model": "llama3.2:3b"})


def test_upload_validation(client):
    r = client.post("/api/documents", files=[("files", ("x.exe", b"abc", "application/octet-stream"))])
    assert r.status_code == 400
    assert client.post("/api/chat", json={"question": "hi"}).status_code in (200, 400)


def test_full_flow(client):
    docs = upload_notes(client)
    assert docs[0]["status"] == "ready" and docs[0]["pages"] == 2 and docs[0]["chunks"] >= 2

    # ---- chat (SSE) ----
    r = client.post("/api/chat", json={"question": "What is dropout? give me a pdf", "history": []})
    assert r.status_code == 200
    events = [e for e in r.text.split("\n\n") if e.strip()]
    names = [e.split("\n")[0].replace("event: ", "") for e in events]
    assert names[0] == "sources" and "token" in names and "export_hint" in names and names[-1] == "done"
    sources = json.loads(events[0].split("data: ", 1)[1])
    assert sources[0]["filename"] == "notes.pdf" and sources[0]["page"] == 1

    # ---- follow-up with history uses the rewrite path ----
    r = client.post("/api/chat", json={"question": "explain more", "history": [
        {"role": "user", "content": "What is dropout?"}, {"role": "assistant", "content": "A technique."}]})
    assert "event: done" in r.text

    # ---- question bank: build a DOCX question bank, parse it ----
    qb = Document()
    qb.add_paragraph("1. What is dropout? (5 marks)")
    qb.add_paragraph("2. What does batch normalization do? [2M]")
    qb.add_paragraph("3. Explain zzzunknown topic.")
    buf = BytesIO()
    qb.save(buf)
    parsed = client.post("/api/question-bank/parse", files={"file": ("qb.docx", buf.getvalue(), "application/octet-stream")}).json()
    assert len(parsed["questions"]) == 3 and parsed["questions"][0]["marks"] == 5

    # ---- answer job ----
    job = client.post("/api/question-bank/answer", json={
        "questions": parsed["questions"], "style": "exam", "allow_general_knowledge": True, "title": "DL answers"}).json()
    for _ in range(100):
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["status"] in {"done", "failed"}:
            break
        time.sleep(0.2)
    assert state["status"] == "done", state
    statuses = [r["status"] for r in state["results"]]
    assert statuses == ["done", "done", "general"], statuses
    assert state["results"][0]["sources"] and "[1]" not in state["results"][0]["answer"]

    # ---- regenerate one answer, then download in all formats ----
    r = client.post(f"/api/jobs/{job['id']}/questions/1/regenerate", json={"instructions": "shorter"})
    assert r.status_code == 200 and r.json()["status"] == "done"
    for fmt, magic in (("docx", b"PK"), ("pdf", b"%PDF"), ("md", b"# DL answers")):
        d = client.get(f"/api/jobs/{job['id']}/download", params={"format": fmt})
        assert d.status_code == 200 and d.content.startswith(magic), fmt
    assert client.get(f"/api/jobs/{job['id']}/download", params={"format": "exe"}).status_code == 400

    # ---- chat export ----
    e = client.post("/api/export", json={"title": "Chat", "format": "pdf", "items": [{"question": "Q?", "answer": "A."}]})
    assert e.content.startswith(b"%PDF")

    # ---- strict mode: not-found without general knowledge ----
    job2 = client.post("/api/question-bank/answer", json={"questions": [{"text": "Explain zzzunknown topic."}]}).json()
    for _ in range(100):
        s2 = client.get(f"/api/jobs/{job2['id']}").json()
        if s2["status"] != "running" and s2["status"] != "queued":
            break
        time.sleep(0.2)
    assert s2["results"][0]["status"] == "not_found"

    # ---- delete ----
    assert client.delete(f"/api/documents/{docs[0]['id']}").status_code == 200
    assert client.get("/api/documents").json() == []
