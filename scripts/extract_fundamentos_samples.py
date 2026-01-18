from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def main() -> None:
    root = Path("docs/fundamentos_teoria")
    pdfs = sorted(root.glob("*.pdf"))
    print(f"PDFs: {len(pdfs)}")

    for path in pdfs:
        doc = fitz.open(path)
        pages_to_read = min(2, doc.page_count)
        samples: list[str] = []
        for i in range(pages_to_read):
            text = doc.load_page(i).get_text("text")
            text = " ".join(text.split())
            samples.append(text[:800])

        sample_joined = " | ".join(samples)[:1600]
        print("\n---")
        print(path.name)
        print(f"pages: {doc.page_count}")
        print(f"sample: {sample_joined}")


if __name__ == "__main__":
    main()
