# DanskHjælp

A personal Danish learning assistant that lives in Telegram.

It is my go-to Danish translator **and** a spaced-repetition tutor in one: every word I look up, every book page I photograph and every grammar question I ask is saved to a database. Throughout the day it pings me with short (~5 minute) quizzes built from exactly that material, so the things I keep forgetting (adjective forms, en/et, irregular verbs) come back until they stick.

- **Level:** intermediate (currently at *lavere mellemniveau*)
- **Interface language:** Danish everywhere, with an English fallback on demand
- **Platform:** iPhone (Telegram + iOS Shortcuts), backend in Python on Azure
- **Second goal:** a hands-on project for learning Azure, Terraform and CI/CD

---

## Core ideas

1. **Lookup = capture.** I use the bot as my translator, and every lookup saves and schedules the word automatically. No separate "add a card" step.
2. **Plain code runs the schedule, not the LLM.** Spaced repetition (FSRS) is a deterministic algorithm. Claude is used only where it adds value: explaining, extracting from scans, writing example sentences and grading free-text answers.
3. **Structured data first, vectors on top.** Words, cards and reviews live in normal SQL tables. Full-text search and embeddings are used to search my own materials, not to drive learning.
4. **My own material is the curriculum.** Example sentences and gap-fills come from the pages I actually study.
5. **Never trust the model blindly.** Danish inflections and genders are checked: extracted items are confirmed (✅ / ✏️), uncertain answers are flagged ⚠️, and corrections are stored once and reused.

---

## Features

### 1. Lookup (translator)
Send anything to the bot:

| Input | Example |
|---|---|
| Danish word (any form) | `stort`, `købte` |
| English word | `proud` → *stolt* |
| Phrase / idiom | `det går nok` |
| Word + context sentence | `stort — "Det var et stort problem for dem"` |
| Screenshot / photo | a word circled on a page |

Flow:
1. Normalize to the base form (`stort` → **stor**), keeping the form I actually looked up.
2. **Check the database first.** If the word is known, answer instantly from the DB (free and consistent) and show my history: *"Du har slået det op 3 gange · 60 % rigtige."*
3. If new: Claude writes the entry, which is saved.
4. Reply with an answer card:

```
stor (adj.)
stor · stort · store — større · størst

🇩🇰 Noget, der fylder meget eller er mere end normalt.
🇬🇧 big, large, great

Eks: Det var et stort problem for dem.
Pas på: stor ≠ høj (om personer)

[🇬🇧 Mere på engelsk] [🔊 Udtale] [✏️ Ret] [🚫 Lær ikke]
```

5. Auto-schedule: a new word gets its first review in the next ping (~2 h). Looking the same word up again marks it as *struggling* and increases review frequency.

### 2. Material intake (scans, book pages, notes, questions)
Every upload goes through the same pipeline:

```
upload (photo / scan / text / question)
   │
   ▼
1. KEEP THE ORIGINAL → file saved + documents row (source, date, type, tags)
2. TRANSCRIBE        → Claude vision (print + handwriting); I confirm what was read
3. EXTRACT           → words → items + cards
                       grammar rules → rule cards
                       sentences → example bank (gap-fills)
                       exercises → quiz tasks
4. INDEX             → chunks → Postgres full-text search + embeddings (pgvector)
```

| I send | It becomes |
|---|---|
| Book page | suggested words to tick off, example sentences, searchable page text |
| Notebook scan | transcription I check, then extracted rules and words |
| Grammar question (*"sin vs. hans?"*) | answer in DA + EN, saved as a note, optional quiz card |
| Longer text / article | unknown words found, text saved as reading material |

### 3. Quizzes (spaced repetition)
- **Pings:** about every 2 hours, 08:00–20:00 (adjustable). Skipped if nothing is due; missed sessions don't pile up beyond a cap.
- **Session:** ~8–12 mixed tasks, about 5 minutes.
- **Task types:**
  - Meaning: DA → betydning, EN → DA
  - Inflection drills: *"et ___ hus (stor)"* → *stort*
  - Gender: *en* eller *et* bord?
  - Gap-fill sentences from my own material
  - Look-alike drills: *glad / lykkelig / tilfreds* (phase 2)
  - Free sentence writing, graded by Claude in Danish
