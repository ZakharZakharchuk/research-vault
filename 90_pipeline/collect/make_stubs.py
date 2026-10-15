#!/usr/bin/env python3
"""Генератор заготовок літературних нотаток із library.bib.

Створює у 10_literature/notes/ файли @<citekey>.md зі статусом `imported`:
метадані з .bib + підстава включення з тріажу. Аналітичні поля лишаються
порожніми — їх заповнює Stage 2 (скіл litnote-summarize) після читання PDF.

Наявні файли НЕ перезаписуються.

Підстава включення (RQ, пріоритет, примітка) береться з таблиць «Включено»
журналу скринінгу 90_pipeline/out/screening.md.

Використання (з кореня сховища):
    python 90_pipeline/collect/make_stubs.py 00_admin/library.bib 10_literature/notes [screening.md] [--dry-run]
"""

import re
import sys
from pathlib import Path

# Підстави включення беруться з журналу скринінгу 90_pipeline/out/screening.md:
# з усіх таблиць, у заголовку яких є колонки «Citekey», «RQ» і «Пріоритет».
# Рядок: | `citekey` | ... | RQ1, RQ2 | High | ... | Примітка |
# Колонка «Примітка» (або остання) стає обґрунтуванням у заготовці.


def load_triage(screening_path):
    """{citekey: (RQ, пріоритет, обґрунтування, дата_хвилі)} з таблиць «Включено»."""
    triage = {}
    if not screening_path.exists():
        return triage
    header, wave = None, ""
    for line in screening_path.read_text(encoding="utf-8").splitlines():
        h = re.match(r"#+\s.*?(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})", line)
        if h and line.startswith("## "):
            wave = h.group(1)
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        low = [c.lower().strip("*` ") for c in cells]
        if "citekey" in low and "rq" in low and any(c.startswith("пріоритет") for c in low):
            header = low
            continue
        if header is None or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        key = re.search(r"`([^`]+)`", row.get("citekey", ""))
        if not key:
            continue
        prio = next((v for k, v in row.items() if k.startswith("пріоритет")), "")
        why = row.get("примітка") or cells[-1]
        triage[key.group(1)] = (row.get("rq", ""), prio.strip("* "), why, wave)
    return triage


TEMPLATE = """---
citekey: "{citekey}"
title: "{title}"
authors: "{authors}"
year: {year}
venue: "{venue}"
doi: "{doi}"
zotero: "{zotero}"
pdf: "{pdf}"
status: imported
summary: ""
key_finding: ""
task:
method: []
datasets: []
language: []
metrics: ""
code: ""
relevance:
relevance_why: ""
cites: []
tags: [{tags}]
verified_by_human: false
---

> [!info] Статус: `imported`
> Метадані з Zotero. Аналітичні поля порожні — заповнюються на Stage 2.
{screening}
## Що зроблено

## Метод

## Дані

## Результати

## Обмеження

## Релевантність для моєї роботи

## Цитати

## Мої нотатки
"""


def clean(s):
    """Прибрати службові дужки BibTeX, розекранувати LaTeX, стиснути пробіли."""
    s = re.sub(r"[{}]", "", s)
    # BibTeX екранує & % _ # $ зворотним слешем; у YAML такий слеш ламає рядок
    s = re.sub(r"\\([&%_#$])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def q(s):
    """Безпечний скаляр YAML у подвійних лапках."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def fmt_authors(raw):
    """«Cheng, Mingxi and Wang, Songli» -> «Cheng M., Wang S.»"""
    out = []
    for person in clean(raw).split(" and "):
        if "," in person:
            last, first = person.split(",", 1)
            initials = " ".join(p[0] + "." for p in first.split() if p)
            out.append(f"{last.strip()} {initials}".strip())
        else:
            out.append(person.strip())
    return ", ".join(out)


def parse_bib(text):
    """Розбити .bib на записи -> {citekey: {поле: значення}}."""
    entries = {}
    for chunk in re.split(r"\n(?=@)", text):
        head = re.match(r"@(\w+)\{([^,]+),", chunk)
        if not head:
            continue
        fields = {}
        for m in re.finditer(r"\n\s*(\w+)\s*=\s*(\{.*?\}|[^,\n]+),?\s*(?=\n\s*\w+\s*=|\n\})",
                             chunk, re.S):
            fields[m.group(1).lower()] = m.group(2).strip()
        entries[head.group(2)] = fields
    return entries


def item_key(path):
    """Ключ Zotero зі шляху до вкладення: ...\\storage\\ABCD1234\\file.pdf"""
    m = re.search(r"storage[\\/]([A-Z0-9]{8})", path)
    return m.group(1) if m else ""


def build(citekey, f):
    pdf = clean(f.get("file", ""))
    key = item_key(pdf)
    rq, priority, why, wave = TRIAGE[citekey]
    tags = ["triage-" + r.strip().lower() for r in rq.split(",") if r.strip()]
    if not pdf:
        tags.append("needs-fulltext")
    screening = (
        f"\n> [!abstract] Підстава включення (скринінг {wave or 'див. screening.md'})\n"
        f"> **{rq}**, пріоритет {priority}. {why}\n"
    )
    if not pdf:
        screening += ("> \n> ⚠️ **Повного тексту немає.** Доки PDF не долучено, "
                      "нотатку не заповнювати: з абстракту вийде текст, "
                      "не відрізнити́й від справжнього аналізу.\n")
    zotero = (f"zotero://select/library/items/{key}" if key
              else f"zotero://select/items/@{citekey}")  # форма Better BibTeX
    return TEMPLATE.format(
        citekey=citekey,
        title=q(clean(f.get("title", ""))),
        authors=q(fmt_authors(f.get("author", ""))),
        year=clean(f.get("year", "")) or "null",
        venue=q(clean(f.get("journal") or f.get("booktitle", ""))),
        doi=q(clean(f.get("doi", ""))),
        zotero=zotero,
        pdf=q(pdf),
        tags=", ".join(tags),
        screening=screening,
    )


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) not in (2, 3):
        print(__doc__)
        sys.exit(1)
    bib, notes = Path(args[0]), Path(args[1])
    entries = parse_bib(bib.read_text(encoding="utf-8"))
    global TRIAGE
    screening = Path(args[2]) if len(args) > 2 else \
        bib.resolve().parent.parent / "90_pipeline" / "out" / "screening.md"
    TRIAGE = load_triage(screening)
    if not TRIAGE:
        sys.exit(f"у {screening} не знайдено жодного рядка «Включено» з citekey/RQ/Пріоритет")

    created, skipped, missing = [], [], []
    for citekey in TRIAGE:
        if citekey not in entries:
            missing.append(citekey)
            continue
        target = notes / f"@{citekey}.md"
        if target.exists():
            skipped.append(citekey)
            continue
        if not dry:
            target.write_text(build(citekey, entries[citekey]), encoding="utf-8")
        created.append(citekey)

    print(f"створено: {len(created)} -> {', '.join(created) or '—'}")
    print(f"пропущено (файл уже є): {len(skipped)} -> {', '.join(skipped) or '—'}")
    if missing:
        print(f"НЕМАЄ В .bib: {', '.join(missing)}")


if __name__ == "__main__":
    main()
