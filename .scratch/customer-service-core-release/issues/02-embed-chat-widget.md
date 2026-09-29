# 02: Embed chat widget

**Status:** done

The external script adds a keyboard-accessible floating chat button and a business-bound iframe. The iframe endpoint accepts the public embed token, applies Content-Security-Policy frame-ancestors from that business's allowlist, uses the existing RAG chat flow, and returns 404 for invalid or rotated tokens.
