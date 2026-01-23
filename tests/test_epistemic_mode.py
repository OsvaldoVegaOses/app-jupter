"""Tests for TICKET-EM01 (Schema + Config) and TICKET-EM02 (Prompts + Loader).

These tests verify the epistemic mode implementation without requiring
database connections by checking source code structure and file existence.
"""
import pytest
from pathlib import Path


# =============================================================================
# TICKET-EM01: Schema + Config Tests
# =============================================================================

class TestEpistemicModeEnum:
    """Tests for EpistemicMode enum in settings.py."""
    
    def test_enum_exists_in_settings(self):
        """EpistemicMode enum should be defined in settings.py."""
        settings_path = Path(__file__).parent.parent / "app" / "settings.py"
        source = settings_path.read_text(encoding="utf-8")
        
        assert "class EpistemicMode" in source
        assert "str, Enum" in source
    
    def test_enum_has_both_values(self):
        """EpistemicMode should have CONSTRUCTIVIST and POST_POSITIVIST values."""
        settings_path = Path(__file__).parent.parent / "app" / "settings.py"
        source = settings_path.read_text(encoding="utf-8")
        
        assert 'CONSTRUCTIVIST = "constructivist"' in source
        assert 'POST_POSITIVIST = "post_positivist"' in source
    
    def test_from_string_method_exists(self):
        """EpistemicMode should have from_string classmethod."""
        settings_path = Path(__file__).parent.parent / "app" / "settings.py"
        source = settings_path.read_text(encoding="utf-8")
        
        assert "def from_string" in source
        assert "cls.CONSTRUCTIVIST" in source  # Default fallback
    
    def test_enum_can_be_imported(self):
        """EpistemicMode should be importable."""
        from app.settings import EpistemicMode
        
        assert EpistemicMode.CONSTRUCTIVIST.value == "constructivist"
        assert EpistemicMode.POST_POSITIVIST.value == "post_positivist"
    
    def test_from_string_with_valid_value(self):
        """from_string should parse valid values."""
        from app.settings import EpistemicMode
        
        assert EpistemicMode.from_string("constructivist") == EpistemicMode.CONSTRUCTIVIST
        assert EpistemicMode.from_string("post_positivist") == EpistemicMode.POST_POSITIVIST
    
    def test_from_string_with_invalid_value(self):
        """from_string should return CONSTRUCTIVIST for invalid values."""
        from app.settings import EpistemicMode
        
        assert EpistemicMode.from_string("invalid") == EpistemicMode.CONSTRUCTIVIST
        assert EpistemicMode.from_string(None) == EpistemicMode.CONSTRUCTIVIST
        assert EpistemicMode.from_string("") == EpistemicMode.CONSTRUCTIVIST


class TestPostgresBlockFunctions:
    """Tests for epistemic mode functions in postgres_block.py."""
    
    def test_get_project_epistemic_mode_exists(self):
        """get_project_epistemic_mode should be defined."""
        pg_block_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_block_path.read_text(encoding="utf-8")
        
        assert "def get_project_epistemic_mode(" in source
        assert "EpistemicMode" in source
    
    def test_set_project_epistemic_mode_exists(self):
        """set_project_epistemic_mode should be defined with lock logic."""
        pg_block_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_block_path.read_text(encoding="utf-8")
        
        assert "def set_project_epistemic_mode(" in source
        assert "axial_relationships" in source  # Lock check
        assert "Cannot change epistemic_mode" in source
    
    def test_has_axial_relations_exists(self):
        """has_axial_relations helper should be defined."""
        pg_block_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_block_path.read_text(encoding="utf-8")
        
        assert "def has_axial_relations(" in source
    
    def test_get_project_db_includes_epistemic_mode(self):
        """get_project_db should SELECT and return epistemic_mode."""
        pg_block_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_block_path.read_text(encoding="utf-8")
        
        # Check that epistemic_mode is in the SELECT
        assert "epistemic_mode" in source
        assert '"epistemic_mode":' in source  # In return dict
    
    def test_list_projects_db_includes_epistemic_mode(self):
        """list_projects_db should include epistemic_mode."""
        pg_block_path = Path(__file__).parent.parent / "app" / "postgres_block.py"
        source = pg_block_path.read_text(encoding="utf-8")
        
        # Find list_projects_db function and check it includes epistemic_mode
        assert "SELECT id, name, description, org_id, owner_id, config, created_at, updated_at, epistemic_mode" in source


