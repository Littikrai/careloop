import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from .models import DocumentRevision
from .vector_store import embedding_tokenizer


@dataclass(frozen=True)
class PreviewChunk:
    order: int
    heading: str
    text: str
    embedding_text: str
    token_count: int


def _offsets(tokenizer: Any, text: str) -> list[tuple[int, int]]:
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, verbose=False)
    offsets = [(int(start), int(end)) for start, end in encoded["offset_mapping"]]
    if len(offsets) != len(encoded["input_ids"]) or any(end <= start for start, end in offsets):
        raise ValueError("The embedding tokenizer must provide valid token offsets for document preview.")
    return offsets


def _sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    lines: list[str] = []
    for line in content.split("\n"):
        match = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            body = "\n".join(lines).strip()
            if body:
                sections.append((heading, body))
            heading, lines = match.group(1), []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if body:
        sections.append((heading, body))
    elif heading and not sections:
        sections.append((heading, heading))
    return sections


def _metadata_prefix(revision: DocumentRevision, heading: str, tokenizer: Any, budget: int) -> str:
    fields = [
        ("product", revision.product), ("version", revision.version),
        ("title", revision.title), ("heading", heading),
    ]
    prefix = "\n".join(f"{name}: {value}" for name, value in fields if value)
    if not prefix or budget <= 0:
        return ""
    offsets = _offsets(tokenizer, prefix)
    if len(offsets) > budget:
        prefix = prefix[:offsets[budget - 1][1]].rstrip()
    while len(tokenizer.encode(prefix, add_special_tokens=False)) > budget:
        prefix = prefix[:-1].rstrip()
    return prefix


def preview_chunks(
    revision: DocumentRevision,
    *,
    tokenizer: Any | None = None,
    max_seq_length: int | None = None,
) -> list[PreviewChunk]:
    if tokenizer is None or max_seq_length is None:
        model_tokenizer, model_limit = embedding_tokenizer()
        tokenizer = tokenizer or model_tokenizer
        max_seq_length = max_seq_length or model_limit
    limit = min(int(settings.DOCUMENT_CHUNK_MAX_TOKENS), max_seq_length)
    special_tokens = int(tokenizer.num_special_tokens_to_add(pair=False))
    if limit <= special_tokens + 1:
        raise ValueError("The embedding model token limit is too small for document chunks.")

    chunks: list[PreviewChunk] = []
    previous_body = ""
    previous_offsets: list[tuple[int, int]] = []
    for heading, body in _sections(revision.content):
        prefix = _metadata_prefix(revision, heading, tokenizer, min(32, limit // 4))
        body_budget = limit - special_tokens - len(tokenizer.encode(prefix, add_special_tokens=False))
        if body_budget < 1:
            raise ValueError("Document metadata leaves no room for body text.")
        overlap = min(16, body_budget // 5)
        offsets = _offsets(tokenizer, body)
        if not offsets:
            continue
        carry = (
            previous_body[previous_offsets[max(0, len(previous_offsets) - overlap)][0]:previous_offsets[-1][1]]
            if previous_offsets and overlap else ""
        )
        token_ends = [end for _, end in offsets]
        paragraph_ends = [bisect_right(token_ends, match.start()) for match in re.finditer(r"\n[ \t]*\n", body)]
        start = 0
        previous_end = 0
        while start < len(offsets):
            leading = carry if start == 0 else ""
            leading_tokens = len(tokenizer.encode(leading, add_special_tokens=False)) if leading else 0
            end = min(start + body_budget - leading_tokens, len(offsets))
            boundary_index = bisect_right(paragraph_ends, end) - 1
            if boundary_index >= 0 and paragraph_ends[boundary_index] > max(start, previous_end):
                end = paragraph_ends[boundary_index]
            while end > start:
                text = body[offsets[start][0]:offsets[end - 1][1]]
                if leading:
                    text = f"{leading}\n{text}"
                embedding_text = f"{prefix}\n{text}" if prefix else text
                token_count = len(tokenizer.encode(embedding_text, add_special_tokens=True))
                if token_count <= limit:
                    break
                end -= 1
            if end == start:
                raise ValueError("A document chunk exceeds the embedding model token limit.")
            chunks.append(PreviewChunk(len(chunks) + 1, heading, text, embedding_text, token_count))
            if end == len(offsets):
                break
            previous_end = end
            start = max(start + 1, end - overlap)
        previous_body, previous_offsets = body, offsets
    if not chunks:
        raise ValueError("Document content has no indexable text.")
    return chunks
