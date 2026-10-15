"""Збирає метадані джерел (автори, назва, рік, видання) з шапок нотаток для prep.py.

Запуск із кореня репозиторію або з цієї теки:
    python3 refmeta.py ../../70_writing/abstract.md ../../70_writing/ch1.md
Результат — refmeta.json поруч зі скриптом. Мережі не потребує, тож працює локально.
"""
import json, os, re, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = os.path.join(HERE, '..', '..', '10_literature', 'notes')

keys = []
for path in sys.argv[1:]:
    for k in re.findall(r'\[\[@([^\]]+)\]\]', open(path, encoding='utf-8').read()):
        if k not in keys:
            keys.append(k)

meta, missing = {}, []
for k in keys:
    p = os.path.join(NOTES, f'@{k}.md')
    if not os.path.exists(p):
        missing.append(k)
        continue
    txt = open(p, encoding='utf-8').read()
    fm = yaml.safe_load(txt.split('---', 2)[1])
    meta[k] = {f: str(fm.get(f, '') or '') for f in ('title', 'authors', 'year', 'venue', 'doi')}

json.dump(meta, open(os.path.join(HERE, 'refmeta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(meta), 'notes;', 'missing:', missing)