- **Scheduling:** FSRS per card. Each item has several cards (meaning, gender, each tricky form), so I can know *stor* but still be drilled on *store*.

### 4. Ask my materials (phase 2)
*"Hvad skrev jeg om inversion?"* → finds my own notebook page. Hybrid search: exact (Postgres full-text search with its `danish` configuration, best for Danish word forms) + semantic (pgvector, best for questions).

### 5. Progress
Weekly summary (*"Ugens svære ord"*), accuracy per word type, streaks. Later: a web dashboard.

---

## Architecture

```
iPhone
 ├─ Telegram app ──────────┐ webhook
 └─ iOS Shortcut "Slå op" ─┤ (HTTPS + secret, milestone 3)
                           ▼
Azure (swedencentral)
 ├─ Container App: FastAPI + Telegram handlers (lookup, intake, quiz answers)
 ├─ Container Apps Job (cron): quiz pings every ~2 h (M2)
 ├─ Container Apps Job: database migrations during deploys
 ├─ Postgres Flexible Server + pgvector (private network)
 │    ├─ learning core: items, cards, reviews, lookups
 │    ├─ materials: documents, chunks, item_sources
 │    └─ search: Danish full-text search + embeddings
 ├─ Blob Storage: original scans (M3)
 ├─ Key Vault + managed identity: secrets, no passwords in code
 └─ Container Registry, Log Analytics, budget alerts

GitHub Actions ── OIDC, no stored Azure secrets ──► Terraform + deploys
```

The messaging layer is kept thin, so a WhatsApp adapter can be added later without touching the core.

### Stack