class TestMigration:
    """Tests for migration 017."""
    
    def test_migration_file_exists(self):
        """Migration 017_epistemic_mode.sql should exist."""
        migration_path = Path(__file__).parent.parent / "migrations" / "017_epistemic_mode.sql"
        assert migration_path.exists(), "Migration file 017_epistemic_mode.sql not found"
    
    def test_migration_has_alter_table(self):
        """Migration should ALTER TABLE proyectos."""
        migration_path = Path(__file__).parent.parent / "migrations" / "017_epistemic_mode.sql"
        source = migration_path.read_text(encoding="utf-8")
        
        assert "ALTER TABLE proyectos" in source
        assert "epistemic_mode" in source
    
    def test_migration_has_check_constraint(self):
        """Migration should have CHECK constraint for valid values."""
        migration_path = Path(__file__).parent.parent / "migrations" / "017_epistemic_mode.sql"
        source = migration_path.read_text(encoding="utf-8")
        
        assert "CHECK" in source
        assert "constructivist" in source
        assert "post_positivist" in source
    
    def test_migration_has_default(self):
        """Migration should default to constructivist."""
        migration_path = Path(__file__).parent.parent / "migrations" / "017_epistemic_mode.sql"
        source = migration_path.read_text(encoding="utf-8")
        
        assert "DEFAULT 'constructivist'" in source


# =============================================================================
# TICKET-EM02: Prompts + Loader Tests
# =============================================================================

class TestPromptsStructure:
    """Tests for prompts directory structure."""
    
    def test_prompts_directory_exists(self):
        """app/prompts/ directory should exist."""
        prompts_dir = Path(__file__).parent.parent / "app" / "prompts"
        assert prompts_dir.exists(), "app/prompts/ directory not found"
        assert prompts_dir.is_dir()
    
    def test_loader_module_exists(self):
        """loader.py should exist in prompts/."""
        loader_path = Path(__file__).parent.parent / "app" / "prompts" / "loader.py"
        assert loader_path.exists(), "app/prompts/loader.py not found"
    
    def test_constructivist_directory_exists(self):
        """constructivist/ subdirectory should exist."""
        dir_path = Path(__file__).parent.parent / "app" / "prompts" / "constructivist"
        assert dir_path.exists(), "app/prompts/constructivist/ not found"
    
    def test_post_positivist_directory_exists(self):
        """post_positivist/ subdirectory should exist."""
        dir_path = Path(__file__).parent.parent / "app" / "prompts" / "post_positivist"
        assert dir_path.exists(), "app/prompts/post_positivist/ not found"


class TestConstructivistTemplates:
    """Tests for constructivist prompt templates."""
    
    REQUIRED_FILES = [
        "system_base.txt",
        "open_coding.txt", 
        "axial_coding.txt",
        "discovery.txt",
        "selective.txt",
        "memo.txt",
    ]
    
    def test_all_templates_exist(self):
        """All required template files should exist."""
        base_dir = Path(__file__).parent.parent / "app" / "prompts" / "constructivist"
        
        for filename in self.REQUIRED_FILES:
            file_path = base_dir / filename
            assert file_path.exists(), f"Missing template: constructivist/{filename}"
    
    def test_open_coding_mentions_gerundio(self):
        """Constructivist open_coding should mention gerundios."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "constructivist" / "open_coding.txt"
        content = file_path.read_text(encoding="utf-8").lower()
        
        assert "gerundio" in content, "Constructivist open_coding should emphasize gerundios"
    
    def test_open_coding_mentions_in_vivo(self):
        """Constructivist open_coding should mention in-vivo coding."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "constructivist" / "open_coding.txt"
        content = file_path.read_text(encoding="utf-8").lower()
        
        assert "in-vivo" in content or "in_vivo" in content, "Constructivist should emphasize in-vivo codes"
    
    def test_system_base_mentions_charmaz(self):
        """Constructivist system_base should reference Charmaz."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "constructivist" / "system_base.txt"
        content = file_path.read_text(encoding="utf-8")
        
        assert "Charmaz" in content, "Constructivist should reference Charmaz"
    
    def test_memo_is_reflexivo(self):
        """Constructivist memo should be reflexivo."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "constructivist" / "memo.txt"
        content = file_path.read_text(encoding="utf-8").lower()
        
        assert "reflexiv" in content, "Constructivist memo should emphasize reflexivity"


