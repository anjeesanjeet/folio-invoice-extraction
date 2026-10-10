"""FastAPI service: upload and review documents, exports, dashboard and flowchart APIs.

Run:  python -m app.main     then open http://127.0.0.1:8200
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import ROOT_DIR, get_settings
from app.db import connect, to_dict
from app.exporter import export
from app.flowchart import latest_doc_id, pipeline_mermaid, trace_mermaid
from app.ingest import IMAGE_EXT
from app.llm import ProviderConfigError, get_provider
from app.pipeline import Pipeline

STATIC = ROOT_DIR / "static"
settings = get_settings()
app = FastAPI(title="Folio: invoice extraction with checks", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@lru_cache(maxsize=1)
def provider():
    return get_provider(settings)


def pipeline(need_model: bool = True) -> Pipeline:
    try:
        return Pipeline(settings, provider() if need_model else None)
    except ProviderConfigError as exc:
        if need_model:
            raise HTTPException(400, str(exc))
        return Pipeline(settings, None)


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/review")


for _p in ("review", "dashboard", "flowchart"):
    def _mk(name=_p):
        return lambda: FileResponse(STATIC / f"{name}.html")
    app.get(f"/{_p}", include_in_schema=False)(_mk())


@app.post("/api/documents")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXT | {".pdf"}:
        raise HTTPException(400, "Upload a PDF, PNG, JPG, WEBP or TIFF file.")
    p = pipeline()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
    try:
        doc_id = p.add(Path(tmp.name), file.filename)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return p.process(doc_id)


@app.get("/api/documents")
def list_docs():
    conn = connect(settings.db_path)
    try:
        rows = [to_dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY id DESC")]
    finally:
        conn.close()
    out = []
    for d in rows:
        ext, val = d.get("extracted") or {}, d.get("validation") or {}
        v = lambda f: (ext.get(f) or {}).get("value") if isinstance(ext.get(f), dict) else None
        out.append({"id": d["id"], "filename": d["filename"], "status": d["status"], "kind": d["kind"],
                    "vendor": v("vendor"), "total": v("total"), "currency": v("currency"),
                    "flagged": sum(1 for x in (val.get("fields") or {}).values() if x["status"] != "ok")})
    return out


@app.get("/api/documents/{doc_id}")
def get_one(doc_id: int):
    conn = connect(settings.db_path)
    try:
        if not conn.execute("SELECT 1 FROM documents WHERE id = ?", (doc_id,)).fetchone():
            raise HTTPException(404, "Document not found")
        return Pipeline.summary(conn, doc_id)
    finally:
        conn.close()


@app.get("/api/documents/{doc_id}/page/{n}")
def page(doc_id: int, n: int = 1):
    path = pipeline(False).page_path(doc_id, n)
    if not path.exists():
        raise HTTPException(404, "Page image not found")
    return FileResponse(path, media_type="image/png")


@app.post("/api/documents/{doc_id}/reprocess")
def reprocess(doc_id: int):
    try:
        return pipeline().process(doc_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class ReviewIn(BaseModel):
    decision: str
    corrections: dict | None = None


@app.post("/api/documents/{doc_id}/review")
def review(doc_id: int, body: ReviewIn):
    try:
        return pipeline(False).review(doc_id, body.decision, body.corrections)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/export/{fmt}")
def download(fmt: str, include_unreviewed: bool = False):
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(400, "Format must be csv or xlsx")
    csv_path, xlsx_path = export(settings.db_path, settings.outputs_dir, include_unreviewed)
    return FileResponse(csv_path if fmt == "csv" else xlsx_path, filename=f"invoices.{fmt}")


@app.get("/api/dashboard")
def dashboard():
    conn = connect(settings.db_path)
    try:
        docs = [dict(r) for r in conn.execute("SELECT status, kind, cost_usd, duration_ms FROM documents")]
    finally:
        conn.close()
    done = [d for d in docs if d["status"] not in ("new", "processing")]
    ev, st = settings.eval_results_path, settings.outputs_dir / "stress_results.json"
    stress = json.loads(st.read_text(encoding="utf-8")) if st.exists() else None
    if stress:
        stress.pop("rows", None)
    return {"provider": settings.llm_provider, "model": settings.model_name,
            "eval": json.loads(ev.read_text(encoding="utf-8")) if ev.exists() else None, "stress": stress,
            "live": {"documents": len(done), "status": dict(Counter(d["status"] for d in done)),
                     "kinds": dict(Counter(d["kind"] or "unknown" for d in done)),
                     "cost_per_doc_usd": round(sum(d["cost_usd"] for d in done) / len(done), 5) if done else None,
                     "duration_avg_ms": round(sum(d["duration_ms"] for d in done) / len(done), 1) if done else None}}


@app.get("/api/flowchart")
def flowchart(view: str = "pipeline", doc_id: int | None = None):
    if view == "pipeline":
        return {"view": view, "mermaid": pipeline_mermaid(settings)}
    if view == "trace":
        did = doc_id or latest_doc_id(settings)
        return {"view": view, "doc_id": did, "mermaid": trace_mermaid(settings, did) if did else None}
    raise HTTPException(400, "view must be pipeline or trace")


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": settings.llm_provider, "model": settings.model_name}


def run() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
