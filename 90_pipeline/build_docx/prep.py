"""Готує звіт до збирання в .docx: реферат (abstract.md) + розділ (ch1.md) + перелік скорочень.
Нумерує посилання [[@citekey]] за першою появою в документі → [N], [N, с. X], [N, M];
будує перелік джерел посилання за ДСТУ 8302:2015; розбиває текст на блоки з інлайн-розміткою.

Виклик: python3 prep.py [ch1.md] [--pages N]
Вхід у робочій теці: ch1.md, abstract.md (необов'язковий), abbreviations.md, lib.json, refmeta.json."""
import json, os, re, sys, unicodedata

args = [a for a in sys.argv[1:]]
pages = '?'
if '--pages' in args:
    i = args.index('--pages'); pages = args[i + 1]; del args[i:i + 2]
ch1_path = args[0] if args else 'ch1.md'

def strip_fm(t):
    return re.sub(r'^---\n.*?\n---\n', '', t, flags=re.S)

ch1 = strip_fm(open(ch1_path, encoding='utf-8').read())
# службовий хвіст розділу (після «---» і заголовка «## Черга верифікації») у документ не йде
ch1 = ch1.split('\n---\n\n## Черга верифікації')[0]
abstract = strip_fm(open('abstract.md', encoding='utf-8').read()) if os.path.exists('abstract.md') else ''
SPLIT = '\n\n@@BODY@@\n\n'
md = abstract + SPLIT + ch1

csl = {x['id']: x for x in json.load(open('lib.json', encoding='utf-8'))}
meta = json.load(open('refmeta.json', encoding='utf-8'))
# overrides.json (необов'язковий): ручні виправлення метаданих, які .bib дає криво.
# {"citekey": {"authors": [["Прізвище", "І."]], "authors_from": "bib", "container": "Назва видання"}}
OVR = json.load(open('overrides.json', encoding='utf-8')) if os.path.exists('overrides.json') else {}

# 1. Нумерація джерел за першою появою (реферат іде першим)
order = []
for k in re.findall(r'\[\[@([^\]]+)\]\]', md):
    if k not in order:
        order.append(k)
num = {k: i + 1 for i, k in enumerate(order)}

ANCH = r'(?:с\.|табл\.|рис\.|розд\.|дод\.)'
# «(розраховано за даними [[@k]], с. X)» → «(розраховано за даними [N, с. X])»
md = re.sub(r'\[\[@([^\]]+)\]\], (' + ANCH + r'[^()]*)\)', lambda m: f'[{num[m.group(1)]}, {m.group(2)}])', md)
# «[[@k]] (с. X)» → «[N, с. X]»
md = re.sub(r'\[\[@([^\]]+)\]\] \((' + ANCH + r'[^()]*)\)', lambda m: f'[{num[m.group(1)]}, {m.group(2)}]', md)
# кілька посилань поспіль «[[@a]], [[@b]]» → «[Na, Nb]»
CITE = r'\[\[@[^\]]+\]\]'
md = re.sub(CITE + r'(?:, ' + CITE + r')+',
            lambda m: '[' + ', '.join(str(num[k]) for k in re.findall(r'\[\[@([^\]]+)\]\]', m.group(0))) + ']', md)
md = re.sub(r'\[\[@([^\]]+)\]\]', lambda m: f'[{num[m.group(1)]}]', md)

# 2. TODO-коментарі → видимі примітки автора
md = re.sub(r'\s*<!--\s*TODO:\s*(.*?)\s*-->', lambda m: f' ⟦Примітка автора: {m.group(1).strip()}⟧', md, flags=re.S)

# 3. Рядок обсягу реферату
def plural(n, one, few, many):
    n = int(n)
    if n % 10 == 1 and n % 100 != 11: return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14: return few
    return many