| Part | Choice |
|---|---|
| Language | Python 3.12 (`uv`, `ruff`, `mypy`, `pytest`) |
| Web + bot | FastAPI + [`python-telegram-bot`](https://python-telegram-bot.org/) in webhook mode |
| Spaced repetition | [`fsrs`](https://pypi.org/project/fsrs/) |
| Database | Postgres Flexible Server + [`pgvector`](https://github.com/pgvector/pgvector), SQLAlchemy + Alembic |
| AI | Claude API: a small, fast model for lookups and grading, a stronger model for vision and long texts |
| Embeddings | Local multilingual embedding model (phase 2) |
| Hosting | Azure Container Apps |
| Infrastructure as code | Terraform (`infra/bootstrap`, `infra/shared`, `infra/app`) |
| CI/CD | GitHub Actions with OIDC sign-in to Azure |

### Environments and delivery

- **dev** and **prod** use the same Terraform with different variables, a separate Telegram bot each, and separate databases on one shared Postgres server.
- **On every PR:** lint, types and tests; Terraform `fmt`, `validate`, tflint, security scan, and a `plan` posted to the PR.
- **On merge to `main`:** build the image → deploy to dev → migrate → smoke test → **wait for approval** → same image to prod.

### How this project is built

Claude writes the code, Terraform and pipelines, with a short explanation of each step. Each PR carries a "what this does and what the concept is" note, so the PR history is a learning log. Prod only deploys after my approval. Secrets never go in chat, the repo or Terraform variables.

---

## Data model

### Learning core
| Table | Purpose | Key fields |
|---|---|---|
| `items` | One learnable thing (word, phrase, rule) | `lemma`, `pos`, `gender`, `forms` (JSONB), `meaning_da`, `meaning_en`, `example`, `notes`, `status` (`set` → `lærer` → `kan`, or `ignoreret`), `verified` |
| `cards` | One quizzable aspect of an item | `item_id`, `task_type` (meaning, gender, form:t, form:e, …), FSRS state, `due` |
| `reviews` | Every answer I give | `card_id`, `ts`, `grade`, `answer`, `response_ms`, `used_english` |
| `lookups` | Every lookup | `item_id`, `ts`, `query` (exact form sent), `context_sentence`, `direction` (DA→EN / EN→DA), `used_english` |

### Materials
| Table | Purpose | Key fields |
|---|---|---|
| `documents` | One upload | `type` (book_page, notebook, text, question), `file_path`, `source`, `tags`, `created_at` |
| `chunks` | Transcribed text pieces | `document_id`, `page`, `text`, embedding (phase 2) |
| `item_sources` | Where an item came from | `item_id`, `document_id` / `chunk_id` |

`documents` and `chunks` are created from M1, so early lookups already record their source.

---

## Milestones

- [ ] **M0 – Foundation.** Repo, Terraform, pipelines and a basic bot replying in Danish from Azure, in dev and prod. Every later feature ships through this pipeline.
- [ ] **M1 – Lookup bot.** Word in → answer card → saved. DB-first lookup, base-form normalization, ✏️ corrections. *Useful from day one.*
- [ ] **M2 – Quizzes.** FSRS cards, pings every ~2 h as a Container Apps Job, meaning, gender and inflection tasks, quiet hours, backlog cap.
- [ ] **M3 – Intake.** Photos, scans and screenshots via Claude vision with a confirm step, originals in Blob Storage. iOS Shortcut "Slå op".
- [ ] **M4 – Richer tasks.** Gap-fills from saved sentences, free-sentence grading, grammar rule cards.
- [ ] **M5 – Search & vectors.** Postgres full-text search + pgvector, "ask my materials", look-alike drills, topic sessions, deduplication.
- [ ] **M6 – Beyond.** Weekly report, web dashboard on the same DB, optional WhatsApp adapter, Danish TTS.

---

## Setup

External prerequisites:
1. **Azure subscription** and the `az` CLI.
2. **GitHub account** and the `gh` CLI.
3. **Two Telegram bot tokens** (dev and prod), from [@BotFather](https://t.me/BotFather).
4. **Anthropic API key** (from M1), from [console.anthropic.com](https://console.anthropic.com).

In Azure, secrets live in Key Vault and are set directly with the `az` CLI. For local development they go in a `.env` file, which is **never committed**. Run commands are added as each part lands.

---

## Costs (estimate)

| Item | Cost per month |
|---|---|
| Telegram Bot API, GitHub Actions | free |
| Azure Container Apps | ~$0–5 (monthly free allowance; depends on whether it scales to zero) |
| Postgres Flexible Server (smallest size) | ~$15–20 |
| Azure Container Registry (Basic) | ~$5 |
| Claude API | a few dollars at most |
| **Total** | **~$25–30** |

These are estimates, to be checked against the Azure pricing calculator before the first deploy. Budget alerts at $10, $20 and $30 are part of the Terraform.

WhatsApp was considered: messages are free inside the 24-hour window after I last write, but setup (Meta Business account, separate number, approved templates) is much heavier. Deferred to M6.

---

## Decisions log

| Decision | Why |
|---|---|
| Telegram over WhatsApp | Zero setup, free push, inline buttons, works well on iPhone |
| Telegram bot over native app / PWA | Fastest path to something I use daily. A web dashboard can be added later on the same DB |
| Azure + Terraform over a cheap VPS | Costs more, but learning them is a goal of the project |
| Container Apps over a VM | Serverless containers, scaling and revisions are more useful to learn than server admin |
| Postgres + pgvector over SQLite | SQLite locking is reported to fail on Azure Files. Postgres also has Danish full-text search and keeps vectors in the same database |
| GitHub Actions + OIDC | Free at this size, widely used, and no long-lived Azure secrets |
| Dev + prod with one Postgres server | Real promotion practice, at a lower cost than two servers |
| FSRS over custom intervals | State-of-the-art, used by Anki, maintained Python package |
| Danish-first UI | Immersion, with English available on demand and logged as a signal |
