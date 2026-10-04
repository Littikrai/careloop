# Customer Service Bot

Self-hosted, multi-business customer support. Administrators create and publish Q&A, questions are embedded locally on CPU, Qdrant retrieves knowledge from the current business, and OpenRouter produces an answer from that knowledge.

## Install with Docker Compose

Requires Docker Engine/Desktop with Compose and Python 3 to generate the local configuration. No GPU is needed. Initial setup downloads the image and Python packages.

```sh
python3 scripts/setup_env.py
# Windows: use `py scripts/setup_env.py` if `python3` is unavailable.
# Open .env and set OPENROUTER_API_KEY before testing generated answers.
docker compose up --build -d
# Wait until `docker compose ps` reports healthy, then:
docker compose exec web python manage.py createsuperuser
```

Choose your own administrator username and password in the interactive prompt. No default password is shipped. Keep the password private; password input is hidden. Every account created with `createsuperuser` manages all businesses. There is no customer registration or per-business role management.

The first Docker startup downloads and warms the configured sentence-transformers model; it may take several minutes on CPU. When `docker compose ps` reports healthy, open http://localhost:8080/admin/, sign in, select **Businesses → Add business**, and save a name. Then open **Q&A → Add Q&A**, select the business, enter a question and answer, and save the draft. On the Q&A list, select one or more drafts and choose **Publish selected Q&A**. An item is available to chat only after its status is **Published** and its index status is **Ready**.

To change a published Q&A, select it and choose **Create replacement drafts for selected Q&A**. Edit the resulting draft and publish it; customers keep receiving the old answer until the replacement is indexed. Use the standard **Delete** control and its confirmation page to remove a Q&A. A deleted item is excluded from future answers even if local vector cleanup is temporarily unavailable.

Use **Open chat** on the business list to visit its public page. Visitors do not need an account. The bot retrieves only published Q&A from that business. An exact question match after Unicode and whitespace normalization takes priority; semantic scores only choose candidate sources. If no result meets the similarity threshold, it does not call OpenRouter and reports that it lacks enough information. Answers display a “Verified answer” source label. An unknown business URL returns 404. Use **Log out** to end the administrator session.

## Import Q&A from JSON

On the **Businesses** list, select **Import Q&A from JSON**, choose the target business, and upload a UTF-8 JSON array. Download or copy [the example file](examples/qa-import.example.json) as a starting point:

    [
      {"question": "When are you open?", "answer": "Every day, 09:00–18:00."}
    ]

Each item must contain exactly the question and answer strings. The importer trims text and normalizes Unicode. It validates the complete file before changing data, skips duplicate pairs, and rejects the entire file if a question conflicts with an existing answer. Imported entries are drafts; select them in **Q&A** and use **Publish selected Q&A** before the bot can answer from them.

## Add document drafts

Open **Documents → Add Document** in the admin, choose a business, then paste text or upload one UTF-8 `.txt`/`.md` file up to 256 KiB. A file name becomes the default title; you can also enter a title yourself. Product and version are optional. Save and open the draft to inspect its normalized text, character count, metadata, and ordered chunk preview. You can edit a draft. Document drafts are not searchable or used in chat yet; publishing and document-based answers are covered by later build tickets.

## Embed on a business website

In the admin, add an entry under **Business integrations**, choose its business, and add one allowed website origin on each line. Use exact origins, for example https://shop.example and http://localhost:3000; paths and wildcards are not accepted. Open the saved integration to copy its widget tag:

    <script async src="https://your-bot.example/static/businesses/widget.js" data-token="..."></script>

The script creates an accessible floating Chat button and opens the business-bound chat in an iframe. Press Escape to close it. The same admin page provides a direct iframe URL for layouts that need to position the chat themselves. The iframe sends the existing public chat form to this service; it does not put the OpenRouter key or an API key in the browser.

The integration page can rotate the embed token. Rotation invalidates the old widget immediately, so copy the new tag before deploying it. It can also create an API key for a later backend integration; the complete key appears in the one-time admin message, while the database retains only its hash. Creating a replacement key keeps the previous key usable for 24 hours; administrators may revoke any key earlier from **Business API keys**.

## Backend Chat API

Use **Create or rotate API key** on a Business integration, copy the one-time key into the business backend, then make this server-to-server request:

    curl http://localhost:8080/api/v1/chat \
      -H 'Authorization: Bearer YOUR_API_KEY' \
      -H 'Content-Type: application/json' \
      --data '{"question":"When are you open?"}'

