# Runtime for the first implementation slice

Implementation choice for **ติดตั้งระบบและจัดการธุรกิจ**, not a claim that all wayfinder decisions are resolved.

- Python / Django 5.2 provides maintained authentication, CSRF protection, migrations and an existing administration interface. Reuse it rather than writing a new authentication system or a separate frontend/API.
- SQLite persists accounts and businesses in the installation's data volume. It avoids another service; its single-writer limit is a reason to revisit the choice if actual write contention warrants it.
- Server-rendered pages and Django admin are the initial UI. English labels are an implementation default, not a restriction on business names or future Q&A languages.
- Gunicorn serves the WSGI application and WhiteNoise serves local static assets. Docker runs as a non-root user, with a named volume for persistent data.
- Embeddings remain sentence-transformers and LLM remains OpenRouter as agreed, but neither service nor a vector database is needed in this ticket. Model and vector-store selection remains open for the Q&A slice.

References: [Django tutorial](https://docs.djangoproject.com/en/5.2/intro/tutorial02/) and [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
