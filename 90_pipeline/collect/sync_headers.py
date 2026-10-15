#!/usr/bin/env python3
"""Синхронізація шапок нотаток із front matter + звіт про розсинхрони.

Проблема, яку розв'язує: `verified_by_human` міняється у front matter, а рядок
шапки «Статус: `summarized`, не верифіковано» лишається старим. Front matter і
текст починають суперечити одне одному, і читач вірить тексту.

ЩО ВИПРАВЛЯЄ (детерміновано, лише перший рядок callout'а статусу):
  тип блоку й підпис статусу відповідно до полів `status` і `verified_by_human`.
  Другий і наступні рядки того самого callout'а — змістовні, їх не чіпає.

ЩО ЛИШЕ ЗВІТУЄ (потребує судження людини або Claude):
  * фрази про очікування верифікації в нотатках, які вже звірені;
  * порядкові лічильники на кшталт «третя робота поспіль» — вони старіють;
  * хаби без жодного вхідного посилання й посилання на неіснуючі хаби.

Використання:
    python sync_headers.py <корінь_сховища>            # лише показати
    python sync_headers.py <корінь_сховища> --apply    # записати виправлення
"""

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("потрібен pyyaml:  pip install pyyaml")

# перший рядок callout'а статусу за станом front matter
HEADERS = {
    ("imported", False): "> [!info] Статус: `imported`",
    ("imported", True): "> [!info] Статус: `imported`",
    ("summarized", False): "> [!warning] Статус: `summarized`, не верифіковано",
    ("summarized", True): "> [!success] Статус: `summarized`, звірено людиною",
    ("verified", False): "> [!warning] Статус: `verified`, але `verified_by_human` не стоїть",
    ("verified", True): "> [!success] Статус: `verified`",
    ("abstract-only", False): "> [!danger] Статус: `abstract-only` — повного тексту немає",
    ("abstract-only", True): "> [!danger] Статус: `abstract-only`, звірено людиною з абстракту",
}

# фрази, що втрачають сенс після верифікації
PENDING_PHRASES = [
    "не верифіковано",
    "Потребує людської верифікації",
    "Перед `verified_by_human: true`",
    "варто верифікувати",
    "чекає на верифікацію",
]

# порядкові лічильники наскрізних тез — старіють з кожним новим джерелом.
# Розмітка між числівником і словом («**третя** робота») і числівники понад
# «десята» раніше проходили повз — їх доводилось знаходити руками.
ORDINAL = (r"перша|друга|третя|четверта|п'ята|шоста|сьома|восьма|дев'ята|десята"
           r"|одинадцята|дванадцята|тринадцята|чотирнадцята|п'ятнадцята")
COUNTER = re.compile(
    r"\b\**(?:" + ORDINAL + r")\**(?:\s*[-–—]\s*\**(?:" + ORDINAL + r")\**)?"
    r"\s+\**(робот[аи]|джерел[оа]|статт[яі])\b[^.]{0,40}",
    re.IGNORECASE)

# Дробові лічильники: «в семи з одинадцяти джерел», «20 із 23 джерел».
# Числівники — закритий список, інакше в скаргу летить кожне «набір із двох
# джерел», що стосується самої статті, а не бази. Додаткова умова: у рядку
# має бути «баз» або «опрацьован» — саме це відрізняє твердження про мою
# базу від опису чужого корпусу.
NUM = (r"\d+|дв[аі]|двох|три|трьох|чотири|чотирьох|п'ять|п'ятьох|шість|шести"
       r"|сім|семи|вісім|восьми|дев'ять|дев'яти|десять|десяти|одинадцять"
       r"|одинадцяти|дванадцять|дванадцяти|тринадцяти|чотирнадцяти|п'ятнадцяти"
       r"|двадцяти|двадцять")
FRACTION = re.compile(
    r"\b(?:" + NUM + r")\s+і?з\s+(?:" + NUM + r")\s+"
    r"(?:\S+\s+){0,2}?(?:джерел\w*|робіт|робота[хм]?|нотаток|статей)\b",
    re.IGNORECASE)
FRACTION_CONTEXT = ("баз", "опрацьован")

LINK = re.compile(r"\[\[([^\]|#]+)")


