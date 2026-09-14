"""Generate sample_cvs/*.pdf from the .txt sources.

Uses a tiny dependency-free PDF writer so the repo ships real PDF files
(which the CV parser can also ingest via pypdf) without needing reportlab.

Run:  python scripts/make_sample_pdfs.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sample_cvs"


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _write_pdf(path: Path, lines: list[str]) -> None:
    font = 11
    leading = 14
    top = 720

    content_parts = [f"BT /F1 {font} Tf 72 {top} Td {leading} TL"]
    for line in lines:
        content_parts.append(f"({_escape(line)}) Tj T*")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()

    path.write_bytes(bytes(out))
    print(f"wrote {path}")


def main() -> None:
    for txt in sorted(SRC.glob("*.txt")):
        lines = txt.read_text(encoding="utf-8").splitlines()
        _write_pdf(SRC / (txt.stem + ".pdf"), lines)
    print("done")


if __name__ == "__main__":
    main()
