"""Prompt loader with epistemic mode differentiation and audit trail.

This module provides functions to load prompt templates based on the
epistemic mode configured for a project. Templates are cached using LRU
cache and fallback to constructivist mode is logged for audit.

Usage:
    from app.prompts.loader import get_system_prompt
    from app.settings import EpistemicMode
    
    prompt, version = get_system_prompt(EpistemicMode.CONSTRUCTIVIST, "open_coding")
"""
from pathlib import Path
from functools import lru_cache
from typing import Tuple

import structlog

from app.settings import EpistemicMode


_logger = structlog.get_logger()
PROMPTS_DIR = Path(__file__).parent

# Mapping explícito stage → filename (cierra gap de naming)
STAGE_TO_FILE = {
    "system_base": "system_base.txt",
    "open_coding": "open_coding.txt",
    "axial_coding": "axial_coding.txt",
    "discovery": "discovery.txt",
    "selective": "selective.txt",
    "memo": "memo.txt",
}

# Valid stages for documentation
VALID_STAGES = tuple(STAGE_TO_FILE.keys())


@lru_cache(maxsize=32)
def load_prompt(mode: EpistemicMode, stage: str) -> Tuple[str, str]:
    """Load a prompt template for the given epistemic mode.
    
    Args:
        mode: EpistemicMode.CONSTRUCTIVIST or EpistemicMode.POST_POSITIVIST
        stage: "open_coding" | "axial_coding" | "discovery" | "selective" | "memo"
    
    Returns:
        Tuple[prompt_text, prompt_version]
        
    Raises:
        FileNotFoundError: if no prompt exists (even fallback)
    """
    filename = STAGE_TO_FILE.get(stage, f"{stage}.txt")
    mode_dir = PROMPTS_DIR / mode.value
    prompt_file = mode_dir / filename
    
    # Intento primario
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8")
        version = f"{mode.value}_{stage}_v1"
        return text, version
    
    # Fallback a constructivista con warning auditado
    fallback_file = PROMPTS_DIR / "constructivist" / filename
    if fallback_file.exists():
        _logger.warning(
            "prompt.fallback",
            requested_mode=mode.value,
            stage=stage,
            fallback_to="constructivist",
            reason="prompt_file_missing",
        )
        text = fallback_file.read_text(encoding="utf-8")
        version = f"fallback_constructivist_{stage}_v1"
        return text, version
    
    raise FileNotFoundError(f"No prompt found for stage '{stage}' in any mode")


def get_system_prompt(mode: EpistemicMode, stage: str) -> Tuple[str, str]:
    """Build complete system prompt combining base + stage-specific.
    
    Args:
        mode: EpistemicMode
        stage: "open_coding" | "axial_coding" | "discovery" | "selective"
    
    Returns:
        Tuple[complete_prompt, prompt_version]
    """
    base_text, base_version = load_prompt(mode, "system_base")
    stage_text, stage_version = load_prompt(mode, stage)
    
    combined = f"{base_text}\n\n---\n\n{stage_text}"
    version = f"{base_version}+{stage_version}"
    
    return combined, version


def clear_prompt_cache() -> None:
    """Clear the LRU cache for prompt loading (useful for testing)."""
    load_prompt.cache_clear()
