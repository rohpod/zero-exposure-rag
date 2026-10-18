# Third-party resources

Every library, model, dataset and tool we use is listed here. Add a row as soon as you start using something new. The Datathon submission requires links to all open-source resources.

| Name | Type | Version | Licence | Link | Used for | Added by |
|---|---|---|---|---|---|---|
| Faker | library | 33.3.1 | MIT | https://github.com/joke2k/faker | Synthetic banking data generation in data/generate.py | Kishan |
| deepset/prompt-injections | dataset | — | Apache-2.0 | https://huggingface.co/datasets/deepset/prompt-injections | Training data for prompt-injection classifier (injection vs. benign text) | Kaustubh |
| requests | library | 2.34.2 | Apache-2.0 | https://pypi.org/project/requests/ | HTTP client for the red-team harness (run_suite.py) calling POST /ask | Kashvith |
| rank_bm25 | library | 0.2.2 | Apache-2.0 | https://github.com/dorianbrown/rank_bm25 | BM25 retrieval for RAG pipeline (Stage 1 retrieval track) | Kishan |
| scikit-learn | library | 1.4.1.post1 | BSD-3-Clause | https://scikit-learn.org/ | TF-IDF + logistic regression injection classifier (app/guards/train_injection.py); installed via apt (python3-sklearn) on VM, not pip, due to s390x build failures | Kaustubh |

Types: library, model, dataset, tool.

For datasets, confirm the licence allows our use before adding them to the training or evaluation pipeline.
