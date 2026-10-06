"""Throwaway prototype: compare local Thai Markdown retrieval embeddings."""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DATA_DIR", "/private/tmp/customer-service-embedding-prototype")
os.environ.setdefault("DJANGO_SECRET_KEY", "prototype-only-secret-" + "x" * 40)

for line in (ROOT / ".env").read_text().splitlines():
    name, separator, value = line.partition("=")
    if separator and name and not name.startswith("#"):
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))

import django

django.setup()

from django.conf import settings
from django.test.utils import override_settings
from sentence_transformers import SentenceTransformer

from businesses.document_chunks import preview_chunks
from businesses.openrouter import OpenRouterError, complete_answer

SAMPLE = ROOT / "examples/aquaflow-p200-spec.example.md"
E5_PATH = Path("/private/tmp/customer-service-e5-small")
CASES = [
    ("AquaFlow P200 เป็นยังไง", "AquaFlow P200 เป็นปั๊มน้ำหมุนเวียน"),
    ("ตัวเครื่องหนักเท่าไหร่", "น้ำหนักตัวเครื่อง: 620 กรัม"),
    ("ใช้กับตู้ปลาขนาดไหนได้บ้าง", "80–200 ลิตร"),
    ("ใช้กับน้ำเค็มได้ไหม", "ห้ามใช้กับน้ำเค็ม"),
    ("ปรับความแรงได้กี่ระดับ", "ปรับระดับการไหลได้ 3 ระดับ"),
    ("แรงดันไฟที่รองรับคือเท่าไหร่", "220–240 โวลต์ AC"),
    ("รับประกันกี่เดือน", "รับประกันตัวเครื่อง 12 เดือน"),
    ("ถ้าน้ำไหลเบาลงควรทำอย่างไร", "ตรวจฟองน้ำ ใบพัด และท่อก่อน"),
    ("ร้านเปิดกี่โมง", None),
]
ANSWER_CASES = [CASES[0], CASES[1], CASES[-1]]


def load(name):
    started = time.perf_counter()
    model = SentenceTransformer(name, device="cpu")
    return model, time.perf_counter() - started


def chunks_for(model, revision, limit):
    with override_settings(DOCUMENT_CHUNK_MAX_TOKENS=limit):
        return preview_chunks(revision, tokenizer=model.tokenizer, max_seq_length=model.max_seq_length)


def evaluate(label, model, chunks, cases, e5):
    prefix = "passage: " if e5 else ""
    passages = [prefix + chunk.embedding_text for chunk in chunks]
    queries = [("query: " if e5 else "") + question for question, _ in cases]
    model.encode(["warmup"], normalize_embeddings=True, show_progress_bar=False)
    started = time.perf_counter()
    doc_vectors = model.encode(passages, normalize_embeddings=True, show_progress_bar=False)
    doc_seconds = time.perf_counter() - started
    started = time.perf_counter()
    query_vectors = model.encode(queries, normalize_embeddings=True, show_progress_bar=False)
    query_seconds = time.perf_counter() - started

    rows = []
    answerable_ranks = []
    for (question, expected), query_vector in zip(cases, query_vectors, strict=True):
        ranked = sorted(
            ((float(query_vector @ doc_vector), chunk) for chunk, doc_vector in zip(chunks, doc_vectors, strict=True)),
            key=lambda item: item[0], reverse=True,
        )
        rank = next((index for index, (_, chunk) in enumerate(ranked, 1) if expected and expected in chunk.text), None)
        if rank:
            answerable_ranks.append(rank)
        rows.append({"question": question, "expected": expected, "ranked": ranked, "gold_rank": rank})

    rr = [1 / rank if rank and rank <= 6 else 0 for rank in (row["gold_rank"] for row in rows if row["expected"])]
    report = [f"### {label}", f"Chunks: {len(chunks)}; encode docs: {doc_seconds:.2f}s; encode queries: {query_seconds:.2f}s"]
    report.append(f"Relevant Hit@3: {sum(rank <= 3 for rank in answerable_ranks)}/{len(answerable_ranks)}; MRR@6: {sum(rr) / max(1, len(rr)):.3f}")
    for row in rows:
        top_score, top_chunk = row["ranked"][0]
        report.append(f"- {row['question']} — expected rank {row['gold_rank'] or 'not answerable'}; top {top_score:.3f}: {top_chunk.text[:110].replace(chr(10), ' ')}")
    return report, rows


def answer_samples(label, rows):
    if not settings.OPENROUTER_API_KEY:
        return [f"### {label} answers", "Skipped: OPENROUTER_API_KEY is not configured."]
    report = [f"### {label} answers (OpenRouter model: {settings.OPENROUTER_MODEL})"]
    for row in rows:
        question = row["question"]
        sources = [
            {"id": f"src-{i}", "type": "document", "title": "AquaFlow P200 test spec",
             "heading": chunk.heading, "product": "AquaFlow P200", "version": "2026.1",
             "text": chunk.text, "authoritative": False}
            for i, (_, chunk) in enumerate(row["ranked"][:6], 1)
        ]
        try:
            result = complete_answer(question, sources)
            report.append(f"- {question} → {result.status}: {result.answer} [sources: {', '.join(result.source_ids)}]")
        except OpenRouterError:
            report.append(f"- {question} → request failed; see application logs, no credentials written to report")
    return report


def main():
    if not SAMPLE.exists() or not E5_PATH.exists():
        raise SystemExit("Missing AquaFlow sample or temporary E5 model download.")
    revision = SimpleNamespace(
        title="AquaFlow P200 test spec", product="AquaFlow P200", version="2026.1",
        content=SAMPLE.read_text(encoding="utf-8"),
    )
    old, old_load = load("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    e5, e5_load = load(str(E5_PATH))
    baseline_chunks = chunks_for(old, revision, 128)
    long_chunks = chunks_for(e5, revision, 256)
    runs = [
        ("MiniLM / 128 tokens", old, baseline_chunks, False),
        ("E5 small / same chunks as MiniLM", e5, baseline_chunks, True),
        ("E5 small / 256-token budget", e5, long_chunks, True),
    ]
    report = ["# PROTOTYPE RESULTS", "", "Retrieval-only comparison uses the same Thai questions and source. E5 uses `query:` / `passage:` prefixes. No production database or Qdrant index is read or changed.", "", f"Model load time: MiniLM {old_load:.2f}s; E5 small {e5_load:.2f}s", ""]
    saved_rows = []
    for label, model, chunks, e5_prefix in runs:
        section, rows = evaluate(label, model, chunks, CASES, e5_prefix)
        report.extend(section + [""])
        if label == "E5 small / 256-token budget":
            saved_rows = rows
    picked = [row for row in saved_rows if row["question"] in {q for q, _ in ANSWER_CASES}]
    report.extend(answer_samples("E5 small / 256-token budget", picked))
    output = Path(__file__).with_name("report.md")
    output.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
