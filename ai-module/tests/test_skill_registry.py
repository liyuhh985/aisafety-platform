from pathlib import Path

from core.hazard_taxonomy import MAJOR_LABELS

SKILL_ROOT = Path(__file__).parents[1] / "skills"


def test_all_major_skills_exist():
    for code in MAJOR_LABELS:
        assert (SKILL_ROOT / code / "SKILL.md").is_file(), code
from pathlib import Path
import pytest
from core.skill_registry import SkillRegistry


def _write_skill(root: Path, code: str, **extra):
    path = root / code / "SKILL.md"
    path.parent.mkdir(parents=True)
    front = {
        "name": code,
        "category": code,
        "description": f"{code} description",
        "version": "1",
    }
    front.update(extra)
    lines = ["---"]
    for key, value in front.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["---", f"# {code}", "## 报告约束", f"{code} report rule"])
    path.write_text("\n".join(lines), encoding="utf-8")


def test_scan_and_load(tmp_path):
    _write_skill(tmp_path, "fire", allowed_tools=["search_cases"])
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    registry.scan_metadata()
    assert registry.get_metadata("fire")["category"] == "fire"
    assert "## 报告约束" not in registry.get_metadata("fire")
    assert "fire report rule" in registry.load_section("fire", "报告约束")


def test_duplicate_category_fails(tmp_path):
    _write_skill(tmp_path, "fire")
    _write_skill(tmp_path, "fire_copy", category="fire")
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    with pytest.raises(ValueError, match="duplicate"):
        registry.scan_metadata()


def test_invalid_category_fails(tmp_path):
    _write_skill(tmp_path, "fire_copy", category="not_a_hazard")
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    with pytest.raises(ValueError, match="category"):
        registry.scan_metadata()


def test_unknown_tool_fails(tmp_path):
    _write_skill(tmp_path, "fire", allowed_tools=["unknown_tool"])
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    with pytest.raises(ValueError, match="unknown tools"):
        registry.scan_metadata()


def test_scan_does_not_cache_body_text(tmp_path):
    _write_skill(tmp_path, "fire", allowed_tools=["search_cases"])
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    registry.scan_metadata()
    assert "fire report rule" not in repr(registry.get_metadata("fire"))
    assert not hasattr(registry, "_body_cache")
def test_canonical_skills_scan_with_real_registry():
    from core.skill_registry import SkillRegistry
    registry = SkillRegistry(
        SKILL_ROOT,
        valid_tool_names={"search_regulation", "search_cases"},
    )
    registry.scan_metadata()
    assert len(registry.metadata_catalog()) == 8
    assert registry.get_metadata("fire")["version"] == "1"
    assert "消防通道" in registry.get_metadata("fire")["routing_keywords"]
    assert {"search_regulation", "search_cases"} <= set(registry.resolve_tools(["fire"]))