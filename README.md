# BIG DATA ENERGY: Zero-Exposure RAG

IBM Z Datathon 2026 | Theme: AI Secured, Innovation Without Exposure | Platform: IBM LinuxONE Community Cloud | Event code: SSF2026

> **Repository status.** This repository was created before the event with documentation and configuration files only. All project code was written during the Datathon window, 17 to 18 October 2026. The commit history shows this.

## Problem

To be completed at submission.

## Solution overview

To be completed at submission.

## Architecture

To be completed at submission. The flowchart image will be added under docs/.

## How it uses IBM Z and LinuxONE

To be completed at submission. Include the instance details, what runs on it and the evidence screenshots.

## Getting started

### Prerequisites

Ensure the following tools and environment are set up on the host (e.g. LinuxONE s390x VM with Ubuntu 24.04):
- **Docker** 24.0+
- **Python** 3.12+ (if running generation or test scripts outside Docker)

#### 1. Configure local auth tokens
Copy the example token mapping to the git-ignored local configuration file:
```bash
cp app/auth_tokens.example.json app/auth_tokens.local.json
```

#### 2. Generate synthetic corpus and models (host-side)
If running or testing locally on the host:
- Generate the synthetic banking documents (`data/generated/documents.json`), relevance fixtures, and customer records:
  ```bash
  python3 data/generate.py
  ```
  *(Note: this step is also automatically executed during `docker build` so the image contains the generated corpus).*

- Train the injection classifier and TF-IDF vectorizer (creates `models/injection_classifier.pkl` and `models/injection_vectorizer.pkl`):
  ```bash
  python3 app/guards/train_injection.py
  ```

#### 3. Model weights
Create the `models/` directory and place the Granite GGUF model inside it:
```bash
mkdir -p models
# Copy or download granite-4.0-h-350m-base-be.f16.gguf into models/
```
Model location expected by the pipeline:
`models/granite-4.0-h-350m-base-be.f16.gguf` (see [docs/environment.md](docs/environment.md) for details).

---

### Run

#### 1. Build the Docker image
Build the container image from a clean checkout without using cache:
```bash
docker build --no-cache -t zero-exposure-rag .
```

#### 2. Run the container

##### Option A: Default Stub Mode
Runs the container in stub mode (deterministic canned responses, no model weights required):
```bash
docker run -d -p 8000:8000 \
  -v $(pwd)/app/auth_tokens.local.json:/app/app/auth_tokens.local.json \
  --name rag-stub zero-exposure-rag
```

##### Option B: Real Mode (Live Model & Trained Guards)
Runs the full pipeline with live LLM inference and trained injection models mounted into the container:
```bash
docker run -d -p 8000:8000 \
  -e STUB_MODE=0 \
  -v $(pwd)/models:/app/models \
  -v $(pwd)/app/auth_tokens.local.json:/app/app/auth_tokens.local.json \
  --name rag-prod zero-exposure-rag
```

#### 3. Verify endpoints

##### Health Check
Verify service status and whether the model is loaded:
```bash
curl -s http://localhost:8000/health
```
Expected response:
```json
{"status":"ok","stub_mode":...,"model_loaded":...}
```

##### Pipeline Requests (`/ask`) across Role Tokens
Verify requests with each role's token:

- **Support Agent** (`tok_support_01`, clearance level 1):
  ```bash
  curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -H "X-User-Token: tok_support_01" \
    -d '{"query": "What are the standard branch operating hours?"}'
  ```

- **Fraud Analyst** (`tok_fraud_01`, clearance level 2):
  ```bash
  curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -H "X-User-Token: tok_fraud_01" \
    -d '{"query": "Check wire transfer anomalies for account 4821."}'
  ```

- **Compliance Officer** (`tok_compliance_01`, clearance level 3):
  ```bash
  curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -H "X-User-Token: tok_compliance_01" \
    -d '{"query": "Provide executive summary of regulatory audit findings."}'
  ```

##### Inspect Audit Log
Verify that requests are recorded in SQLite audit storage:
```bash
curl -s http://localhost:8000/audit
```

## Results

To be completed at submission. Attack success with guards off versus on, benign false-block rate and latency, from the held-out test set.

## Limitations

To be completed at submission.

## Team

| Name | Role | GitHub |
|---|---|---|
| Rohan | Platform lead | [@rohpod](https://github.com/rohpod) |
| Kishan | Data and retrieval lead | [@anskishan](https://github.com/anskishan) |
| Kaustubh | Guards lead | [@kaus1201](https://github.com/kaus1201) |
| Kashvith | Red team and product lead | [@kash-0825](https://github.com/kash-0825) |

## Documentation

- [Contributing guide](CONTRIBUTING.md)
- [Third-party resources](THIRD_PARTY.md)
- [Technical decisions](docs/decisions.md)
- [Environment setup](docs/environment.md)## Credits

Every library, model and dataset we use is listed with its licence in [THIRD_PARTY.md](THIRD_PARTY.md).

## Licence

MIT. See [LICENSE](LICENSE).
