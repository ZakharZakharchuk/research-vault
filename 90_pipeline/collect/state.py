#!/usr/bin/env python3
"""Живий стан бази огляду літератури.

Друкує те, що інакше довелось би переписувати руками в CLAUDE.md і що
через це неминуче старіє: скільки записів, скільки нотаток, де розриви
між бібліотекою й нотатками, хто чекає на верифікацію.

Запускати на початку кожної сесії:
    python 90_pipeline/collect/state.py .
де «.» — корінь сховища.
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("потрібен pyyaml:  pip install pyyaml")

RELEVANCE = ("High", "Medium", "Low")
# 0.40 — поріг зі скіла litnote-summarize («частка High вище 40 % → знизити
# найслабший»). Орієнтир протоколу ще суворіший: ядро ≈ третина бази.
HIGH_SHARE_LIMIT = 0.40

# Наскрізні твердження, які пишуться в нотатках дробом і від того старіють.
# Замість переписувати їх руками — тегувати джерела й рахувати тут.
# {як назвати у виводі: (тег «вади немає в джерелі», тег «є»)}
FRACTIONS = {
    "мажоритарний baseline": ("no-majority-baseline", "majority-baseline-reported"),
}


def parse_bib(path):
    """{citekey: {'title': ..., 'has_pdf': bool}}"""
    out = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for chunk in re.split(r"\n(?=@)", text):
        head = re.match(r"@(\w+)\{([^,]+),", chunk)
        if not head:
            continue
        title = re.search(r"\n\s*title\s*=\s*\{(.+?)\}\s*,\s*\n", chunk, re.S)
        out[head.group(2)] = {
            "title": re.sub(r"[{}\s]+", " ", title.group(1)).strip()[:60] if title else "?",
            "has_pdf": bool(re.search(r"\n\s*file\s*=", chunk)),
        }
    return out


def parse_notes(folder):
    """{citekey: meta}"""
    out = {}
    for path in sorted(folder.glob("@*.md")):
        m = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
        key = path.stem.lstrip("@")
        if not m:
            out[key] = {"_broken": "немає front matter"}
            continue
        try:
            out[key] = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            out[key] = {"_broken": str(e).splitlines()[0]}
    return out


def block(title):
    print(f"\n{title}\n" + "─" * len(title))


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    bib_path = root / "00_admin" / "library.bib"
    if not bib_path.exists():
        print("00_admin/library.bib ще немає — налаштуйте автоекспорт Better BibTeX (SETUP.md, крок 3).")
        bib = {}
    else:
        bib = parse_bib(bib_path)
    notes = parse_notes(root / "10_literature" / "notes")

    block("Бібліотека")
    no_pdf = [k for k, v in bib.items() if not v["has_pdf"]]
    print(f"записів у library.bib: {len(bib)}")
    print(f"  з PDF: {len(bib) - len(no_pdf)}   без PDF: {len(no_pdf)}")

    block("Розриви бібліотека ↔ нотатки")
    no_note = sorted(set(bib) - set(notes))
    no_entry = sorted(set(notes) - set(bib))
    print(f"записів без нотатки: {len(no_note)}"
          + (f" → {', '.join(no_note)}" if no_note else ""))
    print(f"нотаток без запису в .bib: {len(no_entry)}"
          + (f" → {', '.join(no_entry)}" if no_entry else ""))
    print("  (записи без нотатки — це переважно відкинуті або відкладені тріажем;"
          " звіряти з 90_pipeline/out/screening.md, а не додавати нотатки наосліп)")

    broken = [k for k, v in notes.items() if "_broken" in v]
    if broken:
        print(f"НЕЧИТАБЕЛЬНІ нотатки: {', '.join(broken)} — не потраплять у жодну таблицю Dataview")

    block("Нотатки за статусами")
    by_status = {}
    for k, v in notes.items():
        by_status.setdefault(v.get("status", "?"), []).append(k)
    for st in ("imported", "summarized", "verified", "abstract-only", "?"):
        if st in by_status:
            print(f"{st:15} {len(by_status[st]):3}")
    print(f"{'разом':15} {len(notes):3}")

    block("Черга верифікації")
    pending = sorted(k for k, v in notes.items()
                     if v.get("status") in ("summarized", "verified")
                     and v.get("verified_by_human") is not True)
    done = sum(1 for v in notes.values() if v.get("verified_by_human") is True)
    print(f"звірено людиною: {done}")
    print(f"чекає на верифікацію: {len(pending)}")
    for k in pending:
        print(f"  @{k}  ({notes[k].get('relevance') or '—'})")

    block("Розподіл relevance")
    graded = {k: v for k, v in notes.items()
              if v.get("status") in ("summarized", "verified")}
    tally = {r: sum(1 for v in graded.values() if v.get("relevance") == r) for r in RELEVANCE}
    total = sum(tally.values())
    if total:
        print("  ".join(f"{r} {tally[r]}" for r in RELEVANCE)
              + f"  —  High {tally['High'] / total:.0%}")
        if tally["High"] / total > HIGH_SHARE_LIMIT:
            print(f"  увага: частка High {tally['High'] / total:.0%} — вище порога"
                  f" {HIGH_SHARE_LIMIT:.0%}. Орієнтир протоколу — ядро ≈ третина бази."
                  " Знизити найслабший High у партії")
    no_why = sorted(k for k, v in graded.items() if not v.get("relevance_why"))
    if no_why:
        print(f"  без relevance_why: {', '.join('@' + k for k in no_why)}")

    block("Наскрізні дроби (щоб не рахувати з памʼяті)")
    for label, (tag_no, tag_yes) in FRACTIONS.items():
        def tagged(tag):
            return {k for k, v in notes.items()
                    if tag in [str(x) for x in (v.get("tags") or [])]}
        no, yes = tagged(tag_no), tagged(tag_yes)
        denom = len(no) + len(yes)
        if not denom:
            print(f"{label}: тегів немає — дріб не рахується")
            continue
        print(f"{label}: немає у {len(no)} із {denom} ({len(no) / denom:.0%})")
    print("  цей дріб іде в тези нотаток — цитувати звідси, з датою запуску,"
          " а не переписувати з іншої нотатки")

    block("Покриття RQ (за тегами triage-rq*)")
    rq = {}
    untagged = []
    for k, v in notes.items():
        tags = [str(t) for t in (v.get("tags") or [])]
        found = [t.replace("triage-", "").upper() for t in tags if t.startswith("triage-rq")]
        if found:
            for r in found:
                rq.setdefault(r, []).append(k)
        else:
            untagged.append(k)
    for r in sorted(rq):
        print(f"{r}: {len(rq[r])}")
    if untagged:
        print(f"без тегу RQ: {len(untagged)} → {', '.join('@' + k for k in sorted(untagged))}")
    print("квоти й дефіцит — у 00_admin/protocol.md, розд. 2")


if __name__ == "__main__":
    main()
