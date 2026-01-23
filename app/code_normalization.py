"""
Normalización y detección de duplicados de códigos.

Este módulo implementa fuzzy matching para detectar códigos similares
y prevenir fragmentación del grafo de codificación.

Funciones principales:
    - normalize_code(): Normaliza texto (tildes, espacios, etc.)
    - find_similar_codes(): Detecta códigos similares usando rapidfuzz
    - suggest_code_merge(): Sugiere fusión de códigos duplicados

Estrategia Pre-Hoc:
    Interceptar ANTES de insertar códigos para detectar:
    - 'organizacion' vs 'organización' (tildes)
    - 'enfoque_de_genero' vs 'enfoque_genero' (preposición)

Example:
    >>> from app.code_normalization import find_similar_codes
    >>> existing = ['organización', 'territorio', 'género']
    >>> similar = find_similar_codes('organizacion', existing, threshold=0.85)
    >>> # [('organización', 0.92)]
"""

from __future__ import annotations

import unicodedata
import re
import time
from typing import List, Tuple, Optional, Dict, Any

import structlog

# Intentar importar rapidfuzz, con fallback a difflib
try:
    from rapidfuzz import fuzz
    from rapidfuzz import process as fuzz_process
    from rapidfuzz.distance import Levenshtein
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    from difflib import SequenceMatcher

_logger = structlog.get_logger()


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Umbral de similitud para detectar duplicados (0.0 - 1.0)
SIMILARITY_THRESHOLD = 0.85

# Umbral mínimo para Discovery (subido de 0.22 para reducir ruido)
DISCOVERY_THRESHOLD = 0.35


# =============================================================================
# NORMALIZACIÓN DE TEXTO
# =============================================================================

def normalize_code(codigo: str) -> str:
    """
    Normaliza un código para comparación.
    
    Transformaciones:
    - Minúsculas
    - Eliminar acentos/tildes
    - Reemplazar guiones y underscores por espacios
    - Colapsar espacios múltiples
    - Strip whitespace
    
    Args:
        codigo: Código original
        
    Returns:
        Código normalizado para comparación
        
    Example:
        >>> normalize_code("Organización_Social")
        'organizacion social'
    """
    if not codigo:
        return ""
    
    # Minúsculas
    text = codigo.lower()
    
    # Eliminar acentos (ñ se preserva como n)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Reemplazar guiones y underscores por espacios
    text = re.sub(r'[-_]', ' ', text)
    
    # Colapsar espacios múltiples
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calcula similitud entre dos textos.
    
    Usa rapidfuzz si está disponible, sino difflib.
    
    Args:
        text1: Primer texto
        text2: Segundo texto
        
    Returns:
        Similitud entre 0.0 y 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalizar antes de comparar
    norm1 = normalize_code(text1)
    norm2 = normalize_code(text2)
    
    if RAPIDFUZZ_AVAILABLE:
        # Base: similitud Levenshtein normalizada (alineada con Post-Hoc)
        max_len = max(len(norm1), len(norm2))
        if max_len == 0:
            return 0.0
        distance = Levenshtein.distance(norm1, norm2)
        lev_sim = max(0.0, 1.0 - (distance / max_len))

        # Refuerzo: token_set_ratio maneja stopwords/orden (mejor UX en Pre-Hoc)
        token_sim = fuzz.token_set_ratio(norm1, norm2) / 100.0

        # Tomar el máximo para no penalizar variantes con tokens extra (p.ej. "de")
        return max(lev_sim, token_sim)
    else:
        # difflib devuelve 0-1 directamente
        return SequenceMatcher(None, norm1, norm2).ratio()


def _tokenize_normalized(value: str) -> List[str]:
    """Tokeniza un texto YA normalizado en tokens alfanuméricos."""
    if not value:
        return []
    return [tok for tok in re.split(r"[^a-z0-9]+", value) if tok]


