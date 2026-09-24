# Q&A retrieval and answer contract

Implementation choice for **เพิ่ม Q&A แล้วถามบอตได้จริง**.

- Administrators create Q&A as drafts. Publishing embeds the question locally and only marks the item published after the vector is stored successfully.
- The default embedding model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, a CPU-capable multilingual sentence-similarity model. The model name is configurable.
- Qdrant client local mode persists vectors under the existing application data volume. Each business and embedding model uses a separate collection, and retrieved IDs are checked again against published database records from the current business.
- The default OpenRouter model is `openrouter/free`, configurable through `.env`. The API key remains server-side.
- Answers use published Q&A only. General model knowledge is disallowed. When retrieval is below the configured cosine threshold, the application does not call OpenRouter and reports insufficient knowledge.
- Up to three relevant Q&A pairs and the current question are sent to OpenRouter. Conversation history and persisted conversations belong to the later conversation ticket.
- The model is instructed to answer from supplied knowledge, ask one clarifying question if the supplied entries conflict or are ambiguous, and avoid inventing facts. The MVP does not display citations because its source material is the administrator-authored Q&A itself.
- Public chat uses a configurable per-IP, per-business, per-minute limit. The initial in-process counter matches the single Gunicorn worker; use a shared cache if deployment later adds workers or replicas.

References: [Sentence Transformers multilingual models](https://www.sbert.net/examples/sentence_transformer/training/multilingual/README.html), [Qdrant local quickstart](https://qdrant.tech/documentation/quickstart/), and [OpenRouter chat completion API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request).
