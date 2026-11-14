# Standalone Scripts

These are demos, experiments, or maintenance utilities; they are not imported by the FastAPI app.
Run package modules from the repository root so shared modules such as `db_config` resolve:

```sh
python -m scripts.generate_data
python load_data.py
python ingest.py
python -m scripts.ai_query
```

Database/LLM scripts require the appropriate ignored `.env` values. `scripts/main.py`, `scripts/chunk_test.py`, and `scripts/embedding_test.py` are local experiments; `scripts/app.py`, `scripts/copilot.py`, `scripts/query.py`, and `scripts/database.py` are earlier examples, not the served API. The canonical web entry point is `ask_api:app`.
