import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from .models import DocumentRevision
from .vector_store import document_embedding_prefix, embedding_tokenizer

CHUNKER_VERSION = settings.DOCUMENT_CHUNKER_VERSION
_NUMERIC_VALUE_WITH_UNIT = re.compile(
    r"(?<!\w)[+-]?\d+(?:[.,]\d+)?(?:\s*[-–—]\s*[+-]?\d+(?:[.,]\d+)?)?"
    r"\s*[\w°%µμ]+(?:[/·^][\w°%µμ+-]+)*"
)
_LIST_ITEM_MARKER = re.compile(r"^[ \t]{0,3}(?:[-*+]|\d+[.)])[ \t]+")
_MARKDOWN_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


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


def _numeric_unsafe_token_ends(text: str, token_ends: list[int]) -> set[int]:
    unsafe: set[int] = set()
    for match in _NUMERIC_VALUE_WITH_UNIT.finditer(text):
        first = bisect_right(token_ends, match.start()) + 1
        stop = bisect_left(token_ends, match.end()) + 1
        unsafe.update(range(first, stop))
    return unsafe


def _safe_chunk_end(offsets: list[tuple[int, int]], end: int, unsafe_ends: set[int]) -> bool:
    return end <= 0 or end >= len(offsets) or end not in unsafe_ends


def _markdown_table_lines(lines: list[str]) -> set[int]:
    plain_lines = [line.removesuffix("\n") for line in lines]
    table_lines: set[int] = set()
    for index, line in enumerate(plain_lines):
        if not _MARKDOWN_TABLE_SEPARATOR.match(line) or index == 0 or "|" not in plain_lines[index - 1]:
            continue
        start = index - 1
        end = index + 1
        while end < len(plain_lines) and "|" in plain_lines[end] and plain_lines[end].strip():
            end += 1
        table_lines.update(range(start, end))
    return table_lines


def _markdown_unit_ends(text: str, token_ends: list[int]) -> list[int]:
    lines = text.splitlines(keepends=True)
    table_lines = _markdown_table_lines(lines)
    ends = []
    offsets = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    index = 0
    while index < len(lines):
        content = lines[index].removesuffix("\n")
        if index in table_lines:
            unit_end = index
        elif _LIST_ITEM_MARKER.match(content):
            unit_end = index
            next_index = index + 1
            while next_index < len(lines):
                following = lines[next_index].removesuffix("\n")
                if not following.strip() or not following.startswith((" ", "\t")):
                    break
                if _LIST_ITEM_MARKER.match(following.lstrip()):
                    break
                unit_end = next_index
                next_index += 1
        else:
            index += 1
            continue

        line = lines[unit_end]
        if line.endswith("\n"):
            newline = offsets[unit_end] + len(line) - 1
            ends.append(bisect_right(token_ends, newline))
        index = unit_end + 1
    return ends


def _safe_overlap_unit(text: str, tokenizer: Any, budget: int) -> str:
    offsets = _offsets(tokenizer, text)
    if not offsets or budget < 1:
        return ""
    token_ends = [end for _, end in offsets]
    boundaries = [
        bisect_right(token_ends, match.start())
        for match in re.finditer(r"\n[ \t]*\n", text)
    ]
    boundaries.extend(_markdown_unit_ends(text, token_ends))
    start = max((boundary for boundary in boundaries if boundary < len(offsets)), default=0)
    unit = text[offsets[start][0]:offsets[-1][1]]
    return unit if len(tokenizer.encode(unit, add_special_tokens=False)) <= budget else ""


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
    for heading, body in _sections(revision.content):
        embedding_prefix = document_embedding_prefix()
        embedding_prefix_tokens = len(tokenizer.encode(embedding_prefix, add_special_tokens=False))
        metadata = _metadata_prefix(
            revision, heading, tokenizer, min(32, max(0, limit - special_tokens - embedding_prefix_tokens) // 4)
        )
        body_budget = (
            limit
            - special_tokens
            - embedding_prefix_tokens
            - len(tokenizer.encode(metadata, add_special_tokens=False))
        )
        if body_budget < 1:
            raise ValueError("Document metadata leaves no room for body text.")
        target_limit = min(int(settings.DOCUMENT_CHUNK_TARGET_TOKENS), limit)
        prefix_tokens = len(tokenizer.encode(metadata, add_special_tokens=False)) + embedding_prefix_tokens
        target_body_budget = max(1, target_limit - special_tokens - prefix_tokens)
        overlap = min(16, target_body_budget // 5)
        offsets = _offsets(tokenizer, body)
        if not offsets:
            continue
        carry = _safe_overlap_unit(previous_body, tokenizer, overlap) if previous_body else ""
        token_ends = [end for _, end in offsets]
        unsafe_ends = _numeric_unsafe_token_ends(body, token_ends)
        paragraph_ends = [bisect_right(token_ends, match.start()) for match in re.finditer(r"\n[ \t]*\n", body)]
        line_ends = _markdown_unit_ends(body, token_ends)
        sentence_ends = [
            bisect_right(token_ends, match.start())
            for match in re.finditer(r"(?<=[.!?。！？])\s+", body)
        ]
        space_ends = [bisect_right(token_ends, match.start()) for match in re.finditer(r"[ \t]+", body)]
        start = 0
        while start < len(offsets):
            leading = carry if start == 0 else ""
            leading_tokens = len(tokenizer.encode(leading, add_special_tokens=False)) if leading else 0
            hard_end = min(start + body_budget - leading_tokens, len(offsets))
            target_end = min(start + max(1, target_body_budget - leading_tokens), hard_end)
            end = hard_end
            if target_end < len(offsets):
                structural_ends = [*paragraph_ends, *line_ends, len(offsets)]
                boundary = max(
                    (
                        candidate
                        for candidate in structural_ends
                        if start < candidate <= target_end and _safe_chunk_end(offsets, candidate, unsafe_ends)
                    ),
                    default=None,
                )
                if boundary is None:
                    boundary = min(
                        (
                            candidate
                            for candidate in structural_ends
                            if target_end < candidate <= hard_end and _safe_chunk_end(offsets, candidate, unsafe_ends)
                        ),
                        default=None,
                    )
                if boundary is None:
                    boundary = next(
                        (
                            candidate
                            for boundaries in (sentence_ends, space_ends)
                            for candidate in reversed(boundaries)
                            if start < candidate <= target_end and _safe_chunk_end(offsets, candidate, unsafe_ends)
                        ),
                        None,
                    )
                if boundary is not None:
                    end = boundary
            while end > start:
                text = body[offsets[start][0]:offsets[end - 1][1]]
                if leading:
                    text = f"{leading}\n{text}"
                embedding_text = f"{metadata}\n{text}" if metadata else text
                token_count = len(
                    tokenizer.encode(f"{embedding_prefix}{embedding_text}", add_special_tokens=True)
                )
                if token_count <= limit and _safe_chunk_end(offsets, end, unsafe_ends):
                    break
                end -= 1
            if end == start:
                raise ValueError("A document chunk exceeds the embedding model token limit.")
            chunks.append(PreviewChunk(len(chunks) + 1, heading, text, embedding_text, token_count))
            if end == len(offsets):
                break
            line_index = bisect_left(line_ends, end)
            line_start = line_ends[line_index - 1] if line_index else 0
            start = line_start if 0 < end - line_start <= overlap and line_start > start else end
        previous_body = body
    if not chunks:
        raise ValueError("Document content has no indexable text.")
    return chunks
