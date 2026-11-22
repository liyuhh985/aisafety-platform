"""Metadata-only Skill registry with on-demand Markdown body loading."""
from dataclasses import asdict, dataclass
from pathlib import Path
import re

import yaml

from core.hazard_taxonomy import MAJOR_LABELS


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    category: str
    description: str
    allowed_tools: tuple[str, ...]
    routing_keywords: tuple[str, ...]
    version: str
    body_path: Path


class SkillRegistry:
    def __init__(self, skills_dir, valid_tool_names):
        self.skills_dir = Path(skills_dir).resolve()
        self.valid_tool_names = set(valid_tool_names or ())
        self._metadata: dict[str, SkillMetadata] = {}

    def scan_metadata(self):
        """Parse frontmatter only; do not retain full Markdown bodies."""
        loaded: dict[str, SkillMetadata] = {}
        for path in sorted(self.skills_dir.glob("*/SKILL.md")):
            path = path.resolve()
            try:
                path.relative_to(self.skills_dir)
            except ValueError as exc:
                raise ValueError(f"skill path escapes root: {path}") from exc
            text = path.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) != 3 or not parts[2].strip():
                raise ValueError(f"invalid SKILL.md body: {path}")
            try:
                meta = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"invalid SKILL.md frontmatter: {path}: {exc}") from exc
            if not isinstance(meta, dict):
                raise ValueError(f"invalid SKILL.md frontmatter: {path}")

            code = str(meta.get("category") or "").strip()
            name = str(meta.get("name") or "").strip()
            if not code or code not in MAJOR_LABELS:
                raise ValueError(f"invalid category {code!r}: {path}")
            if name != path.parent.name or code != path.parent.name:
                raise ValueError(f"name/category mismatch: {path}")
            if code in loaded:
                raise ValueError(f"duplicate category {code}: {path}")
            description = str(meta.get("description") or "").strip()
            if not description:
                raise ValueError(f"missing description: {path}")

            tools = tuple(str(item).strip() for item in (meta.get("allowed_tools") or []))
            unknown = set(tools) - self.valid_tool_names
            if unknown:
                raise ValueError(f"unknown tools for {code}: {sorted(unknown)}")
            keywords = tuple(
                str(item).strip()
                for item in (meta.get("routing_keywords") or [])
                if str(item).strip()
            )
            loaded[code] = SkillMetadata(
                name=name,
                category=code,
                description=description,
                allowed_tools=tools,
                routing_keywords=keywords,
                version=str(meta.get("version") or "1"),
                body_path=path,
            )
        self._metadata = loaded

    def get_metadata(self, category):
        return asdict(self._metadata[category])

    def load_body(self, category):
        meta = self._metadata[category]
        text = meta.body_path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) != 3 or not parts[2].strip():
            raise ValueError(f"invalid SKILL.md body: {meta.body_path}")
        return parts[2].strip()

    def load_section(self, category, heading):
        body = self.load_body(category)
        marker = f"## {heading}"
        if marker not in body:
            raise KeyError(f"missing section {heading!r} in {category}")
        section = body.split(marker, 1)[1]
        section = re.split(r"\r?\n## ", section, maxsplit=1)[0]
        return section.strip()

    def resolve_tools(self, categories):
        names = []
        for category in categories or []:
            meta = self._metadata.get(category)
            if not meta:
                continue
            for name in meta.allowed_tools:
                if name not in names:
                    names.append(name)
        return names

    def metadata_catalog(self):
        return [
            {
                "category": item.category,
                "description": item.description,
                "routing_keywords": list(item.routing_keywords),
            }
            for item in self._metadata.values()
        ]

    def versions_for(self, categories):
        return {
            code: self._metadata[code].version
            for code in (categories or [])
            if code in self._metadata
        }


def get_skill_registry(skills_dir, valid_tool_names):
    registry = SkillRegistry(skills_dir, valid_tool_names)
    registry.scan_metadata()
    return registry