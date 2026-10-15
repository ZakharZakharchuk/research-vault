#!/usr/bin/env python3
"""Пакує скіли з цієї теки у файли для встановлення.

    python skills/build.py

Результат у skills/dist/:
    research-vault.plugin      — плагін для Claude Cowork: усі скіли одним файлом
    <skill>.zip              — окремі скіли для claude.ai → Settings → Capabilities → Skills

Запускати після кожної зміни SKILL.md і комітити dist/ разом зі зміною,
щоб друзі могли завантажити готові файли прямо з GitHub.
"""

import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
VERSION = "1.0.0"

MANIFEST = {
    "name": "research-vault",
    "version": VERSION,
    "description": "Конвеєр огляду літератури для дослідження (диплом, стаття, курсова, PhD): збір у Zotero, "
                   "нотатки в Obsidian, обслуговування бази, git і перше налаштування "
                   "сховища з шаблону research-vault.",
    "author": {"name": "research-vault"},
    "keywords": ["research", "literature-review", "zotero", "obsidian"],
}


def skills():
    return sorted(p.parent for p in HERE.glob("*/SKILL.md"))


def add_dir(zf, src, arc_prefix):
    for f in sorted(src.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            zf.write(f, f"{arc_prefix}/{f.relative_to(src).as_posix()}")


def main():
    DIST.mkdir(exist_ok=True)
    found = skills()
    # 1. Плагін: .claude-plugin/plugin.json + skills/<name>/...
    plugin = DIST / f"{MANIFEST['name']}.plugin"
    with zipfile.ZipFile(plugin, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(".claude-plugin/plugin.json", json.dumps(MANIFEST, ensure_ascii=False, indent=2))
        zf.write(HERE.parent / "README.md", "README.md")
        for s in found:
            add_dir(zf, s, f"skills/{s.name}")
    # 2. Окремі скіли: <name>.zip з текою <name>/SKILL.md всередині
    for s in found:
        with zipfile.ZipFile(DIST / f"{s.name}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
            add_dir(zf, s, s.name)
    print(f"{len(found)} скілів → {DIST}")
    for f in sorted(DIST.iterdir()):
        print(f"  {f.name:28} {f.stat().st_size:>7} B")


if __name__ == "__main__":
    main()
