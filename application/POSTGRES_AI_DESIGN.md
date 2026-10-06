# PostgreSQL and executive question interface

The demo now exposes `POST /api/ask`. It accepts natural-language questions and
routes them through an approved, read-only analysis catalog. The response includes
an intent, answer, evidence rows, source type, freshness timestamp and next step.

## Data source

Set `DATABASE_URL` to a PostgreSQL connection string. When it is present, the API
uses PostgreSQL; without it, the local synthetic SQLite fixture remains a fallback
for offline demo use. The PostgreSQL schema is in `database-reference/business-schema.sql`.

The source database is synthetic. A future seed command should load the same master,
order, inventory, purchasing, invoice and direct-fulfillment records into PostgreSQL.

## Question handling

The first catalog supports revenue exposure, customer commitments, delivery/OTIF,
inventory risk, margin, cross-department coordination and supplier expedite questions.
It intentionally rejects unsupported questions instead of inventing an answer. The
next provider adapter can send only the question and approved tool descriptions to
the configured AI model. The model must call read-only tools; write tools remain
separate and require human approval.

Use environment variables for a future model provider:

```text
AI_BASE_URL=
AI_MODEL=
AI_API_KEY=
# Optional backup OpenAI-compatible provider. It is tried only if the primary fails.
AI_FALLBACK_BASE_URL=
AI_FALLBACK_MODEL=
AI_FALLBACK_API_KEY=
```

Never commit credentials. The dashboard labels results synthetic and shows the data
source and freshness with each answer.

AI provider calls are capped at 40 per rolling minute by the API process. Advanced read-only analysis can consume two calls: one to propose a query and one to summarize the validated evidence.
