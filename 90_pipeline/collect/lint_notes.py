#!/usr/bin/env python3
"""Лінтер літературних нотаток.

Ловить клас помилок, який Obsidian не показує, а Dataview мовчки проковтує:
нотатка з непарсабельним YAML **зникає з усіх таблиць** `_matrix.md`, і зовні
це виглядає так, ніби джерела просто немає.

Перевіряє:
  * front matter парситься як YAML;
  * citekey збігається з іменем файлу;
  * статус із дозволеного набору;
  * обов'язкові поля наявні;
  * для `summarized` заповнені summary, key_finding, task, metrics;
  * хаб-посилання [[...]] існують у 10_literature/hubs/ (як попередження);
  * `verified_by_human` — булеве.

Використання:
    python lint_notes.py <notes/> [<hubs/>]
Код повернення 1, якщо є помилки.
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("потрібен pyyaml:  pip install pyyaml")

STATUSES = {"imported", "summarized", "verified", "abstract-only"}
REQUIRED = ["citekey", "title", "year", "status", "verified_by_human"]
NEED_FILLED = ["summary", "key_finding", "task", "metrics", "relevance", "relevance_why"]
RELEVANCE = {"High", "Medium", "Low"}
HIGH_SHARE_LIMIT = 0.5  # орієнтир протоколу: ядро ≈ третина бази
LINK = re.compile(r"\[\[([^\]|#]+)")


def hub_names(hubs_dir):
    if not hubs_dir or not hubs_dir.is_dir():
        return None
    return {p.stem for p in hubs_dir.glob("*.md")}


def links_in(value):
    """Витягнути назви хабів із рядка або списку рядків."""
    items = value if isinstance(value, list) else [value]
    out = []
    for it in items:
        if isinstance(it, str):
            out += LINK.findall(it)
    return out


def check(path, hubs):
    errors, warnings = [], []
    text = path.read_text(encoding="utf-8")

    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return ["немає front matter"], []

    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        first = str(e).splitlines()[0]
        hint = ""
        if "double-quoted scalar" in str(e):
            hint = ("  ← ймовірно неекранований зворотний слеш у шляху; "
                    "у подвійних лапках потрібно \\\\")
        return [f"YAML не парситься: {first}{hint}"], []

    if not isinstance(meta, dict):
        return ["front matter не є словником"], []

    for f in REQUIRED:
        if f not in meta:
            errors.append(f"немає поля `{f}`")

    if meta.get("citekey") and f"@{meta['citekey']}.md" != path.name:
        errors.append(f"citekey `{meta['citekey']}` не збігається з іменем файлу")

    status = meta.get("status")
    if status not in STATUSES:
        errors.append(f"статус `{status}` поза конвеєром {sorted(STATUSES)}")

    if not isinstance(meta.get("verified_by_human"), bool):
        errors.append("`verified_by_human` має бути true/false")

    if status in {"summarized", "verified"}:
        for f in NEED_FILLED:
            if meta.get(f):
                continue
            # нотатку, яку людина вже звірила, не ламаємо заднім числом
            if f == "relevance_why" and meta.get("verified_by_human") is True:
                warnings.append("`relevance_why` не заповнене — дописати при наступному перегляді")
            else:
                errors.append(f"статус `{status}`, але `{f}` порожнє")

    rel = meta.get("relevance")
    if rel is not None and rel not in RELEVANCE:
        errors.append(f"`relevance` = `{rel}`, дозволено {sorted(RELEVANCE)}")
    if rel == "High" and status == "abstract-only":
        errors.append("`abstract-only` не може мати relevance High — відтворювати нема чого")

    why = meta.get("relevance_why")
    if why and len(str(why).split()) > 12:
        warnings.append(f"`relevance_why` довше за 12 слів ({len(str(why).split())})")
    if why and not str(why).strip():
        warnings.append("`relevance_why` порожнє після обрізання пробілів")

    if status in {"summarized", "verified"} and not meta.get("pdf"):
        warnings.append("проаналізовано без PDF — перевір, чи не має бути `abstract-only`")

    if hubs is not None:
        for field in ("task", "method", "datasets", "language"):
            for name in links_in(meta.get(field) or []):
                if name.startswith("@"):
                    continue
                if name not in hubs:
                    warnings.append(f"хаб `{name}` (поле {field}) не має файлу в hubs/")

    return errors, warnings


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    notes = Path(sys.argv[1])
    hubs = hub_names(Path(sys.argv[2])) if len(sys.argv) > 2 else None

    bad = 0
    tally = {"High": 0, "Medium": 0, "Low": 0}
    for path in sorted(notes.glob("@*.md")):
        m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
        if m:
            try:
                meta = yaml.safe_load(m.group(1)) or {}
                if meta.get("status") in {"summarized", "verified"}:
                    tally[meta.get("relevance")] = tally.get(meta.get("relevance"), 0) + 1
            except yaml.YAMLError:
                pass
        errors, warnings = check(path, hubs)
        if errors:
            bad += 1
            print(f"✗ {path.name}")
            for e in errors:
                print(f"    ПОМИЛКА: {e}")
            for w in warnings:
                print(f"    увага:   {w}")
        elif warnings:
            print(f"~ {path.name}")
            for w in warnings:
                print(f"    увага:   {w}")
        else:
            print(f"✓ {path.name}")

    print(f"\nнотаток: {len(list(notes.glob('@*.md')))}, з помилками: {bad}")

    graded = sum(v for k, v in tally.items() if k in RELEVANCE)
    if graded:
        parts = ", ".join(f"{k} {tally.get(k, 0)}" for k in ("High", "Medium", "Low"))
        share = tally.get("High", 0) / graded
        print(f"relevance серед опрацьованих ({graded}): {parts} — High {share:.0%}")
        if share > HIGH_SHARE_LIMIT:
            print("  увага: частка High перевищує половину. Орієнтир протоколу — "
                  "ядро 25–35 із 50–60, тобто близько третини. Перечитати relevance_why.")

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
