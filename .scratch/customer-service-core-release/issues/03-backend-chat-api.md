# 03: Backend Chat API

**Status:** done

POST /api/v1/chat accepts a Bearer API key and JSON question. The API key selects the business, rate limits requests by key, and returns the existing RAG result as JSON. It has no CORS headers; browser clients use the embed widget instead.