n_tab = len(re.findall(r'^Таблиця \d+\.\d+ — ', md, flags=re.M))
md = md.replace('{{PAGES}}', str(pages)).replace('{{TABLES}}', str(n_tab))
md = md.replace('{{REFS}} джерел', f'{len(order)} ' + plural(len(order), 'джерело', 'джерела', 'джерел'))

# ---------- перелік посилань ----------
LATEX = {"\\'": '\u0301', '\\`': '\u0300', '\\v ': '\u030c', '\\v': '\u030c', '\\~': '\u0303', '\\"': '\u0308', '\\^': '\u0302'}
def delatex(s):
    s = s.replace('\\\\', '\\')
    s = re.sub(r'\\l\b ?', 'ł', s)
    def acc(m):
        return unicodedata.normalize('NFC', m.group(2) + LATEX[m.group(1)])
    s = re.sub(r"(\\'|\\`|\\v ?|\\~|\\\"|\\\^)\{?([A-Za-z])\}?", lambda m: unicodedata.normalize('NFC', m.group(2) + LATEX[m.group(1) if m.group(1) in LATEX else m.group(1).strip()]), s)
    return s.replace('{', '').replace('}', '')

def initials(given):
    parts = []
    for w in given.split():
        sub = [p[0] + '.' for p in w.split('-') if p and p[0].isalpha()]
        if sub:
            parts.append('-'.join(sub))
    return ' '.join(parts)

def authors_list(k):
    """Повертає список (прізвище, ініціали)."""
    c = csl.get(k, {})
    au = c.get('author', [])
    good = [a for a in au if a.get('family') and a.get('given') and 'University' not in a.get('family', '')]
    o = OVR.get(k, {})
    if 'authors' in o:                     # ручне виправлення з overrides.json
        return [tuple(x) for x in o['authors']]
    if o.get('authors_from') == 'bib':     # брати авторів із .bib, а не з нотатки
        return [(a['family'], initials(a['given'])) for a in good]
    if True:
        res = []
        for a in delatex(meta[k]['authors']).split(','):
            a = a.strip()
            if not a or a.startswith('et al'):
                continue
            m = re.match(r'(.+?)\s+((?:[A-ZА-ЯІЇЄҐ][a-zа-яії]?\.\s?-?)+)$', a)
            res.append((m.group(1), m.group(2).strip()) if m else (a, ''))
        return res
    return [(a['family'], initials(a['given'])) for a in good]

def is_cyr(s):
    return bool(re.search('[А-Яа-яІіЇїЄєҐґ]', s or ''))

def sentence_case_upper(t):
    if t.isupper():
        t = t.lower()
        t = t[0].upper() + t[1:]
        t = re.sub(r'\bnlp\b', 'NLP', t)
    return t

