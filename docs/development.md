# Development guide

## Environment

Python 3.12 and [uv](https://docs.astral.sh/uv/):

```bash
uv venv -p 3.12 .venv
uv pip install -p .venv -r requirements-dev.txt
```

Use `.venv/bin/python` (or activate the environment) for every command below.

## Configuration

```bash
cp .env.example .env
```

`.env` is git-ignored. The defaults use the offline mock LLM (`LLM_PROVIDER=mock`), which needs no key. Every variable is described in `.env.example`. To use Groq, set `LLM_PROVIDER=groq` and `GROQ_API_KEY`. Only synthetic data may be sent to it.

Auth tokens come from `AUTH_TOKENS_JSON` if it is set, otherwise from `AUTH_TOKENS_FILE` (default `app/auth_tokens.local.json`). To use a file: `cp app/auth_tokens.example.json app/auth_tokens.local.json`.

Outside Docker the server does not read `.env` by itself: pass variables inline as in the examples below, or let Docker Compose load the file (`env_file`). Without Docker, use the token file (`app/auth_tokens.local.json`) rather than `AUTH_TOKENS_JSON`, which is awkward to quote in a shell.

## Generate data and train the classifier

```bash
python data/generate.py                 # data/generated/{documents,customers,relevance_fixtures}.json
python data/extract_canaries.py         # data/canary_registry.json (only if canaries change)
python app/guards/train_injection.py    # models/injection_*.pkl
```

Both outputs are git-ignored and deterministic.

## Run the server

```bash
# offline, no key
LLM_PROVIDER=mock uvicorn app.main:app --port 8000

# Groq
LLM_PROVIDER=groq GROQ_API_KEY=... uvicorn app.main:app --port 8000
```

Or with Docker: `docker compose up` (see the README). Check `GET /health`, then call `/ask` with a token header, for example `X-User-Token: tok_support_01`.

## Tests

```bash
pytest -q
```

Tests use the mock provider and a temporary audit database; they never call Groq.

## Red team (dev subset)

The attack suite and the dev subset are committed. Start a server for evaluation:

```bash
EVAL_MODE=1 POISONED_CORPUS=1 LLM_CACHE=1 LLM_PROVIDER=groq GROQ_API_KEY=... \
  uvicorn app.main:app --port 8000
```

Then, with `TOKEN_SUPPORT_AGENT`, `TOKEN_FRAUD_ANALYST` and `TOKEN_COMPLIANCE_OFFICER` exported:

```bash
python redteam/run_suite.py --subset redteam/subsets/dev_small.txt --mode both
python redteam/score.py --results redteam/raw/run_results.jsonl
```

See [redteam.md](redteam.md) for the success rules and runner options. Tune on the dev split only; the test split is for the final run.