class TestPostPositivistTemplates:
    """Tests for post-positivist prompt templates."""
    
    REQUIRED_FILES = [
        "system_base.txt",
        "open_coding.txt",
        "axial_coding.txt", 
        "discovery.txt",
        "selective.txt",
        "memo.txt",
    ]
    
    def test_all_templates_exist(self):
        """All required template files should exist."""
        base_dir = Path(__file__).parent.parent / "app" / "prompts" / "post_positivist"
        
        for filename in self.REQUIRED_FILES:
            file_path = base_dir / filename
            assert file_path.exists(), f"Missing template: post_positivist/{filename}"
    
    def test_open_coding_mentions_sustantivo(self):
        """Post-positivist open_coding should mention sustantivos."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "post_positivist" / "open_coding.txt"
        content = file_path.read_text(encoding="utf-8").lower()
        
        assert "sustantivo" in content, "Post-positivist open_coding should emphasize sustantivos"
    
    def test_open_coding_mentions_abstraccion(self):
        """Post-positivist open_coding should mention abstraction."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "post_positivist" / "open_coding.txt"
        content = file_path.read_text(encoding="utf-8").lower()
        
        assert "abstrac" in content, "Post-positivist should emphasize abstraction"
    
    def test_system_base_mentions_glaser_strauss(self):
        """Post-positivist system_base should reference Glaser/Strauss."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "post_positivist" / "system_base.txt"
        content = file_path.read_text(encoding="utf-8")
        
        assert "Glaser" in content or "Strauss" in content, "Post-positivist should reference Glaser/Strauss"
    
    def test_axial_has_paradigm(self):
        """Post-positivist axial should mention paradigm."""
        file_path = Path(__file__).parent.parent / "app" / "prompts" / "post_positivist" / "axial_coding.txt"
        content = file_path.read_text(encoding="utf-8").lower()
        
        assert "paradigma" in content or "paradigm" in content, "Post-positivist axial should use paradigmatic approach"


class TestPromptLoader:
    """Tests for prompt loader functionality."""
    
    def test_loader_has_stage_to_file_mapping(self):
        """Loader should have STAGE_TO_FILE mapping."""
        loader_path = Path(__file__).parent.parent / "app" / "prompts" / "loader.py"
        source = loader_path.read_text(encoding="utf-8")
        
        assert "STAGE_TO_FILE" in source
        assert "open_coding" in source
        assert "axial_coding" in source
    
    def test_loader_has_load_prompt_function(self):
        """Loader should have load_prompt function."""
        loader_path = Path(__file__).parent.parent / "app" / "prompts" / "loader.py"
        source = loader_path.read_text(encoding="utf-8")
        
        assert "def load_prompt(" in source
        assert "lru_cache" in source  # Should use caching
    
    def test_loader_has_get_system_prompt_function(self):
        """Loader should have get_system_prompt function."""
        loader_path = Path(__file__).parent.parent / "app" / "prompts" / "loader.py"
        source = loader_path.read_text(encoding="utf-8")
        
        assert "def get_system_prompt(" in source
    
    def test_loader_has_fallback_logging(self):
        """Loader should log warnings on fallback."""
        loader_path = Path(__file__).parent.parent / "app" / "prompts" / "loader.py"
        source = loader_path.read_text(encoding="utf-8")
        
        assert "prompt.fallback" in source
        assert "_logger.warning" in source
    
    def test_loader_can_be_imported(self):
        """Loader module should be importable."""
        from app.prompts.loader import load_prompt, get_system_prompt, STAGE_TO_FILE
        
        assert callable(load_prompt)
        assert callable(get_system_prompt)
        assert isinstance(STAGE_TO_FILE, dict)
    
    def test_load_prompt_returns_tuple(self):
        """load_prompt should return (text, version) tuple."""
        from app.prompts.loader import load_prompt, clear_prompt_cache
        from app.settings import EpistemicMode
        
        clear_prompt_cache()  # Ensure fresh load
        text, version = load_prompt(EpistemicMode.CONSTRUCTIVIST, "open_coding")
        
        assert isinstance(text, str)
        assert len(text) > 100  # Should have substantial content
        assert isinstance(version, str)
        assert "constructivist" in version
        assert "open_coding" in version
    
    def test_get_system_prompt_combines_base_and_stage(self):
        """get_system_prompt should combine base + stage prompts."""
        from app.prompts.loader import get_system_prompt, clear_prompt_cache
        from app.settings import EpistemicMode
        
        clear_prompt_cache()
        combined, version = get_system_prompt(EpistemicMode.CONSTRUCTIVIST, "open_coding")
        
        # Should contain content from both base and stage
        assert "Charmaz" in combined  # From system_base
        assert "gerundio" in combined.lower()  # From open_coding
        assert "+" in version  # Combined version format


class TestDifferentiationBetweenModes:
    """Tests verifying actual differentiation between modes."""
    
    def test_open_coding_differs_between_modes(self):
        """open_coding prompts should differ between modes."""
        from app.prompts.loader import load_prompt, clear_prompt_cache
        from app.settings import EpistemicMode
        
        clear_prompt_cache()
        
        const_text, _ = load_prompt(EpistemicMode.CONSTRUCTIVIST, "open_coding")
        post_text, _ = load_prompt(EpistemicMode.POST_POSITIVIST, "open_coding")
        
        # They should be different
        assert const_text != post_text
        
        # Constructivist emphasizes gerundios
        assert "gerundio" in const_text.lower()
        # Post-positivist emphasizes sustantivos
        assert "sustantivo" in post_text.lower()
    
    def test_system_base_differs_between_modes(self):
        """system_base prompts should differ between modes."""
        from app.prompts.loader import load_prompt, clear_prompt_cache
        from app.settings import EpistemicMode
        
        clear_prompt_cache()
        
        const_text, _ = load_prompt(EpistemicMode.CONSTRUCTIVIST, "system_base")
        post_text, _ = load_prompt(EpistemicMode.POST_POSITIVIST, "system_base")
        
        assert const_text != post_text
        assert "Charmaz" in const_text
        assert "Glaser" in post_text or "Strauss" in post_text


# =============================================================================
# TICKET-EM03: Integration in analysis.py Tests
# =============================================================================

class TestAnalysisIntegration:
    """Tests for epistemic mode integration in analysis.py."""
    
    def test_analysis_imports_epistemic_mode(self):
        """analysis.py should import EpistemicMode and related functions."""
        analysis_path = Path(__file__).parent.parent / "app" / "analysis.py"
        source = analysis_path.read_text(encoding="utf-8")
        
        assert "from .settings import AppSettings, EpistemicMode" in source
        assert "from .prompts.loader import get_system_prompt" in source
        assert "get_project_epistemic_mode" in source
    
    def test_analyze_interview_text_uses_epistemic_mode(self):
        """analyze_interview_text should use epistemic mode for prompt selection."""
        analysis_path = Path(__file__).parent.parent / "app" / "analysis.py"
        source = analysis_path.read_text(encoding="utf-8")
        
        # Should get epistemic mode from project
        assert "epistemic_mode = get_project_epistemic_mode" in source or \
               "get_project_epistemic_mode(clients.pg, project_id)" in source
        
        # Should get differentiated prompt
        assert "get_system_prompt(epistemic_mode" in source
    
    def test_analyze_interview_text_has_meta_output(self):
        """analyze_interview_text should include _meta in output."""
        analysis_path = Path(__file__).parent.parent / "app" / "analysis.py"
        source = analysis_path.read_text(encoding="utf-8")
        
        assert 'out["_meta"]' in source
        assert '"epistemic_mode"' in source
        assert '"prompt_version"' in source
    
    def test_cognitive_metadata_includes_epistemic_mode(self):
        """cognitive_metadata should include epistemic_mode."""
        analysis_path = Path(__file__).parent.parent / "app" / "analysis.py"
        source = analysis_path.read_text(encoding="utf-8")
        
        assert '"epistemic_mode": epistemic_mode.value' in source
    
    def test_analysis_logs_epistemic_mode(self):
        """analysis.py should log epistemic_mode on start."""
        analysis_path = Path(__file__).parent.parent / "app" / "analysis.py"
        source = analysis_path.read_text(encoding="utf-8")
        
        assert "analysis.started" in source
        assert "epistemic_mode=" in source
    
    def test_analysis_has_fallback_to_default_prompt(self):
        """analysis.py should fallback to QUAL_SYSTEM_PROMPT if load fails."""
        analysis_path = Path(__file__).parent.parent / "app" / "analysis.py"
        source = analysis_path.read_text(encoding="utf-8")
        
        assert "QUAL_SYSTEM_PROMPT" in source  # Fallback prompt should still exist
        assert "epistemic_mode.load_failed" in source  # Warning log for fallback
