#!/usr/bin/env python3
"""Добудова цитатного графу `cites` у шапках нотаток.

Навіщо окремий скрипт: посилання односторонні в часі. Коли в бібліотеку
додається джерело `B`, усі раніше написані нотатки, що на нього посилаються,
лишаються без лінка — вони писались, коли `B` ще не було.

────────────────────────────────────────────────────────────────────────────
ТРИ РЕЖИМИ. Мережа й файли сховища в хмарній сесії не перетинаються:
контейнер має мережу, але не бачить ваше сховище; `device_bash` бачить
файли, але мережі не має. Тому робота розділена так, щоб **жоден крок не
потребував вашого терміналу**:

    python build_cites.py . --plan
        офлайн. Дивиться, чого бракує в кеші, і пише список URL у
        90_pipeline/out/cites_queue.json

    (Claude тягне ці URL через web_fetch і складає відповіді у
     90_pipeline/out/cites_fetched.json)

    python build_cites.py . --ingest --apply
        офлайн. Вливає відповіді в кеш, рахує перетин із бібліотекою,
        дописує `cites`.

    python build_cites.py . --online --apply
        усе за один раз, якщо запускати зі свого терміналу, де є і мережа,
        і сховище. Найзручніший режим, але не обовʼязковий.

────────────────────────────────────────────────────────────────────────────
ДЖЕРЕЛА ДАНИХ, у порядку спадання довіри:

1. **OpenAlex** `works/doi:<DOI>` → `referenced_works`. Основний шлях.
   Шлях без query-параметрів; `works?filter=...` віддає 429 (див. CLAUDE.md).
2. **Crossref** `works/<DOI>` → `reference[].DOI`. Запасний.
3. **Semantic Scholar** `paper/DOI:<DOI>/references`. Другий запасний.

Виміряно автором шаблону (серпень 2026), і це варто памʼятати перед тим, як
покладатись на запасні шляхи: **ACL Anthology не депонує списки посилань у
Crossref взагалі** (`reference-count: 0`), а Semantic Scholar через спільну
вихідну IP хмари стабільно віддає 429. Тобто для свіжих робіт ACL цитатний
граф **не будується автоматично з жодного джерела** — їхні `cites` ставляться
руками під час читання PDF на Stage 2.

────────────────────────────────────────────────────────────────────────────
ПРАВИЛА (зі скіла `litnote-maintain`, розд. 4):

- знайдене — додаємо; ненайдене — **не видаляємо** (списки посилань неповні
  в усіх трьох джерелах, відсутність там нічого не доводить);
- уже наявні лінки, поставлені руками, не чіпаємо;
- у `cites` кладуться **лише** роботи, наявні в `library.bib`.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("потрібен pyyaml:  pip install pyyaml")

UA = "litnote-build-cites/2.0 (research-vault)"
CACHE = "openalex_cache.json"
QUEUE = "cites_queue.json"
FETCHED = "cites_fetched.json"
PAUSE = 0.35
STALE_DAYS = 90          # як часто перепитувати джерела, що віддали порожньо


# ─────────────────────────── дрібне ───────────────────────────

def norm_doi(doi):
    if not doi:
        return None
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(doi).strip().lower())
    return d or None


def short_id(u):
    """Канонічна форма ідентифікатора OpenAlex: голе число, без URL і без «W».

    Одне й те саме джерело трапляється в трьох написаннях —
    `https://openalex.org/W123`, `W123` і `123`, — і якщо не звести їх до
    одного, перетин мовчки виходить порожнім: не помилка, а нуль знахідок,
    що виглядає як «нічого нового». Особливо легко — при засіванні кешу
    вручну."""
    return str(u).rsplit("/", 1)[-1].lstrip("Ww")


def oa_url(doi):
    return ("https://api.openalex.org/works/doi:"
            + urllib.parse.quote(doi, safe="/.:") + "?select=id,referenced_works")


def cr_url(doi):
    return "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/.:")


def s2_url(doi):
    return ("https://api.semanticscholar.org/graph/v1/paper/DOI:"
            + urllib.parse.quote(doi, safe="/.:") + "/references?fields=externalIds&limit=500")


def today():
    return time.strftime("%Y-%m-%d")


def stale(datestr):
    if not datestr:
        return True
    try:
        t = time.mktime(time.strptime(datestr, "%Y-%m-%d"))
    except ValueError:
        return True
    return (time.time() - t) > STALE_DAYS * 86400


# ─────────────────────────── читання сховища ───────────────────────────

def parse_bib_dois(path):
    out = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    for chunk in re.split(r"\n(?=@)", text):
        head = re.match(r"@(\w+)\{([^,]+),", chunk)
        if not head:
            continue
        m = re.search(r"\n\s*doi\s*=\s*[{\"]([^}\"]+)", chunk, re.I)
        out[head.group(2).strip()] = norm_doi(m.group(1)) if m else None
    return out


def split_note(text):
    m = re.match(r"(---\n)(.*?)(\n---\n)(.*)", text, re.S)
    return (m.group(2), m.group(4)) if m else (None, text)


def read_notes(folder):
    out = []
    for p in sorted(folder.glob("@*.md")):
        fm_text, _ = split_note(p.read_text(encoding="utf-8"))
        if fm_text is None:
            continue
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            print(f"  ! YAML не парситься, пропускаю: {p.name}")
            continue
        blob = json.dumps(fm.get("cites") or [], ensure_ascii=False)
        out.append({"key": p.stem.lstrip("@"), "path": p, "doi": norm_doi(fm.get("doi")),
                    "cites": set(re.findall(r"\[\[@([^\]]+)\]\]", blob))})
    return out


CITES_BLOCK = re.compile(r"^cites:.*?(?=^[A-Za-z_][\w_]*:|\Z)", re.M | re.S)


def write_cites(path, keys):
    text = path.read_text(encoding="utf-8")
    fm_text, body = split_note(text)
    if fm_text is None:
        return False
    m = CITES_BLOCK.search(fm_text)
    if not m:
        return False
    rebuilt = "cites:\n" + "".join('  - "[[@%s]]"\n' % k for k in sorted(keys))
    new_fm = fm_text[:m.start()] + rebuilt.rstrip("\n") + "\n" + fm_text[m.end():]
    path.write_text("---\n" + new_fm.rstrip("\n") + "\n---\n" + body, encoding="utf-8")
    return True


# ─────────────────────────── мережа (лише --online) ───────────────────────────

def fetch_json(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:                                     # noqa: BLE001
        return {"_error": type(e).__name__}


# ─────────────────────────── розбір відповідей ───────────────────────────

def parse_openalex(payload):
    if not isinstance(payload, dict) or "id" not in payload:
        return None
    return {"oa_id": short_id(payload["id"]),
            "refs_oa": [short_id(x) for x in (payload.get("referenced_works") or [])]}


def parse_crossref(payload):
    msg = (payload or {}).get("message") or {}
    return [norm_doi(r.get("DOI")) for r in (msg.get("reference") or []) if r.get("DOI")]


def parse_s2(payload):
    out = []
    for item in ((payload or {}).get("data") or []):
        ext = ((item.get("citedPaper") or {}).get("externalIds") or {})
        if ext.get("DOI"):
            out.append(norm_doi(ext["DOI"]))
    return out


# ─────────────────────────── режими ───────────────────────────

def plan(root, bib_dois, notes, cache):
    """Що саме треба дотягнути. Офлайн."""
    need = []
    for key, doi in sorted(bib_dois.items()):
        if doi and "oa_id" not in cache.get(doi, {}):
            need.append({"citekey": key, "doi": doi, "source": "openalex", "url": oa_url(doi)})
    for n in notes:
        d = n["doi"]
        if not d:
            continue
        c = cache.get(d, {})
        if "refs_oa" not in c:
            if not any(x["doi"] == d and x["source"] == "openalex" for x in need):
                need.append({"citekey": n["key"], "doi": d, "source": "openalex", "url": oa_url(d)})
        elif not c["refs_oa"] and "refs_doi" not in c and stale(c.get("empty_checked")):
            need.append({"citekey": n["key"], "doi": d, "source": "crossref", "url": cr_url(d)})
            need.append({"citekey": n["key"], "doi": d, "source": "s2", "url": s2_url(d)})

    qpath = root / "90_pipeline" / "out" / QUEUE
    qpath.parent.mkdir(parents=True, exist_ok=True)
    qpath.write_text(json.dumps(need, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"у черзі: {len(need)} запитів → {qpath}")
    if not need:
        print("кеш повний — мережа не потрібна, одразу --ingest")
        return
    print("\nформат відповідей у 90_pipeline/out/" + FETCHED + " — обʼєкт виду:")
    print('  {"<doi>": {"openalex": <сирий JSON>, "crossref": <сирий JSON>, "s2": <сирий JSON>}}')
    print("класти можна частинами: --ingest вливає те, що є, решта лишається в черзі")
    for x in need[:6]:
        print(f"  {x['source']:9s} @{x['citekey'][:38]:40s} {x['url']}")
    if len(need) > 6:
        print(f"  … ще {len(need) - 6}")


def ingest_payloads(cache, fetched):
    """Вливає сирі відповіді в кеш. Офлайн."""
    added = 0
    for doi, per_source in (fetched or {}).items():
        d = norm_doi(doi)
        c = cache.setdefault(d, {})
        if "openalex" in per_source:
            parsed = parse_openalex(per_source["openalex"])
            if parsed:
                c.update(parsed)
                added += 1
        for src, fn in (("crossref", parse_crossref), ("s2", parse_s2)):
            if src in per_source:
                refs = [r for r in fn(per_source[src]) if r]
                if refs:
                    c["refs_doi"] = sorted(set(c.get("refs_doi", [])) | set(refs))
                    c["refs_doi_src"] = src
                    added += 1
        if not c.get("refs_oa") and not c.get("refs_doi"):
            c["empty_checked"] = today()
    return added


def online(bib_dois, notes, cache):
    """Тягне сам. Лише для запуску з термінала, де є і мережа, і сховище."""
    for key, doi in sorted(bib_dois.items()):
        if not doi or "oa_id" in cache.get(doi, {}):
            continue
        parsed = parse_openalex(fetch_json(oa_url(doi)))
        time.sleep(PAUSE)
        cache.setdefault(doi, {}).update(parsed or {"oa_id": None})
        print(f"  {'✔' if parsed else '—'} {key}")
    for n in notes:
        d = n["doi"]
        if not d:
            continue
        c = cache.setdefault(d, {})
        if "refs_oa" not in c:
            parsed = parse_openalex(fetch_json(oa_url(d)))
            time.sleep(PAUSE)
            c.update(parsed or {"oa_id": None, "refs_oa": []})
        if not c.get("refs_oa") and "refs_doi" not in c and stale(c.get("empty_checked")):
            refs = parse_crossref(fetch_json(cr_url(d)))
            time.sleep(PAUSE)
            src = "crossref"
            if not refs:
                refs = parse_s2(fetch_json(s2_url(d)))
                time.sleep(PAUSE)
                src = "s2"
            if refs:
                c["refs_doi"] = [r for r in refs if r]
                c["refs_doi_src"] = src
            else:
                c["empty_checked"] = today()
        print(f"  {len(c.get('refs_oa') or []) or len(c.get('refs_doi') or []):4d}  @{n['key']}")


def resolve(bib_dois, notes, cache, apply_changes):
    """Перетин із бібліотекою і запис. Офлайн."""
    doi2key = {}
    for k, d in bib_dois.items():
        if d:
            doi2key.setdefault(d, k)
    oaid2key = {short_id(v["oa_id"]): doi2key[d] for d, v in cache.items()
                if d in doi2key and v.get("oa_id")}

    total, blind = 0, []
    for n in notes:
        c = cache.get(n["doi"] or "", {})
        if not c.get("refs_oa") and not c.get("refs_doi"):
            blind.append(n["key"])
        found = {oaid2key[short_id(r)] for r in (c.get("refs_oa") or [])
                 if short_id(r) in oaid2key}
        found |= {doi2key[d] for d in (c.get("refs_doi") or []) if d in doi2key}
        found.discard(n["key"])
        new = sorted(found - n["cites"])
        if not new:
            continue
        total += len(new)
        print(f"  @{n['key']}: +{len(new)} → {', '.join(new)}")
        if apply_changes and not write_cites(n["path"], n["cites"] | set(new)):
            print("    ! поле cites не знайдено, пропущено")

    print(f"\nнових звʼязків: {total}   режим: " + ("ЗАПИС" if apply_changes else "показ"))
    if blind:
        print(f"без списку посилань у жодному джерелі ({len(blind)}): {', '.join('@' + b for b in blind)}")
        print("  для них `cites` ставляться руками під час читання PDF — див. шапку скрипта")
    print("ненайдене не видаляється: списки посилань неповні в усіх трьох джерелах")


def main():
    ap = argparse.ArgumentParser(description="Цитатний граф: OpenAlex + Crossref + Semantic Scholar")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--plan", action="store_true", help="офлайн: скласти чергу запитів")
    ap.add_argument("--ingest", action="store_true", help="офлайн: влити відповіді й порахувати")
    ap.add_argument("--online", action="store_true", help="тягнути самому (потрібні мережа + сховище)")
    ap.add_argument("--apply", action="store_true", help="записати зміни у файли")
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = root / "90_pipeline" / "out"
    bib_dois = parse_bib_dois(root / "00_admin" / "library.bib")
    notes = read_notes(root / "10_literature" / "notes")
    cache_path = out_dir / CACHE
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    print(f".bib: {len(bib_dois)} записів   нотаток: {len(notes)}   кеш: {len(cache)}\n")

    if args.plan:
        plan(root, bib_dois, notes, cache)
        return

    if args.online:
        online(bib_dois, notes, cache)
    elif args.ingest:
        fpath = out_dir / FETCHED
        if not fpath.exists():
            sys.exit(f"немає {fpath} — спершу --plan, потім покласти туди відповіді")
        n = ingest_payloads(cache, json.loads(fpath.read_text(encoding="utf-8")))
        print(f"влито відповідей: {n}\n")
    else:
        print("нічого не роблю: оберіть --plan, --ingest або --online\n")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    resolve(bib_dois, notes, cache, args.apply)


if __name__ == "__main__":
    main()
