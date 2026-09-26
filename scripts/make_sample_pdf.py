"""
make_sample_pdf.py — Generates a small, text-based sample contract PDF.

This exists because the test suite needs a real PDF upload, and we don't want
to commit one. It builds a minimal single-page PDF byte-by-byte (with correct
xref offsets) so no extra PDF-writing dependency is needed.

Usage:
    python scripts/make_sample_pdf.py   # writes backend/samples/sample_contract.pdf
"""

from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "backend" / "samples" / "sample_contract.pdf"

# Fake freelance contract exercising the risky-clause types the PRD cares
# about (termination, liability, IP assignment, auto-renewal, payment).
CONTRACT_LINES = [
    "FREELANCE SERVICES AGREEMENT",
    "",
    "1. SERVICES. The Designer shall provide logo and brand identity",
    "services as described in Exhibit A.",
    "",
    "2. TERMINATION. Client may terminate this Agreement at any time, for",
    "any reason, with zero (0) days written notice and without payment of",
    "any outstanding invoices.",
    "",
    "3. PAYMENT. Invoices are net-120. Client may withhold payment at its",
    "sole discretion until Client is fully satisfied with the work.",
    "",
    "4. INTELLECTUAL PROPERTY. Upon execution, Designer assigns to Client",
    "all right, title, and interest in all work product created prior to",
    "the Effective Date, including portfolio pieces.",
    "",
    "5. LIABILITY. In no event shall Client's total liability exceed the",
    "fees paid under this Agreement in the preceding one (1) month.",
    "",
    "6. AUTO-RENEWAL. This Agreement renews automatically for successive",
    "one-year terms unless Designer cancels in person at Client's office",
    "at least 90 days before the renewal date.",
    "",
    "7. GOVERNING LAW. This Agreement is governed by the laws of Delaware.",
]


def build_pdf(lines) -> bytes:
    """Assemble a minimal valid single-page PDF from text lines.

    Uses only PDF features pdfplumber/pdfminer needs for text extraction:
    one Helvetica font, one content stream with Tj text operators.
    Offsets for the xref table are computed while concatenating objects.
    """
    # Escape parens/backslashes for the PDF string literal syntax.
    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    # Content stream: move down the page line by line (14pt leading).
    stream_lines = ["BT", "/F1 10 Tf", "14 TL", "50 760 Td"]
    for line in lines:
        stream_lines.append(f"({esc(line)}) Tj T*")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    # Cross-reference table with exact byte offsets.
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


def main() -> None:
    """Write the sample PDF to backend/samples/, creating the folder if needed."""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(build_pdf(CONTRACT_LINES))
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
