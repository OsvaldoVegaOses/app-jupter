"""Functional smoke test for APP_Jupter using a DOCX file.

Runs a minimal end-to-end flow against the running backend API:
- Reads DOCX text (for quick PII/toponym checks)
- Lists projects and optionally creates a test project
- Uploads + ingests the DOCX
- Fetches dashboard counts + stage snapshot
- Runs a Discovery search + AI analysis
- Inserts one candidate code (if suggested) and validates it
- Verifies it appears in definitive open codes

Usage (PowerShell):
    ./.venv/Scripts/python scripts/functional_test_docx.py --docx "C:\\Users\\osval\\Downloads\\Resumen_visual_test_JD007.docx"

Note: This script intentionally avoids printing secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from docx import Document  # python-docx
except Exception as exc:  # pragma: no cover
    raise RuntimeError("python-docx is required. Install with `pip install python-docx`.") from exc


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# NOTE: keep phone heuristic conservative to avoid counting any random numbers in transcripts.
# Chile-focused patterns (mobile: 9xxxx xxxx, landline: 2xxxx xxxx), with optional +56.
PHONE_RE = re.compile(r"\b(?:\+?56\s*)?(?:9|2)\s*\d{4}[\s-]?\d{4}\b")
RUT_RE = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b|\b\d{7,8}-[\dkK]\b")


@dataclass
class DocxSummary:
    paragraphs: int
    chars: int
    emails: int
    phones: int
    ruts: int
    contains: Dict[str, bool]


def _load_api_key() -> Optional[str]:
    # Priority: environment
    key = os.getenv("NEO4J_API_KEY") or os.getenv("API_KEY")
    if key:
        return key

    # Fallback: .env in cwd
    env_path = Path(".env")
    if env_path.exists():
        txt = env_path.read_text(encoding="utf-8", errors="ignore")
        for name in ("NEO4J_API_KEY", "API_KEY"):
            m = re.search(rf"^\s*{re.escape(name)}\s*=\s*(.+)\s*$", txt, flags=re.M)
            if m:
                val = m.group(1).strip().strip('"').strip("'")
                if val:
                    return val
    return None


def _docx_to_text(docx_path: Path) -> str:
    doc = Document(str(docx_path))
    parts: List[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    return "\n".join(parts)


def summarize_docx(docx_path: Path) -> Tuple[str, DocxSummary]:
    text = _docx_to_text(docx_path)

    # Keep checks very lightweight: just counts and a few key terms.
    emails = len(EMAIL_RE.findall(text))
    phones = len(PHONE_RE.findall(text))
    ruts = len(RUT_RE.findall(text))

    # Terms mentioned in the user's critique
    key_terms = [
        "La Florida",
        "Puente Alto",
        "Horcón",
        "Horcon",  # without accent
    ]
    contains = {term: (term.lower() in text.lower()) for term in key_terms}

    para_count = len([p for p in text.splitlines() if p.strip()])
    chars = len(text)

    return text, DocxSummary(
        paragraphs=para_count,
        chars=chars,
        emails=emails,
        phones=phones,
        ruts=ruts,
        contains=contains,
    )


def _req(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    **kwargs: Any,
) -> requests.Response:
    last_exc: Optional[BaseException] = None
    for attempt in range(1, 4):
        try:
            return session.request(method, url, headers=headers, timeout=120, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise
    raise RuntimeError(f"request failed unexpectedly: {last_exc}")


def _print_http_error(label: str, resp: requests.Response) -> None:
    try:
        body = resp.text
    except Exception:
        body = "(no body)"
    body = (body or "")
    if len(body) > 2000:
        body = body[:2000] + "..."
    print(f"{label}: {resp.status_code} {resp.reason}")
    if body.strip():
        print(body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", required=True, help="Path to DOCX")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--project", default=None, help="Existing project id to reuse")
    ap.add_argument("--create-project-name", default=None, help="Project name to create if --project not provided")
    ap.add_argument("--min-chars", type=int, default=200)
    ap.add_argument("--max-chars", type=int, default=1200)
    ap.add_argument("--batch-size", type=int, default=20)
    args = ap.parse_args()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"ERROR: DOCX not found: {docx_path}", file=sys.stderr)
        return 2

    api_key = _load_api_key()
    if not api_key:
        print("ERROR: Could not find API key (NEO4J_API_KEY/API_KEY) in env or .env", file=sys.stderr)
        return 3

    headers = {"X-API-Key": api_key}

    print("== DOCX quick checks ==")
    text, summary = summarize_docx(docx_path)
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2))

    base = args.base_url.rstrip("/")
    sess = requests.Session()

    print("\n== Backend health ==")
    # healthz is provided by admin health router
    try:
        h = _req(sess, "GET", f"{base}/healthz", headers=headers)
        print("healthz_status:", h.status_code)
    except Exception as exc:
        print("ERROR: backend not reachable:", str(exc), file=sys.stderr)
        return 10

    print("\n== List projects (searching for JD-007) ==")
    r = _req(sess, "GET", f"{base}/api/projects", headers=headers)
    if not r.ok:
        print("ERROR: /api/projects failed:", r.status_code, r.text[:500], file=sys.stderr)
        return 4
    projects = (r.json() or {}).get("projects") or []
    jd = [p for p in projects if "jd" in str(p).lower() and "007" in str(p).lower()]
    print("projects_total:", len(projects))
    print("jd007_matches:", len(jd))
    for p in jd[:10]:
        # avoid dumping full object; print key fields only
        pid = p.get("id") if isinstance(p, dict) else None
        name = p.get("name") if isinstance(p, dict) else None
        print("-", pid, "|", name)

    project_id: Optional[str] = args.project
    if not project_id:
        # Generate a unique project name by default to avoid collisions across runs.
        ts = time.strftime("%Y%m%d_%H%M%S")
        name = args.create_project_name or f"jd007_visual_test_{docx_path.stem}_{ts}"
        print("\n== Create test project ==")
        cr = _req(
            sess,
            "POST",
            f"{base}/api/projects",
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps({"name": name, "description": "smoke test from scripts/functional_test_docx.py"}),
        )
        if not cr.ok:
            # If the project already exists (rare unless name is forced), try to reuse it.
            detail = (cr.text or "")
            if cr.status_code == 400 and "Ya existe" in detail:
                print("create_project_conflict: attempting reuse")
                # Heuristic: pick the most recent matching project id from the list.
                reuse = None
                for p in projects:
                    if not isinstance(p, dict):
                        continue
                    pid = p.get("id")
                    if isinstance(pid, str) and pid.startswith("jd007-visual-test"):
                        reuse = pid
                        break
                if reuse:
                    project_id = reuse
                    print("reused_project_id:", project_id)
                else:
                    print("ERROR: create project conflict and no reuse candidate found", file=sys.stderr)
                    _print_http_error("create_project_error", cr)
                    return 5
            else:
                print("ERROR: create project failed", file=sys.stderr)
                _print_http_error("create_project_error", cr)
                return 5
        created = cr.json() or {}
        if not project_id:
            project_id = created.get("id")
            print("created_project_id:", project_id)

    if not project_id:
        print("ERROR: Could not determine project id", file=sys.stderr)
        return 6

    print("\n== Upload + ingest DOCX ==")
    with open(docx_path, "rb") as f:
        files = {"file": (docx_path.name, f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        data = {
            "project": project_id,
            "batch_size": str(args.batch_size),
            "min_chars": str(args.min_chars),
            "max_chars": str(args.max_chars),
        }
        up = _req(sess, "POST", f"{base}/api/upload-and-ingest", headers=headers, files=files, data=data)
    print("upload_ingest_status:", up.status_code)
    if not up.ok:
        print("upload_ingest_error:", up.text[:1200])
        return 7
    upj = up.json() if up.headers.get("content-type", "").startswith("application/json") else {"raw": up.text}
    print("upload_ingest_response_keys:", sorted(list(upj.keys()))[:30])

    print("\n== Status snapshot (stages) ==")
    try:
        st = _req(sess, "GET", f"{base}/api/status", headers=headers, params={"project": project_id})
        print("status_snapshot_status:", st.status_code)
        if st.ok:
            sj = st.json() or {}
            print(
                json.dumps(
                    {
                        "completed": sj.get("completed"),
                        "total": sj.get("total"),
                        "next_stage": sj.get("next_stage"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_http_error("status_snapshot_error", st)
    except Exception as exc:
        print("status_snapshot_exception:", str(exc))

    print("\n== Dashboard counts ==")
    try:
        dc = _req(sess, "GET", f"{base}/api/dashboard/counts", headers=headers, params={"project": project_id})
        print("dashboard_counts_status:", dc.status_code)
        if dc.ok:
            dj = dc.json() or {}
            out = {
                "ingesta": dj.get("ingesta"),
                "codificacion": dj.get("codificacion"),
                "axial": dj.get("axial"),
                "candidatos": dj.get("candidatos"),
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            _print_http_error("dashboard_counts_error", dc)
    except Exception as exc:
        print("dashboard_counts_exception:", str(exc))

    # If the backend crashed/restarted due to an exception, detect it early.
    try:
        hh = _req(sess, "GET", f"{base}/healthz", headers=headers)
        print("healthz_after_counts:", hh.status_code)
    except Exception as exc:
        print("WARNING: backend unreachable after counts/status:", str(exc))

    print("\n== Discovery search (pobreza) ==")
    ds = _req(
        sess,
        "POST",
        f"{base}/api/search/discover",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps({
            "positive_texts": ["pobreza"],
            "negative_texts": ["logistica_entrevista", "muletilla"],
            "target_text": "pobreza y desarrollo",
            "top_k": 10,
            "project": project_id,
        }),
    )
    print("discover_status:", ds.status_code)
    if not ds.ok:
        print("discover_error:", ds.text[:800])
        return 8
    djson = ds.json() or {}
    frag_count = int(djson.get("count") or 0)
    print("discover_fragments_count:", frag_count)

    if frag_count > 0:
        frags = djson.get("fragments") or []
        sample = frags[:10]

        print("\n== Discovery AI analyze ==")
        an = _req(
            sess,
            "POST",
            f"{base}/api/discovery/analyze",
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps({
                "positive_texts": ["pobreza"],
                "negative_texts": ["logistica_entrevista", "muletilla"],
                "target_text": "pobreza y desarrollo",
                "fragments": sample,
                "project": project_id,
            }),
        )
        print("analyze_status:", an.status_code)
        if not an.ok:
            print("analyze_error:", an.text[:800])
        else:
            aj = an.json() or {}
            codes = aj.get("codigos_sugeridos") or []
            print("ai_structured:", bool(aj.get("structured")))
            print("ai_codes_count:", len(codes))

            # Insert + validate one candidate to test candidate->definitive flow
            if codes:
                first_code = str(codes[0]).strip()
                frag0 = sample[0] if sample else {}
                frag_id = frag0.get("fragmento_id") or frag0.get("id") or "unknown"
                archivo = frag0.get("archivo")

                print("\n== Insert candidate code (1) ==")
                ins = _req(
                    sess,
                    "POST",
                    f"{base}/api/codes/candidates",
                    headers={**headers, "Content-Type": "application/json"},
                    data=json.dumps({
                        "project": project_id,
                        "codigo": first_code,
                        "cita": "smoke test candidate",
                        "fragmento_id": frag_id,
                        "archivo": archivo,
                        "fuente_origen": "discovery_ai",
                        "fuente_detalle": "scripts/functional_test_docx.py",
                        "score_confianza": 0.75,
                        "memo": "candidate inserted by smoke test",
                    }),
                )
                print("insert_candidate_status:", ins.status_code)
                if ins.ok:
                    print("insert_candidate_response:", ins.json())

                print("\n== List candidates (latest) ==")
                lc = _req(sess, "GET", f"{base}/api/codes/candidates", headers=headers, params={"project": project_id, "limit": 5, "sort_order": "desc"})
                print("list_candidates_status:", lc.status_code)
                candidate_id = None
                if lc.ok:
                    ljson = lc.json() or {}
                    candidates = ljson.get("candidates") or []
                    if candidates:
                        candidate_id = candidates[0].get("id")
                        print("latest_candidate_id:", candidate_id)

                if candidate_id is not None:
                    print("\n== Validate candidate (should promote if auto-promote enabled) ==")
                    vc = _req(
                        sess,
                        "PUT",
                        f"{base}/api/codes/candidates/{candidate_id}/validate",
                        headers={**headers, "Content-Type": "application/json"},
                        data=json.dumps({"project": project_id, "memo": "validated by smoke test"}),
                    )
                    print("validate_candidate_status:", vc.status_code)
                    if vc.ok:
                        print("validate_candidate_response:", vc.json())

                    print("\n== Verify definitive codes list ==")
                    oc = _req(sess, "GET", f"{base}/api/coding/codes", headers=headers, params={"project": project_id, "limit": 50, "search": first_code})
                    print("open_codes_status:", oc.status_code)
                    if oc.ok:
                        oj = oc.json() or {}
                        hits = oj.get("codes") or []
                        print("open_codes_hits:", len(hits))

    print("\nDONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
