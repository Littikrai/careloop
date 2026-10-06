# 10: ตรวจรับฐานความรู้จากเอกสารและอัปเดตคู่มือ

**What to build:** ผู้ติดตั้งใหม่ทำตามคู่มือเพื่อเพิ่ม นำเข้า เผยแพร่ และดูแล Documents แล้วทดสอบคำตอบพร้อมแหล่งอ้างอิงได้ รวมถึงเข้าใจข้อจำกัดของ local CPU/Qdrant

**Blocked by:** 03: นำเข้า Document drafts จาก JSON; 04: เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง; 05: แทนที่ Archive และลบ Document อย่างปลอดภัย; 06: รักษาแชตให้ใช้งานได้ระหว่าง indexing; 07: รักษาโครงสร้าง Markdown; 08: ใช้ embedding model ที่เลือกและ rebuild ดัชนีระหว่าง maintenance; 09: ตรวจผลค้นหาและคำตอบจาก Markdown ภาษาไทย.

**Status:** completed

- [x] คู่มืออธิบายการเพิ่มข้อความ/TXT/Markdown, schema JSON, preview/publish, Test retrieval, replacement, archive และ retry พร้อมตัวอย่างข้อมูลที่ไม่มี secrets
- [x] ตัวอย่าง environment configuration และตาราง config ครบสำหรับ chunk tokens, max chunks, embedding batch, indexing budget, Gunicorn threads และ OpenRouter structured-output model guidance
- [x] ตรวจเส้นทาง Docker Compose: สร้างธุรกิจ → import JSON → preview → publish → ถามผ่าน widget/API; lifecycle tests ครอบคลุม replace/archive/retry และการคงข้อมูลหลัง restart
- [x] ตรวจ Q&A exact authority, semantic evidence, conflicting product clarification, insufficient knowledge, source attribution, token limits และการแยกข้อมูลธุรกิจตลอดทุกช่องทาง
- [x] Django checks, migration check, mypy, application tests ทั้ง 131 รายการ, container build/health check และ smoke test ผ่าน พร้อมบันทึกผลตามจริง
- [x] เอกสารระบุว่า Qdrant local รองรับหนึ่ง web process, indexing อาจเพิ่ม latency บน CPU และการขยายเป็นหลาย workers/งานพร้อมกันต้องใช้ Qdrant server กับ durable queue

## Verification

ทดสอบด้วย Docker Compose ใน isolated project: สร้างธุรกิจทดสอบ, import ตัวอย่าง JSON, preview/publish เอกสาร 7 chunks, ทดสอบ retrieval และส่งคำถามทั้ง 10 ข้อผ่าน iframe widget; Chat API smoke check ผ่าน ส่วน replace/archive/retry, การแยก business และการคงข้อมูลผ่าน restart ครอบคลุมโดย integration tests ใน suite ทั้ง 131 รายการ

ตรวจ environment ที่ติดตั้งใช้อยู่ด้วย `docker compose up --build -d`: container กลับมา healthy บน `localhost:8080` และ URL แชตเดิมของ `fish_shop` ยังตอบ HTTP 200 หลัง recreate โดยเก็บ volume เดิมไว้ Django check และ migration check ผ่าน, mypy ผ่าน 46 source files, และ `python manage.py test --settings=config.test_settings` ผ่าน 131 tests

รายงาน retrieval/answer จริง 10 ข้อ, citations, latency, model และ prompt SHA-256 อยู่ใน [test report](../../../test-results/aquaflow-p200-qwen3.8-flash.json); ไม่มี API key หรือ embed token ในไฟล์
