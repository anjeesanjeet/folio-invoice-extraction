"""Turns an uploaded file into page images (for the model and the review page) and, for digital PDFs, a text layer."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


@dataclass
class Document:
    kind: str                       # digital | scan
    pages: list[bytes] = field(default_factory=list)   # PNG bytes
    text: str = ""                  # text layer (digital PDFs only)
    sharpness: float | None = None  # scans only: edge strength; low means blurry or low resolution


def sharpness(img) -> float:
    """Variance of edge strength at a fixed width. Sharp text gives strong edges; blur and heavy compression flatten them."""
    from PIL import ImageFilter, ImageStat
    g = img.convert("L")
    g = g.resize((1000, max(1, int(g.height * 1000 / g.width))))
    return round(ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0], 1)


def _png(img) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def load(path: Path, max_pages: int = 3, scale: float = 1.6) -> Document:
    from PIL import Image
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        img = Image.open(path)
        if max(img.size) > 2000:
            img.thumbnail((2000, 2000))
        return Document("scan", [_png(img)], sharpness=sharpness(img))
    if ext != ".pdf":
        raise ValueError(f"Unsupported file type '{ext}'. Use PDF, PNG, JPG, WEBP or TIFF.")
    import pdfplumber
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    pages = [_png(pdf[i].render(scale=scale).to_pil()) for i in range(min(len(pdf), max_pages))]
    with pdfplumber.open(str(path)) as doc:
        text = "\n".join((p.extract_text() or "") for p in doc.pages[:max_pages])
    kind = "digital" if len(text.strip()) > 40 else "scan"     # an image-only PDF is a scan
    if kind == "digital":
        return Document(kind, pages, text)
    from PIL import Image
    return Document(kind, pages, "", sharpness(Image.open(io.BytesIO(pages[0]))))