def split_note(text):
    """-> (front_matter_text, body) або (None, text)"""
    m = re.match(r"(---\n.*?\n---\n)(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else (None, text)


def status_callout_span(body):
    """Межі першого callout'а статусу в тілі: (початок_рядка, кінець_першого_рядка)."""
    m = re.search(r"^> \[!\w+\][^\n]*Статус:[^\n]*$", body, re.M)
    return m.span() if m else None


def process(path, apply):
    text = path.read_text(encoding="utf-8")
    fm_text, body = split_note(text)
    fixes, notes_out = [], []

    if fm_text is None:
        return ["немає front matter"], []

    try:
        fm = yaml.safe_load(fm_text.strip("-\n")) or {}
    except yaml.YAMLError as e:
        return [f"YAML не парситься: {str(e).splitlines()[0]}"], []

    status = fm.get("status")
    verified = fm.get("verified_by_human") is True
    want = HEADERS.get((status, verified))

    span = status_callout_span(body)
    if want is None:
        notes_out.append(f"невідомий статус `{status}` — шапку не чіпав")
    elif span is None:
        notes_out.append("callout статусу не знайдено — шапку не чіпав")
    else:
        have = body[span[0]:span[1]]
        if have != want:
            fixes.append(f"шапка: «{have.strip()}» → «{want.strip()}»")
            # тіло оновлюємо завжди, щоб подальші перевірки бачили стан ПІСЛЯ виправлення
            body = body[:span[0]] + want + body[span[1]:]
            if apply:
                path.write_text(fm_text + body, encoding="utf-8")

    # звіти без автоматичного втручання
    if verified:
        for phrase in PENDING_PHRASES:
            if phrase in body:
                notes_out.append(f"звірено людиною, але в тексті лишилось «{phrase}»")

    for m in COUNTER.finditer(body):
        notes_out.append(f"порядковий лічильник: «{m.group(0).strip()}» — перерахувати")

    for line in body.splitlines():
        if "станом на" in line or not any(c in line.lower() for c in FRACTION_CONTEXT):
            continue
        for m in FRACTION.finditer(line):
            notes_out.append(f"дробовий лічильник без дати: «{m.group(0).strip()}»"
                             " — перерахувати й дописати «(станом на ДД.ММ.РРРР)»")

    return fixes, notes_out


def hub_report(notes_dir, hubs_dir):
    used, defined = {}, set()
    if hubs_dir.is_dir():
        defined = {p.stem for p in hubs_dir.glob("*.md") if not p.stem.startswith("_")}
    for path in notes_dir.glob("@*.md"):
        for name in LINK.findall(path.read_text(encoding="utf-8")):
            if name.startswith("@"):
                continue
            used.setdefault(name, set()).add(path.stem)
    orphan = sorted(defined - set(used))
    undefined = sorted(set(used) - defined)
    return orphan, undefined, used


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    root = Path(args[0])
    notes_dir = root / "10_literature" / "notes"
    hubs_dir = root / "10_literature" / "hubs"

    print("режим: " + ("ЗАПИС" if apply else "лише показати (додай --apply, щоб виправити)"))

    total_fixes = 0
    for path in sorted(notes_dir.glob("@*.md")):
        fixes, notes_out = process(path, apply)
        if fixes or notes_out:
            print(f"\n{path.name}")
            for f in fixes:
                total_fixes += 1
                print(f"  {'✔' if apply else '→'} {f}")
            for n in notes_out:
                print(f"  ? {n}")

    orphan, undefined, used = hub_report(notes_dir, hubs_dir)
    print("\nХаби\n────")
    print(f"використано унікальних: {len(used)}   файлів-хабів: {len(used) - len(undefined) + len(orphan)}")
    if orphan:
        print(f"без жодного вхідного посилання ({len(orphan)}): {', '.join(orphan)}")
    if undefined:
        print(f"посилання без файлу ({len(undefined)}): {', '.join(undefined)}")
    print("  (хаб без файлу — це норма, поки нема що написати в означенні;"
          " хаб без посилань — привід перевірити, чи не змінилась назва)")

    print(f"\nвиправлень шапок: {total_fixes}"
          + ("" if apply else " (не записано)"))


if __name__ == "__main__":
    main()
