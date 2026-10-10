"""Exports portfolio assets in one command (starts its own temporary server):

    outputs/thumbnail.png          1600x1200 Contra cover (from /dashboard?mode=thumbnail)
    outputs/dashboard_full.png     full results page
    outputs/review_page.png        review page showing a flagged document
    outputs/flowchart_pipeline.png pipeline and checks (generated from the code)
    outputs/flowchart_trace.png    step-by-step trace of one document
    docs/architecture.md           Mermaid source for GitHub

Setup once:  python -m playwright install chromium
Run:         python -m scripts.export_assets
"""
from __future__ import annotations

import socket
import sys
import threading
import time

from app.config import get_settings
from app.flowchart import latest_doc_id, write_docs


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(port: int):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.1)
    sys.exit("Server did not start.")


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("Playwright is missing. Run: pip install playwright && python -m playwright install chromium")
    s = get_settings()
    s.outputs_dir.mkdir(parents=True, exist_ok=True)
    print(f"Wrote {write_docs(s)}")
    port = _port()
    server = _serve(port)
    base = f"http://127.0.0.1:{port}"
    did = latest_doc_id(s)
    shots = [("thumbnail.png", "/dashboard?mode=thumbnail", (1600, 1200), 1, False, "page"),
             ("dashboard_full.png", "/dashboard", (1440, 900), 2, True, "page"),
             ("flowchart_pipeline.png", "/flowchart?view=pipeline&export=1", (1300, 900), 2, True, "main")]
    if did:
        shots += [("review_page.png", f"/review?doc={did}", (1600, 1000), 2, False, "review"),
                  ("flowchart_trace.png", f"/flowchart?view=trace&export=1&doc={did}", (1000, 900), 2, True, "main")]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, path, (w, h), scale, full, mode in shots:
                page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
                page.goto(base + path, wait_until="networkidle")
                if mode == "review":
                    page.wait_for_selector(".frow", timeout=30_000)
                    page.wait_for_timeout(800)
                    page.screenshot(path=str(s.outputs_dir / name))
                else:
                    page.wait_for_function("window.__ready === true", timeout=30_000)
                    page.wait_for_timeout(400)
                    if mode == "main":
                        page.locator("main.page").screenshot(path=str(s.outputs_dir / name))
                    else:
                        page.screenshot(path=str(s.outputs_dir / name), full_page=full)
                page.close()
                print(f"Saved outputs/{name}")
            browser.close()
    finally:
        server.should_exit = True
        time.sleep(0.5)
    if not s.eval_results_path.exists():
        print("\nNote: no evaluation results yet, so the thumbnail is marked as a preview. Run `python -m eval.run_eval` first.")


if __name__ == "__main__":
    main()