A successful response has `answer`, `status` (`answer`, `needs_clarification`, or `insufficient_knowledge`), and `sources` (an array of public labels such as `{"type":"qa","label":"Verified answer"}`). Invalid or revoked keys return 401; malformed questions return 422; exhausted API-key rate limits return 429; RAG or LLM failures return 503. This endpoint deliberately has no CORS support, so do not put its API key in browser code. Use the widget for browser chat.

SQLite data, Qdrant vectors, and the downloaded embedding model live in the `app_data` Docker volume. `docker compose restart` and `docker compose down` keep it. `docker compose down -v` deletes that volume and its data. Keep `.env` when restarting: changing its secret invalidates existing login sessions. To reset a password, run `docker compose exec web python manage.py changepassword USERNAME`.

The published port binds to the local machine only. Before exposing the service publicly, configure an HTTPS reverse proxy, trusted hosts, secure cookies, and access-rate limits appropriate to your deployment. `DJANGO_HTTPS_ONLY=true` enables HTTPS redirects and secure cookies; the proxy must provide a correctly trusted HTTPS scheme to the application. Public HTTPS deployment is not tested in this slice.

## Configuration

`.env` is read by Compose and is excluded from Git and the Docker build context. `scripts/setup_env.py` refuses to overwrite it.

| Setting | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required random secret of at least 50 characters; generated by setup |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts; local addresses by default |
| `DJANGO_HTTPS_ONLY` | Enable HTTPS-only cookies and redirects; false for local HTTP |
| `DATA_DIR` | Persistent data directory; `/data` in the container |
| `OPENROUTER_API_KEY` | Required server-side key for generated answers |
| `OPENROUTER_MODEL` | OpenRouter model slug; defaults to `openrouter/free` for trials. Use a fixed compatible model for predictable production answers. |
| `EMBEDDING_MODEL` | sentence-transformers model; changing it requires reindexing in a later ticket |
| `DOCUMENT_CHUNK_MAX_TOKENS` | Upper bound for document preview chunks; defaults to `256` and is capped by the embedding model's sequence limit |
| `RAG_SCORE_THRESHOLD` | Minimum cosine score; defaults to `0.55` |
| `RAG_TOP_K` | Maximum Q&A entries sent to the LLM; defaults to `3` |
| `CHAT_RATE_LIMIT_PER_MINUTE` | Questions per client IP and business; defaults to `30` |
| `API_RATE_LIMIT_PER_MINUTE` | Questions per API key per minute; defaults to `30` |
| `PUBLIC_BASE_URL` | Public base URL used in admin widget and iframe installation code; defaults to `http://localhost:8080` |

The OpenRouter key is never rendered into a page. Every completion requires strict JSON Schema support; an incompatible model/provider returns a service error. The current chat is single-turn; conversation persistence belongs to a later ticket. The in-process rate limit matches the single Gunicorn worker and should use a shared cache if a deployment adds workers or replicas.

## Local development and checks

Python 3.14 is used by the container. These commands use a POSIX shell; on Windows use the equivalent virtualenv activation and environment-variable syntax.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/setup_env.py
set -a
. ./.env
set +a
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

`runserver` is for development only; Docker uses Gunicorn and WhiteNoise. Do not deploy using `config.test_settings`: it intentionally uses a public test key and fast password hashing.

```sh
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python -m mypy
python manage.py test --settings=config.test_settings
```

Tests cover the administrator create/list flow, JSON import and its validation, draft and bulk publish behavior, failed indexing, Qdrant business isolation, OpenRouter request boundaries, public chat and widget behavior, API authentication and rate limits, CSRF, input validation/escaping, and persistence through separate processes.

## Verification status

Application tests and type checking run on macOS with Python 3.14. The Docker image was built and started on macOS with CPU-only PyTorch; its health check passed, and the configured multilingual model produced a real 384-dimensional embedding from inside the container. The OpenRouter request boundary is covered by tests; generated answers require an operator-provided API key and have not been sent to a real provider during verification. Windows and Linux installation remain targets, not verified platforms. No capacity or latency claim is made.

## Planning

See [document knowledge build tickets](.scratch/customer-service-documents-build/README.md), [document knowledge decisions](.scratch/customer-service-documents/map.md), [core release tickets](.scratch/customer-service-core-release/README.md), [future build tickets](.scratch/customer-service-build/README.md), and [domain language](CONTEXT.md). Feedback/insights remain future work.

## License

Released under the [MIT License](LICENSE).
