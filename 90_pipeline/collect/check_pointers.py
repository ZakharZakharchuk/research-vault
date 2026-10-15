#!/usr/bin/env python3
"""Пошук розсинхронів, які не видно жодною окремою перевіркою.

Усе, що цей скрипт шукає, на практиці знаходиться очима, а не інструментом,
і саме тому — пізно:

1. **Вказівник на файл, з якого зміст переїхав.** Нотатки посилаються на
   калібрувальні факти в `CLAUDE.md`, хоча їхнє місце — `00_admin/facts.md`.
   Файл існує, посилання виглядає справним — але веде не туди.
2. **Два написання однієї сутності.** Хаби `tokenization` і `tokenisation`
   живуть паралельно й ділять backlinks навпіл, через що жоден не виглядає
   важливим.
3. **Висячі `[[@citekey]]`** — посилання на роботу, якої немає в `library.bib`.

Перевірки навмисно окремі від `lint_notes.py` (той дивиться на одну нотатку)
і від `sync_headers.py` (той дивиться на шапки й хаби). Тут — звʼязки **між**
файлами сховища.

    python 90_pipeline/collect/check_pointers.py .

Код виходу 1, якщо є хоч одна знахідка — щоб можна було чіпляти в pre-commit.
"""

import re
import sys
from pathlib import Path

# Файли, зміст яких переїхав. {куди-не-можна-посилатись: (куди-треба, з-якої-дати)}
MOVED = {
    "CLAUDE.md": ("00_admin/facts.md", "калібрувальні факти й архітектурна лінія живуть у facts.md"),
}
# Рядки, за яких згадка перенесеного файлу законна (посилання на решту його змісту)
MOVED_OK = ("git", "коміт", "push", "стиль", "конвеєр", "середовищ", "переїхал", "розд. Git")

CITE = re.compile(r"\[\[@([^\]|#]+)\]\]")
# плейсхолдери в шаблонах і довідках — не висячі посилання
CITE_PLACEHOLDERS = {"citekey", "ключ", "key"}
HUB = re.compile(r"\[\[([^\]|#@]+)\]\]")
MD_MENTION = re.compile(r"`([\w./-]+\.md)`")


def norm_hub(name):
    """Написання, що мають вважатись одним і тим самим хабом."""
    s = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    s = s.replace("rumour", "rumor").replace("colour", "color").replace("behaviour", "behavior").replace("isation", "ization")
    s = s.replace("analyse", "analyze").replace("modelling", "modeling")
    return s


def bib_keys(path):
    if not path.exists():
        return set()
    return set(re.findall(r"@\w+\{([^,]+),", path.read_text(encoding="utf-8", errors="replace")))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    notes_dir = root / "10_literature" / "notes"
    hubs_dir = root / "10_literature" / "hubs"
    keys = bib_keys(root / "00_admin" / "library.bib")

    scanned = sorted(list(notes_dir.glob("*.md")) + list(hubs_dir.glob("*.md")))
    findings = 0

    # ── 1. вказівники на переїхалий зміст
    print("Вказівники на переїхалий зміст\n" + "─" * 30)
    hits = 0
    for p in scanned:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for bad, (good, why) in MOVED.items():
                if bad not in line:
                    continue
                if any(w.lower() in line.lower() for w in MOVED_OK):
                    continue
                hits += 1
                print(f"  {p.name}:{i} → `{bad}` замінити на `{good}`")
                print(f"      ({why})")
    print("  чисто" if not hits else f"  знахідок: {hits}")
    findings += hits

    # ── 2. згадки .md-файлів, яких немає
    print("\nЗгадки файлів, яких немає у сховищі\n" + "─" * 35)
    hits = 0
    existing = {p.name for p in root.rglob("*.md") if ".git" not in p.parts and "_to_delete" not in p.parts}
    for p in scanned:
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for mention in MD_MENTION.findall(line):
                if Path(mention).name not in existing:
                    hits += 1
                    print(f"  {p.name}:{i} → `{mention}`")
    print("  чисто" if not hits else f"  знахідок: {hits}")
    findings += hits

    # ── 3. варіанти написання хабів
    print("\nВаріанти написання однієї сутності\n" + "─" * 34)
    groups = {}
    used = {}
    for p in hubs_dir.glob("*.md"):
        if p.stem.startswith("_"):
            continue
        groups.setdefault(norm_hub(p.stem), []).append(p.stem)
    for p in notes_dir.glob("@*.md"):
        for name in HUB.findall(p.read_text(encoding="utf-8")):
            used.setdefault(name, set()).add(p.stem)
            groups.setdefault(norm_hub(name), [])
            if name not in groups[norm_hub(name)]:
                groups[norm_hub(name)].append(name)
    hits = 0
    for _, variants in sorted(groups.items()):
        if len(variants) > 1:
            hits += 1
            detail = ", ".join(f"{v} ({len(used.get(v, ()))} backlinks)" for v in sorted(variants))
            print(f"  {detail}")
    print("  чисто" if not hits else
          f"  знахідок: {hits} — звести до одного написання за конвенцією hubs/_hubs.md")
    findings += hits

    # ── 4. висячі посилання на роботи
    print("\nПосилання на роботи поза library.bib\n" + "─" * 36)
    hits = 0
    for p in scanned:
        dangling = sorted({k for k in CITE.findall(p.read_text(encoding="utf-8"))
                           if k not in keys and k not in CITE_PLACEHOLDERS})
        if dangling:
            hits += len(dangling)
            print(f"  {p.name}: {', '.join('@' + d for d in dangling)}")
    print("  чисто" if not hits else f"  знахідок: {hits} — або додати запис у .bib, або прибрати лінк")
    findings += hits

    print(f"\nразом знахідок: {findings}")
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
