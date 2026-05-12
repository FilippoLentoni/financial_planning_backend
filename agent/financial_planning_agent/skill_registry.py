from __future__ import annotations

from pathlib import Path
from typing import Any


def skill_files(base_dir: Path | None = None) -> list[Path]:
    root = base_dir or Path(__file__).parent
    return sorted((root / "skills").glob("*/SKILL.md"))


def parse_skill_frontmatter(skill_file: Path, base_dir: Path | None = None) -> dict[str, Any]:
    text = skill_file.read_text(encoding="utf-8")
    root = base_dir or Path(__file__).parent
    metadata: dict[str, Any] = {
        "name": skill_file.parent.name,
        "description": "",
        "allowedTools": [],
        "path": str(skill_file.relative_to(root)),
    }
    if not text.startswith("---"):
        return metadata

    end = text.find("\n---", 3)
    if end == -1:
        return metadata

    current_key = ""
    for raw_line in text[3:end].splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key == "allowed-tools":
            metadata["allowedTools"].append(line[4:].strip())
            continue
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            current_key = key.strip()
            if current_key == "allowed-tools":
                metadata["allowedTools"] = []
            elif current_key == "name":
                metadata["name"] = value.strip()
            elif current_key == "description":
                metadata["description"] = value.strip()
    return metadata


def loaded_skills(base_dir: Path | None = None) -> list[dict[str, Any]]:
    root = base_dir or Path(__file__).parent
    return [parse_skill_frontmatter(skill_file, root) for skill_file in skill_files(root)]


def load_skill_instructions(base_dir: Path | None = None) -> str:
    root = base_dir or Path(__file__).parent
    return "\n\n".join(skill_file.read_text(encoding="utf-8") for skill_file in skill_files(root))
