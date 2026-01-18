"""
Procesamiento y fragmentación de documentos DOCX.

Este módulo contiene la lógica para:
1. Leer archivos DOCX de entrevistas transcritas
2. Detectar y separar roles de hablante (entrevistador/entrevistado)
3. Fragmentar el texto en chunks óptimos para análisis
4. Filtrar contenido no sustantivo (fillers, timestamps)

Flujo de procesamiento:
    DOCX → Paragraphs → ParagraphRecords → FragmentRecords → Embeddings
    
Clases principales:
    - ParagraphRecord: Párrafo individual con texto y speaker
    - FragmentRecord: Fragmento coalescido con métricas de tokens
    - FragmentLoadResult: Resultado de carga con fragmentos y estadísticas

Funciones principales:
    - load_fragments(): Carga un DOCX y retorna fragmentos listos para embedding
    - read_paragraph_records(): Lee párrafos con detección de speaker
    - coalesce_paragraph_records(): Agrupa párrafos en fragmentos óptimos
    - match_citation_to_fragment(): Busca fragmento que coincide con una cita del LLM

Parámetros de fragmentación:
    - min_chars: Mínimo de caracteres por fragmento (default: 200)
    - max_chars: Máximo de caracteres por fragmento (default: 1200)
    - min_interviewee_tokens: Mínimo de tokens del entrevistado para incluir (default: 10)
    
Detección de speaker:
    - Busca prefijos como "Entrevistador:", "Moderador:", "Entrevistado:"
    - Detecta timestamps para cambio de speaker
    - Default: interviewee (el contenido principal son respuestas)

Example:
    >>> from app.documents import load_fragments
    >>> fragments = load_fragments("entrevista.docx")
    >>> print(f"Fragmentos: {len(fragments)}")
    Fragmentos: 45
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from docx import Document


@dataclass
class ParagraphRecord:
    text: str
    speaker: str  # interviewer | interviewee | unknown


@dataclass
class FragmentRecord:
    text: str
    speaker: str
    interviewer_tokens: int
    interviewee_tokens: int


@dataclass
class FragmentLoadResult:
    fragments: List[FragmentRecord]
    stats: Dict[str, int]


_INTERVIEWER_PREFIXES = (
    r"\s*entrevistador(?:a)?[\s\.:,-]*",
    r"\s*moderador(?:a)?[\s\.:,-]*",
    r"\s*[\w\s\.]+,\s*entrevistador(?:a)?[\s\.:,-]*",
)
_INTERVIEWEE_PREFIXES = (
    r"\s*entrevistad[ao][\s\.:,-]*",
    r"\s*participante[\s\.:,-]*",
)
_TIMESTAMP_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?")
_INTERVIEWER_KEYWORDS = ["entrevistador", "moderador"]
_FILLER_RE = re.compile(r"^(ya|claro|s[íi]|aj[áa]|ok|bueno|mmm+|entiendo|perfecto|correcto|vale)[\.,]?\s*$", re.IGNORECASE)
_PREAMBLE_PATTERNS = (
    re.compile(r"^archivo de audio\b", re.IGNORECASE),
    re.compile(r"^transcripci[óo]n\b", re.IGNORECASE),
    re.compile(r"^entrevista\b", re.IGNORECASE),
    re.compile(r"^comuna\b", re.IGNORECASE),
    re.compile(r"^fecha\b", re.IGNORECASE),
    re.compile(r"^lugar\b", re.IGNORECASE),
    re.compile(r"^participantes?\b", re.IGNORECASE),
    re.compile(r"^tema\b", re.IGNORECASE),
    re.compile(r"^proyecto\b", re.IGNORECASE),
    re.compile(r"^registro\b", re.IGNORECASE),
    re.compile(r"^c[oó]digo\b", re.IGNORECASE),
    re.compile(r"^social[_\s].*comuna[_\s]", re.IGNORECASE),
)

def normalize_text(raw: str) -> str:
    text = raw.replace("\u00A0", " ")
    # remove timestamp if inside text
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def _split_speaker(text: str) -> Tuple[str, str]:
    """Detect speaker prefixes and strip them, defaulting to interviewee."""
    for pattern in _INTERVIEWER_PREFIXES:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return "interviewer", text[match.end():].strip()
    for pattern in _INTERVIEWEE_PREFIXES:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return "interviewee", text[match.end():].strip()
    return "interviewee", text


def _is_filler(text: str) -> bool:
    if not text:
        return True
    if len(text) <= 3:
        return True
    if _FILLER_RE.match(text.strip()):
        return True
    return False


def _is_preamble_line(text: str) -> bool:
    if not text:
        return True
    if len(text.split()) <= 4:
        return True
    return any(pattern.search(text) for pattern in _PREAMBLE_PATTERNS)


def _token_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _prepare_paragraph(raw: str) -> ParagraphRecord | None:
    normalized = normalize_text(raw)
    if not normalized:
        return None
    speaker, content = _split_speaker(normalized)
    if not content:
        return None
    if speaker == "interviewer" and _is_filler(content):
        return None
    return ParagraphRecord(text=content, speaker=speaker)


def read_paragraph_records(path: str | Path) -> List[ParagraphRecord]:
    doc = Document(str(path))
    paragraphs: List[ParagraphRecord] = []
    current_speaker = "interviewee"
    dialog_started = False

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        
        # 1. Stateful Speaker Detection (Metadata Line)
        if _TIMESTAMP_RE.match(text):
            lower_text = text.lower()
            if any(kw in lower_text for kw in _INTERVIEWER_KEYWORDS):
                current_speaker = "interviewer"
            else:
                current_speaker = "interviewee"
            # We skip this line as it is just metadata
            dialog_started = True
            continue

        # 2. Content Processing
        normalized = normalize_text(text)
        if not normalized:
            continue
        speaker_from_prefix, content = _split_speaker(normalized)
        if speaker_from_prefix == "interviewee" and content == normalized:
            speaker = current_speaker
        else:
            speaker = speaker_from_prefix

        if not dialog_started:
            if speaker == "interviewer" or "?" in content:
                dialog_started = True
            elif _is_preamble_line(content):
                continue

        if speaker == "interviewer" and _is_filler(content):
            continue

        paragraphs.append(ParagraphRecord(text=content, speaker=speaker))

    return paragraphs


def read_paragraphs(path: str | Path) -> List[str]:
    return [p.text for p in read_paragraph_records(path)]


def coalesce_paragraph_records(
    paragraphs: Sequence[ParagraphRecord],
    min_chars: int = 200,
    max_chars: int = 1200,
    min_interviewee_tokens: int = 10,
    overlap_chars: int = 100,
) -> Tuple[List[FragmentRecord], int]:
    """
    Agrupa párrafos en fragmentos respetando límites de caracteres.
    
    Args:
        paragraphs: Lista de párrafos con speaker
        min_chars: Mínimo de caracteres por fragmento
        max_chars: Máximo de caracteres por fragmento
        min_interviewee_tokens: Mínimo de tokens del entrevistado para incluir
        overlap_chars: Caracteres de solapamiento entre fragmentos (default: 100)
                       Esto preserva contexto en los bordes de fragmentos.
    
    Returns:
        Tupla de (fragmentos, fragmentos_descartados)
    """
    fragments: List[FragmentRecord] = []
    buffer: List[str] = []
    interviewee_tokens = 0
    interviewer_tokens = 0
    pending_interviewer_tokens = 0
    discarded_fragments = 0
    overlap_prefix = ""  # Almacena el texto de solapamiento del fragmento anterior

    def flush(keep_overlap: bool = True) -> None:
        nonlocal buffer, interviewee_tokens, interviewer_tokens, discarded_fragments, overlap_prefix
        if not buffer:
            interviewee_tokens = 0
            interviewer_tokens = 0
            return
        
        # Prepend overlap from previous fragment if exists
        text_parts = [overlap_prefix] if overlap_prefix else []
        text_parts.extend(buffer)
        text = " ".join(text_parts).strip()
        
        if not text or interviewee_tokens < min_interviewee_tokens:
            discarded_fragments += 1
            buffer = []
            interviewee_tokens = 0
            interviewer_tokens = 0
            overlap_prefix = ""
            return
        
        dominant = "interviewee" if interviewee_tokens >= max(1, interviewer_tokens) else "interviewer"
        fragments.append(
            FragmentRecord(
                text=text,
                speaker=dominant,
                interviewer_tokens=interviewer_tokens,
                interviewee_tokens=interviewee_tokens,
            )
        )
        
        # Keep overlap for next fragment
        if keep_overlap and overlap_chars > 0:
            buffer_text = " ".join(buffer)
            if len(buffer_text) > overlap_chars:
                # Find a good break point (space) near overlap_chars from end
                overlap_start = len(buffer_text) - overlap_chars
                space_pos = buffer_text.find(" ", overlap_start)
                if space_pos > 0:
                    overlap_prefix = buffer_text[space_pos:].strip()
                else:
                    overlap_prefix = buffer_text[-overlap_chars:].strip()
            else:
                overlap_prefix = buffer_text.strip()
        else:
            overlap_prefix = ""
        
        buffer = []
        interviewee_tokens = 0
        interviewer_tokens = 0

    for para in paragraphs:
        tokens = _token_count(para.text)
        if para.speaker == "interviewer":
            if buffer:
                flush()
            pending_interviewer_tokens += tokens
            continue

        if not buffer:
            interviewer_tokens = pending_interviewer_tokens
        else:
            interviewer_tokens += pending_interviewer_tokens
        pending_interviewer_tokens = 0

        candidate_text = " ".join(buffer + [para.text]).strip()
        if buffer and len(candidate_text) > max_chars and len(" ".join(buffer)) >= min_chars:
            flush()
        buffer.append(para.text)
        interviewee_tokens += tokens

    flush(keep_overlap=False)  # Last fragment doesn't need overlap
    return fragments, discarded_fragments


def coalesce_paragraphs(paragraphs: Sequence[str], min_chars: int = 200, max_chars: int = 1200) -> List[str]:
    records = [ParagraphRecord(text=para, speaker="interviewee") for para in paragraphs]
    fragments, _ = coalesce_paragraph_records(records, min_chars=min_chars, max_chars=max_chars)
    return [fragment.text for fragment in fragments]

def match_citation_to_fragment(
    citation: str,
    fragments: Sequence[str],
    threshold: float = 0.5,
) -> int | None:
    """
    Find the fragment that best matches a citation from LLM analysis.
    
    Uses substring matching and sequence similarity to recover fragment index
    when the LLM doesn't provide fragmento_idx.
    
    Args:
        citation: The citation text from LLM (typically 20-60 words)
        fragments: List of fragment texts to search
        threshold: Minimum similarity score (0.0-1.0) to accept a match
        
    Returns:
        Index of best matching fragment, or None if no match above threshold
    """
    from difflib import SequenceMatcher
    
    if not citation or not fragments:
        return None
    
    citation_lower = citation.lower().strip()
    best_idx = None
    best_score = 0.0
    
    for idx, frag in enumerate(fragments):
        frag_lower = frag.lower()
        
        # Fast path: direct substring match
        if citation_lower in frag_lower:
            return idx
        
        # Slower path: sequence similarity
        score = SequenceMatcher(None, citation_lower, frag_lower).ratio()
        
        # Boost score if citation words appear in fragment
        citation_words = set(citation_lower.split())
        frag_words = set(frag_lower.split())
        overlap = len(citation_words & frag_words) / max(len(citation_words), 1)
        score = (score + overlap) / 2
        
        if score > best_score and score >= threshold:
            best_score = score
            best_idx = idx
    
    return best_idx


def make_fragment_id(file_name: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_name}|{index}"))


def batched(seq: Iterable, size: int) -> Iterable[List]:
    batch: List = []
    for item in seq:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_fragment_records(
    file_path: str | Path,
    min_chars: int = 200,
    max_chars: int = 1200,
    min_interviewee_tokens: int = 10,
) -> FragmentLoadResult:
    paragraphs = read_paragraph_records(file_path)
    fragments, discarded = coalesce_paragraph_records(
        paragraphs,
        min_chars=min_chars,
        max_chars=max_chars,
        min_interviewee_tokens=min_interviewee_tokens,
    )
    stats = {
        "paragraphs_total": len(paragraphs),
        "paragraphs_interviewer": sum(1 for p in paragraphs if p.speaker == "interviewer"),
        "interviewer_tokens_dropped": sum(_token_count(p.text) for p in paragraphs if p.speaker == "interviewer"),
        "fragments_discarded_low_interviewee": discarded,
        "interviewee_tokens_kept": sum(f.interviewee_tokens for f in fragments),
        "interviewer_tokens_attached": sum(f.interviewer_tokens for f in fragments),
    }
    return FragmentLoadResult(fragments=fragments, stats=stats)


def load_fragments(
    file_path: str | Path,
    min_chars: int = 200,
    max_chars: int = 1200,
    min_interviewee_tokens: int = 10,
) -> List[str]:
    result = load_fragment_records(file_path, min_chars=min_chars, max_chars=max_chars, min_interviewee_tokens=min_interviewee_tokens)
    return [fragment.text for fragment in result.fragments]