def ref_entry(k):
    c = csl.get(k, {})
    au = authors_list(k)
    title = c.get('title', '')
    # якщо в .bib назва порожня або набрана ВЕЛИКИМИ — беремо з нотатки
    if not title.strip() or title.isupper():
        title = sentence_case_upper(meta[k]['title'])
    title = title.replace('’', "'").rstrip('.')
    cont = c.get('container-title', '')
    if not cont.strip():
        cont = meta.get(k, {}).get('venue', '')
    cont = OVR.get(k, {}).get('container', cont)
    year = (c.get('issued', {}).get('date-parts') or [[meta[k]['year']]])[0][0]
    cyr = is_cyr(title)
    P, V, N = ('С.', 'Т.', '№') if cyr else ('P.', 'Vol.', 'No.')
    pages = (c.get('page') or '').replace('--', '–').replace('-', '–')
    if pages and '–' in pages:
        a, b = pages.split('–', 1)
        if a == b:
            pages = ''
    doi = c.get('DOI', '')
    arx = c.get('number', '') if (c.get('number', '') or '').startswith('arXiv') else ''
    # автори
    def inv(s, i):  # «І. Прізвище»
        return f'{i} {s}'.strip()
    if len(au) <= 3:
        head = ', '.join(f'{s} {i}'.strip() for s, i in au) + '. ' + title + '.'
    else:
        head = title + ' / ' + inv(*au[0]) + (' та ін.' if cyr else ' et al.')
    parts = [head]
    if arx or not cont:
        parts.append(f'arXiv preprint {arx}.' if arx else '')
        parts.append(f'{year}.')
    elif c.get('type') == 'article-journal':
        vol = []
        if c.get('volume'): vol.append(f'{V} {c["volume"]}')
        if c.get('issue'): vol.append(f'{N} {c["issue"]}')
        parts.append(f'{cont}. {year}.' + (' ' + ', '.join(vol) + '.' if vol else ''))
        if pages: parts.append(f'{P} {pages}.')
    else:
        place = c.get('publisher-place')
        # місце проведення ACM-конференцій у .bib записане без ком («Hannover Germany», «Virtual Event China»)
        PLACE_FIX = {'Hannover Germany': 'Hannover', 'Honolulu HI USA': 'Honolulu', 'Boise ID USA': 'Boise'}
        place = PLACE_FIX.get(place, place)
        if place and place.startswith('Virtual Event'):
            place = None
        parts.append(f'{cont}. ' + (f'{place}, ' if place else '') + f'{year}.')
        if pages: parts.append(f'{P} {pages}.')
    if doi:
        parts.append(f'DOI: {doi}.')
    s = ' '.join(p for p in parts if p)
    s = re.sub(r'\.\.', '.', s)
    s = re.sub(r'\bthe The\b', 'the', s)
    return delatex(s)

refs = [ref_entry(k) for k in order]

# ---------- блоки ----------
def to_blocks(text):
    blocks = []
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.startswith('# '):
            blocks.append({'t': 'h1', 'text': ln[2:].strip()}); i += 1; continue
        if ln.startswith('## '):
            blocks.append({'t': 'h2', 'text': re.sub(r'^(\d+\.\d+)\.\s', r'\1 ', ln[3:].strip())}); i += 1; continue
        if ln.startswith('### '):
            blocks.append({'t': 'h3', 'text': re.sub(r'^(\d+\.\d+\.\d+)\.\s', r'\1 ', ln[4:].strip())}); i += 1; continue
        if ln.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                r = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-{3,}:?', c) for c in r):
                    rows.append(r)
                i += 1
            blocks.append({'t': 'table', 'rows': rows}); continue
        if re.match(r'^Таблиця \d+\.\d+ — ', ln):
            blocks.append({'t': 'caption', 'text': ln.strip()}); i += 1; continue
        if ln.startswith('¹'):
            blocks.append({'t': 'note', 'text': 'Примітка. ' + ln[1:].strip()}); i += 1; continue
        blocks.append({'t': 'p', 'text': ln.strip()}); i += 1
    return blocks

abs_md, body_md = md.split(SPLIT)
abstract_blocks = to_blocks(abs_md)
blocks = to_blocks(body_md)

abbr = []
if os.path.exists('abbreviations.md'):
    for l in open('abbreviations.md', encoding='utf-8'):
        if ' — ' in l and not l.startswith(('title', 'note', '#')):
            a, b = l.strip().split(' — ', 1)
            abbr.append([a, b])
title = {}
if os.path.exists('title.md'):
    for l in strip_fm(open('title.md', encoding='utf-8').read()).splitlines():
        if ': ' in l:
            k_, v_ = l.split(': ', 1)
            title[k_.strip()] = v_.strip()
json.dump({'title': title, 'abstract': abstract_blocks, 'blocks': blocks, 'refs': refs, 'abbr': abbr}, open('doc.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(abstract_blocks), 'abstract blocks;', len(blocks), 'blocks;', len(refs), 'refs;', n_tab, 'tables; pages =', pages)
for r in refs[:60]:
    print('-', r)
left = re.findall(r'\[\[@', md)
print('unconverted citations:', len(left))
