# Збирання розділу в .docx (бета)

`prep.py` перетворює розділ (`70_writing/ch1.md` тощо) на блоки й нумерує посилання `[[@citekey]]` → `[N]` за першою появою, будує перелік джерел за ДСТУ 8302:2015 (автори — з нотаток, решта — з `library.bib`). `build.js` (npm `docx`) збирає документ за ДСТУ 3008:2015: титул → реферат → скорочення → розділ → перелік джерел.

Статус: працює на одному реальному розділі; на вашому тексті можливі дрібні вади оформлення джерел. Виправляються через `overrides.json`, а не правкою коду.

## Що потрібно

- Python 3 + `pyyaml`; Node.js + `npm install docx` у цій теці;
- **pandoc ≥ 2.11** (старіші не читають bibtex).

Найпростіше — попросити Claude зібрати документ у хмарній сесії: там усе це є.

## Кроки

Усе в цій теці (`90_pipeline/build_docx/`):

```
copy ..\..\70_writing\ch1.md .                 # розділ
copy ..\..\70_writing\abstract.md .            # реферат, необов'язково
copy ..\..\70_writing\abbreviations.md .
copy ..\..\70_writing\title.md .               # титульна сторінка, необов'язково
pandoc ..\..\00_admin\library.bib -f bibtex -t csljson -o lib.json
python refmeta.py ..\..\70_writing\abstract.md ..\..\70_writing\ch1.md   # → refmeta.json
python prep.py ch1.md                         # → doc.json
node build.js ch1.docx                        # → ch1.docx
```

## overrides.json (необов'язковий)

Коли `.bib` дає криві метадані (корпоративний автор, немає назви видання):

```json
{
  "author2025": {"authors": [["Прізвище", "І. П."]], "container": "Proceedings of ..."},
  "other2023": {"authors_from": "bib"}
}
```

Проміжні `*.json` і `*.docx` у цій теці ігноруються git.
