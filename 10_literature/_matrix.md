# Матриця джерел

Панель керування оглядом. Кожна таблиця — окрема черга роботи.

Порядок статусів: `imported` → `summarized` → `verified`.
Насичення — за правилом `00_admin/protocol.md`, розд. 8; ядро ≈ третина бази.

---

## 1. Черга на аналіз (Stage 2)

Метадані є, аналізу ще нема.

```dataview
TABLE year, venue, file.link AS "Нотатка"
FROM "10_literature/notes"
WHERE status = "imported" OR status = null
SORT year DESC
```

---

## 2. Черга на верифікацію

Claude заповнив — треба звірити метрики й датасети з PDF і поставити `verified_by_human: true`.

```dataview
TABLE year, key_finding, metrics
FROM "10_literature/notes"
WHERE status = "summarized" AND verified_by_human = false
SORT year DESC
```

---

## 3. Ядро огляду — по задачах

Групування по `task` дає скелет розділу огляду (теоретичні основи по задачах).

**Аналізу існуючих рішень ця таблиця не дає** — він потрібен у зрізі по системах і по недоліках, а не по задачах. Матеріал для нього — блоки «Обмеження» і «чого не брати» в тілі нотаток; у front matter їх немає, тому Dataview їх не збере.

```dataview
TABLE WITHOUT ID file.link AS "Джерело", year, method, datasets, relevance
FROM "10_literature/notes"
WHERE verified_by_human = true
GROUP BY task
SORT rows.year DESC
```

---

## 4. Висока релевантність

```dataview
TABLE year, key_finding, metrics
FROM "10_literature/notes"
WHERE relevance = "High"
SORT year DESC
```

---

## 5. Джерела мовою фокусу

Джерела з даними мовою вашої роботи (`focus_language` у `00_admin/config.md`). Скіл `vault-setup` підставляє код мови нижче; вручну — замініть `uk` у рядку `WHERE`.

```dataview
TABLE year, datasets, metrics
FROM "10_literature/notes"
WHERE contains(string(language), "uk")
SORT year DESC
```

---

## 6. Немає повного тексту

Нотатки зроблено з абстракту. Числа звідси **не цитувати** — спершу дістати PDF і переписати.

```dataview
TABLE year, venue, doi
FROM "10_literature/notes"
WHERE status = "abstract-only" OR pdf = ""
SORT year DESC
```

---

## 7. Проблеми

Нотатки без задачі, без датасету, або зі статусом поза конвеєром `imported → summarized → verified`.

```dataview
TABLE year, status, task, datasets
FROM "10_literature/notes"
WHERE task = null OR length(datasets) = 0
  OR !contains(list("imported", "summarized", "verified", "abstract-only"), status)
SORT year DESC
```

---

## 8. Прогрес

```dataview
TABLE length(rows) AS "К-сть"
FROM "10_literature/notes"
GROUP BY status
```
