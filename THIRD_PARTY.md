# Third-party resources

Every library, model, dataset, service and tool we use is listed here. Add a row as soon as you start using something new.

| Name | Type | Version | Licence | Link | Used for |
|---|---|---|---|---|---|
| FastAPI | library | 0.143.3 | MIT | https://fastapi.tiangolo.com/ | HTTP API (`app/main.py`) |
| Uvicorn | library | 0.54.0 | BSD-3-Clause | https://www.uvicorn.org/ | ASGI server |
| Pydantic | library | 2.14.1 | MIT | https://docs.pydantic.dev/ | Request/response models |
| httpx | library | 0.28.1 | BSD-3-Clause | https://www.python-httpx.org/ | Groq API client (`app/llm/groq.py`) |
| rank_bm25 | library | 0.2.2 | Apache-2.0 | https://github.com/dorianbrown/rank_bm25 | BM25 retrieval |
| scikit-learn | library | 1.9.1 | BSD-3-Clause | https://scikit-learn.org/ | TF-IDF + logistic regression injection classifier (`app/guards/train_injection.py`) |
| pytest | tool | 9.1.1 | MIT | https://docs.pytest.org/ | Test runner (dev only) |
| requests | library | 2.34.2 | Apache-2.0 | https://pypi.org/project/requests/ | HTTP client for the red-team runner (`redteam/run_suite.py`, dev only) |
| Chart.js | library | 4.4.4 | MIT | https://www.chartjs.org/ | Attack-success chart in the dashboard (vendored) |
| deepset/prompt-injections | dataset | n/a | Apache-2.0 | https://huggingface.co/datasets/deepset/prompt-injections | Training data for the prompt-injection classifier |
| Groq API | hosted service | n/a | Groq terms of service | https://console.groq.com/ | Hosted LLM inference on the free tier (`LLM_PROVIDER=groq`) |
| Qwen 3.8 27B (`qwen/qwen3.8-27b`) | model | n/a | See the model card on Hugging Face (Qwen) | https://huggingface.co/Qwen | Answer generation via Groq; the licence on the model card governs its use |

Types: library, model, dataset, service, tool.

Prompts go to a hosted service (Groq) when `LLM_PROVIDER=groq`, so only synthetic data may be used with it. For datasets, confirm the licence allows our use before adding them to the training or evaluation pipeline.
