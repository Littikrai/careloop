# 08: ตรวจรับฐานความรู้จากเอกสารและอัปเดตคู่มือ

**What to build:** ผู้ติดตั้งใหม่ทำตามคู่มือเพื่อเพิ่ม นำเข้า เผยแพร่ และดูแล Documents แล้วทดสอบคำตอบพร้อมแหล่งอ้างอิงได้ รวมถึงเข้าใจข้อจำกัดของ local CPU/Qdrant และวิธี reindex

**Blocked by:** 03: นำเข้า Document drafts จาก JSON; 04: เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง; 05: แทนที่ Archive และลบ Document อย่างปลอดภัย; 06: รักษาแชตให้ใช้งานได้ระหว่าง indexing; 07: สร้างดัชนีใหม่เมื่อ embedding model หรือ chunker เปลี่ยน.

**Status:** ready-for-agent

- [ ] คู่มืออธิบายการเพิ่มข้อความ/TXT/Markdown, schema JSON, preview/publish, Test retrieval, replacement, archive, retry และ maintenance reindex พร้อมตัวอย่างข้อมูลที่ไม่มี secrets
- [ ] ตัวอย่าง environment configuration และตาราง config ครบสำหรับ chunk tokens, max chunks, embedding batch, indexing budget, Gunicorn threads และ OpenRouter structured-output model guidance
- [ ] ตรวจเส้นทางสะอาดผ่าน Docker Compose: สร้างธุรกิจ → เพิ่ม/import Documents → preview → publish → ถามผ่าน chat/widget/API → replace/archive → retry/restart → reindex
- [ ] ตรวจ Q&A exact authority, semantic evidence, conflicting product clarification, insufficient knowledge, source attribution, token limits และการแยกข้อมูลธุรกิจตลอดทุกช่องทาง
- [ ] รัน Django checks, migration check, type checking, application tests, container build/health check และ smoke test จริงตาม credentials ที่มี พร้อมบันทึกสิ่งที่ทดสอบและสิ่งที่ยังไม่ยืนยันตามจริง
- [ ] เอกสารระบุว่า Qdrant local รองรับหนึ่ง web process, indexing อาจเพิ่ม latency บน CPU และการขยายเป็นหลาย workers/งานพร้อมกันต้องใช้ Qdrant server กับ durable queue
