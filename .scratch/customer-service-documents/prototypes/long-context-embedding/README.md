# PROTOTYPE: Longer-context embedding for Markdown retrieval

Question: does `intfloat/multilingual-e5-small` improve Thai Markdown retrieval, and does increasing the chunk budget help independently of the embedding model?

Run from the repository root with:

```sh
HF_HUB_OFFLINE=1 .venv/bin/python .scratch/customer-service-documents/prototypes/long-context-embedding/compare.py
```

The prototype compares current MiniLM chunks at 128 tokens, E5 on the same chunk text, and E5 with a 256-token chunk budget. It uses the AquaFlow example, does not read or change the app database/vector index, and saves results to `report.md`. If `.env` contains OpenRouter settings, it also compares three fixed answer cases using that configured model and prompt.