def _token_overlap_ok(norm_a: str, norm_b: str, min_jaccard: float = 0.5) -> bool:
    """Guardrail anti falsos-positivos: exige solapamiento de tokens."""
    ta = set(_tokenize_normalized(norm_a))
    tb = set(_tokenize_normalized(norm_b))
    if not ta or not tb:
        return False

    inter = ta.intersection(tb)
    union = ta.union(tb)
    if not union:
        return False

    jaccard = len(inter) / len(union)
    if jaccard < min_jaccard:
        return False

    # Si difieren solo en un token, exigir similitud alta entre esos tokens
    diff_a = list(ta - tb)
    diff_b = list(tb - ta)
    if len(diff_a) == 1 and len(diff_b) == 1:
        tok_a, tok_b = diff_a[0], diff_b[0]
        max_len = max(len(tok_a), len(tok_b))
        if max_len == 0:
            return False
        if RAPIDFUZZ_AVAILABLE:
            distance = Levenshtein.distance(tok_a, tok_b)
            tok_sim = 1.0 - (distance / max_len)
        else:
            tok_sim = SequenceMatcher(None, tok_a, tok_b).ratio()
        return tok_sim >= 0.8

    return True


def find_similar_codes(
    codigo: str,
    existing_codes: List[str],
    threshold: float = SIMILARITY_THRESHOLD,
    limit: int = 5,
) -> List[Tuple[str, float]]:
    """
    Encuentra códigos similares al propuesto.
    
    Args:
        codigo: Código nuevo propuesto
        existing_codes: Lista de códigos existentes
        threshold: Umbral mínimo de similitud (default 0.85)
        limit: Máximo de resultados
        
    Returns:
        Lista de tuplas (codigo_existente, similitud) ordenadas por similitud desc
        
    Example:
        >>> find_similar_codes('organizacion', ['organización', 'territorio'])
        [('organización', 0.92)]
    """
    if not codigo or not existing_codes:
        return []
    
    norm_codigo = normalize_code(codigo)
    results: List[Tuple[str, float]] = []
    
    # Estrategia (alineada con Post-Hoc + robustez UX):
    # 1) Normalizar
    # 2) Pre-filtro por diferencia de longitud SOLO si no hay alta similitud tokenizada
    #    (evita falsos negativos típicos por stopwords como "de")
    # 3) Similitud por Levenshtein normalizado + token_set_ratio (o difflib fallback)
    # 4) Guardrail: solapamiento de tokens (reduce falsos positivos)
    for existing in existing_codes:
        if not existing:
            continue
        norm_existing = normalize_code(existing)
        if not norm_existing:
            continue

        max_len = max(len(norm_codigo), len(norm_existing))
        if max_len == 0:
            continue

        # Si RapidFuzz está disponible, usar token_set_ratio como señal rápida.
        # Si esa señal NO es alta, aplicamos el pre-filtro por longitud.
        if RAPIDFUZZ_AVAILABLE:
            token_sim = fuzz.token_set_ratio(norm_codigo, norm_existing) / 100.0
            if token_sim < threshold:
                if abs(len(norm_codigo) - len(norm_existing)) > int((1 - threshold) * max_len):
                    continue
        else:
            if abs(len(norm_codigo) - len(norm_existing)) > int((1 - threshold) * max_len):
                continue

        similarity = calculate_similarity(norm_codigo, norm_existing)
        if similarity < threshold:
            continue

        if not _token_overlap_ok(norm_codigo, norm_existing):
            continue

        # Mantener el texto original como candidato de fusión
        results.append((existing, similarity))

    results.sort(key=lambda x: x[1], reverse=True)
    results = results[:limit]
    
    return results


