#!/usr/bin/env python3
"""Sanitize .env by joining continuation lines into the previous key's value.

Backs up the original to `.env.bak` before writing changes.
"""
from pathlib import Path


def is_key_line(s: str) -> bool:
    s = s.lstrip()
    if not s or s.startswith("#"):
        return True
    return "=" in s and s.split("=", 1)[0].strip().replace("\"", "").replace("'", "").replace("-", "").isalnum()


def sanitize(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out_lines = []
    curr = None
    for raw in lines:
        # Preserve comments and blank lines as separate entries
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            if curr is not None:
                out_lines.append(curr)
                curr = None
            out_lines.append(raw)
            continue

        if is_key_line(raw):
            if curr is not None:
                out_lines.append(curr)
            curr = raw.rstrip()
        else:
            # continuation line - append directly (remove leading spaces)
            if curr is None:
                curr = raw.rstrip()
            else:
                curr = curr + raw.strip()

    if curr is not None:
        out_lines.append(curr)

    backup = path.with_name(path.name + ".bak")
    backup.write_text(text, encoding="utf-8")
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    p = Path(".env")
    if not p.exists():
        print(".env not found")
        raise SystemExit(1)
    sanitize(p)
    print("Sanitized .env -> .env.bak created")
