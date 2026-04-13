# Incident Memory Copilot

Incident Memory Copilot is a hackathon-ready AI incident response agent for engineering and DevOps teams. It uses Groq for fast troubleshooting guidance and Hindsight by Vectorize as the persistent memory layer so the system can remember prior incidents, recall similar failures, and improve recommendations over time.

## Why this fits the hackathon

- Solves a real business problem: faster incident triage and repeat outage resolution.
- Makes memory central to the product, not incidental.
- Shows a visible before-and-after: first incident gets a general fix, later incidents get memory-guided fixes.
- Demonstrates persistent learning with Hindsight retain and recall.

## What the demo shows

- A black, dashboard-style UI built for a live hackathon demo.
- Incident classification, similarity band, and repeat counts.
- Matched prior incident context and remembered fix.
- A session incident feed that makes the learning curve visible.
- Fallback local troubleshooting guidance when Groq is not configured, so the app still demos cleanly.

## Stack

- FastAPI backend
- Vanilla HTML/CSS/JS frontend served by FastAPI
- Groq LLM for remediation suggestions
- Hindsight Memory for retain and recall

## One-command local run

1. Go to the project:
   ```bash
   cd ai-incident-fix-engine
   ```

2. Copy the environment template if needed:
   ```bash
   cp .env.example .env
   ```

3. Add your keys to `.env`:
   - `GROQ_API_KEY=gsk_your_real_key_here`
   - `HINDSIGHT_API_KEY=your_hindsight_key`
   - `HINDSIGHT_BANK_ID=your_bank_id`
   - `HINDSIGHT_ORG_PATH=your_org_path`

4. Start everything with one command:
   ```bash
   ./run.sh
   ```

5. Open:
   - App: `http://127.0.0.1:8000`
   - API docs: `http://127.0.0.1:8000/docs`

## Demo flow for judges

1. Run `sqlite3.OperationalError: no such table: users`
   The app treats it as a new incident and stores the fix in memory.

2. Run a similar error such as `sqlite3.OperationalError: no such table: user_data`
   The app recalls the prior issue, shows that memory was used, and responds with a stronger fix path.

3. Switch to another sample incident from the quick chips.
   The incident feed starts showing repeated learning behavior over multiple runs.

## Troubleshooting

If Hindsight returns `401 Invalid organization path`, update:

```bash
HINDSIGHT_ORG_PATH=your_org_path
```

Then restart `./run.sh`.