def find_similar_codes_with_stats(
    codigo: str,
    existing_codes: List[str],
    threshold: float = SIMILARITY_THRESHOLD,
    limit: int = 5,
) -> Tuple[List[Tuple[str, float]], Dict[str, Any]]:
    """Igual que find_similar_codes, pero devuelve métricas internas.

    Nota:
    - Diseñada para observabilidad (Pre‑Hoc) sin loguear contenido sensible.
    - No altera el comportamiento: mismo ranking/limit que find_similar_codes.
    """
    started = time.perf_counter()

    stats: Dict[str, Any] = {
        "rapidfuzz": RAPIDFUZZ_AVAILABLE,
        "existing_count": len(existing_codes) if existing_codes else 0,
        "threshold": float(threshold),
        "limit": int(limit),
        "comparisons": 0,
        "skipped_empty_existing": 0,
        "skipped_norm_empty": 0,
        "skipped_len_prefilter": 0,
        "skipped_similarity": 0,
        "skipped_token_overlap": 0,
        "kept": 0,
        "best_similarity": None,
    }

    if not codigo or not existing_codes:
        stats["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return [], stats

    norm_codigo = normalize_code(codigo)
    if not norm_codigo:
        stats["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return [], stats

    results: List[Tuple[str, float]] = []

    for existing in existing_codes:
        stats["comparisons"] += 1

        if not existing:
            stats["skipped_empty_existing"] += 1
            continue

        norm_existing = normalize_code(existing)
        if not norm_existing:
            stats["skipped_norm_empty"] += 1
            continue

        max_len = max(len(norm_codigo), len(norm_existing))
        if max_len == 0:
            stats["skipped_norm_empty"] += 1
            continue

        # Prefiltro de longitud (condicionado por token_set_ratio cuando RapidFuzz está disponible)
        if RAPIDFUZZ_AVAILABLE:
            token_sim = fuzz.token_set_ratio(norm_codigo, norm_existing) / 100.0
            if token_sim < threshold:
                if abs(len(norm_codigo) - len(norm_existing)) > int((1 - threshold) * max_len):
                    stats["skipped_len_prefilter"] += 1
                    continue
        else:
            if abs(len(norm_codigo) - len(norm_existing)) > int((1 - threshold) * max_len):
                stats["skipped_len_prefilter"] += 1
                continue

        similarity = calculate_similarity(norm_codigo, norm_existing)
        if similarity < threshold:
            stats["skipped_similarity"] += 1
            continue

        if not _token_overlap_ok(norm_codigo, norm_existing):
            stats["skipped_token_overlap"] += 1
            continue

        stats["kept"] += 1
        if stats["best_similarity"] is None or float(similarity) > float(stats["best_similarity"]):
            stats["best_similarity"] = float(similarity)

        results.append((existing, similarity))

    results.sort(key=lambda x: x[1], reverse=True)
    results = results[:limit]

    stats["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return results, stats


def suggest_code_merge(
    new_codes: List[Dict[str, Any]],
    existing_codes: List[str],
    threshold: float = SIMILARITY_THRESHOLD,
    deduplicate_batch: bool = True,
) -> List[Dict[str, Any]]:
    """
    Procesa códigos nuevos y marca los que tienen similares existentes.
    
    INCLUYE deduplicación intra-batch para evitar "Batch Blindness".
    
    Para cada código nuevo, busca similares en:
    1. existing_codes (de la BD)
    2. Otros códigos en el mismo batch (si deduplicate_batch=True)
    
    Args:
        new_codes: Lista de códigos candidatos (dicts con 'codigo')
        existing_codes: Lista de nombres de códigos existentes
        threshold: Umbral de similitud
        deduplicate_batch: Si True, elimina duplicados dentro del batch
        
    Returns:
        Lista de códigos con campo 'similar_existing' añadido si hay duplicados
        Si deduplicate_batch=True, los duplicados intra-batch se fusionan
        
    Example:
        >>> codes = [{'codigo': 'organizacion', 'cita': 'A'},
        ...          {'codigo': 'organizacion', 'cita': 'B'}]  # Duplicado!
        >>> existing = ['territorio']
        >>> result = suggest_code_merge(codes, existing, deduplicate_batch=True)
        >>> len(result)  # Solo 1, con evidencias combinadas
        1
    """
    if not new_codes:
        return new_codes
    
    # =========================================================================
    # PASO 1: Deduplicación Intra-Batch (Evitar Batch Blindness)
    # =========================================================================
    
    if deduplicate_batch:
        from collections import defaultdict
        
        # Agrupar por código normalizado
        batch_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        for code_dict in new_codes:
            codigo = code_dict.get('codigo', '')
            if not codigo:
                continue
            
            # Normalizar para agrupar variantes idénticas
            norm_key = normalize_code(codigo)
            batch_groups[norm_key].append(code_dict)
        
        # Detectar duplicados intra-batch
        deduplicated = []
        batch_duplicates_found = 0
        
        for norm_key, group in batch_groups.items():
            if len(group) == 1:
                # Código único en el batch
                deduplicated.append(group[0])
            else:
                # ¡DUPLICADOS INTRA-BATCH DETECTADOS!
                batch_duplicates_found += len(group) - 1
                
                # Tomar el primero como base
                merged = dict(group[0])
                
                # Combinar citas de todos los duplicados
                all_citas = []
                all_fragmentos = set()
                all_archivos = set()
                max_score = 0.0
                
                for item in group:
                    if item.get('cita'):
                        all_citas.append(item['cita'])
                    if item.get('fragmento_id'):
                        all_fragmentos.add(item['fragmento_id'])
                    if item.get('archivo'):
                        all_archivos.add(item['archivo'])
                    if item.get('score_confianza'):
                        max_score = max(max_score, item.get('score_confianza', 0))
                
                # Fusionar información
                if len(all_citas) > 1:
                    merged['cita'] = " | ".join(all_citas[:3])  # Max 3 citas
                    if len(all_citas) > 3:
                        merged['cita'] += f" (+{len(all_citas)-3} más)"
                
                if max_score > 0:
                    merged['score_confianza'] = max_score
                
                # Marcar como fusionado
                merged['_batch_merged'] = True
                merged['_batch_count'] = len(group)
                
                # Nota en memo
                existing_memo = merged.get('memo') or ''
                merge_note = f"[BATCH-MERGE] {len(group)} entradas idénticas fusionadas"
                merged['memo'] = f"{merge_note} {existing_memo}".strip()
                
                _logger.info(
                    "code_normalization.batch_duplicates_merged",
                    codigo=merged.get('codigo'),
                    count=len(group),
                    sources=[c.get('archivo') for c in group],
                )
                
                deduplicated.append(merged)
        
        if batch_duplicates_found > 0:
            _logger.warning(
                "code_normalization.batch_blindness_prevented",
                duplicates_found=batch_duplicates_found,
                unique_codes=len(deduplicated),
                original_count=len(new_codes),
            )
        
        # Usar lista deduplicada
        new_codes = deduplicated
    
    # =========================================================================
    # PASO 2: Comparar contra códigos existentes en BD
    # =========================================================================
    
    if not existing_codes:
        return new_codes
    
    result = []
    for code_dict in new_codes:
        codigo = code_dict.get('codigo', '')
        if not codigo:
            result.append(code_dict)
            continue
        
        similar = find_similar_codes(codigo, existing_codes, threshold)
        
        if similar:
            # Clonar dict y agregar info de similares
            updated = dict(code_dict)
            updated['similar_existing'] = similar
            updated['has_similar'] = True
            
            # Agregar nota al memo
            best_match = similar[0]
            similarity_note = f"[SIMILAR] '{best_match[0]}' ({best_match[1]:.0%})"
            existing_memo = updated.get('memo') or ''
            updated['memo'] = f"{similarity_note} {existing_memo}".strip()
            
            _logger.info(
                "code_normalization.similar_found",
                new_code=codigo,
                similar_to=best_match[0],
                similarity=best_match[1],
            )
            
            result.append(updated)
        else:
            result.append(code_dict)
    
    return result



def get_existing_codes_for_project(pg_conn, project_id: str) -> List[str]:
    """
    Obtiene lista de códigos únicos existentes en un proyecto.
    
    Consulta tanto códigos validados como candidatos pendientes.
    
    Args:
        pg_conn: Conexión PostgreSQL
        project_id: ID del proyecto
        
    Returns:
        Lista de nombres de códigos únicos
    """
    sql = """
    SELECT DISTINCT codigo FROM (
        -- Códigos validados (definitivos)
        SELECT codigo FROM analisis_codigos_abiertos WHERE project_id = %s
        UNION
        -- Códigos candidatos pendientes/validados
        SELECT codigo FROM codigos_candidatos 
        WHERE project_id = %s AND estado IN ('pendiente', 'validado')
    ) AS all_codes
    """
    
    try:
        with pg_conn.cursor() as cur:
            cur.execute(sql, (project_id, project_id))
            rows = cur.fetchall()
        return [row[0] for row in rows if row[0]]
    except Exception as e:
        _logger.warning("code_normalization.get_existing_failed", error=str(e))
        return []
