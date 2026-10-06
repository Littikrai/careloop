# 06: รักษาแชตให้ใช้งานได้ระหว่าง indexing

**What to build:** ระหว่างแอดมินเผยแพร่ Document บน CPU แชตยังรับคำถามได้ และงานที่ล้มเหลวหรือถูกตัดด้วย container restart สามารถลองใหม่โดยไม่ทำให้ Published revision เสียหาย

**Blocked by:** 04: เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง; 05: แทนที่ Archive และลบ Document อย่างปลอดภัย.

**Status:** resolved

- [x] Docker ใช้ Gunicorn `gthread` หนึ่ง worker และอย่างน้อยสาม threads โดยจำนวน threads ตั้งค่าจาก environment ได้ แต่ไม่เปิดหลาย workers ขณะใช้ Qdrant local
- [x] Qdrant local client เปิดใช้ข้าม thread ภายใต้ `RLock` เดียวสำหรับการสร้าง client/search/create/upsert/delete และ SentenceTransformer มี lock แยก; document embeddings ทำเป็น batch ค่าเริ่มต้น 16 แล้วคืน lock ทุก batch
- [x] Publish ได้ครั้งละหนึ่งเอกสารต่อ installation; งานซ้อนถูกปฏิเสธทันทีพร้อมข้อความลองใหม่ และ SQLite transaction ไม่ครอบ tokenize, embedding หรือ Qdrant I/O
- [x] Preview/publish ปฏิเสธเอกสารเกิน `DOCUMENT_MAX_CHUNKS` ค่าเริ่มต้น 256 และหยุดอย่างปลอดภัยเมื่อเกิน indexing time budget ค่าเริ่มต้น 240 วินาทีภายใต้ timeout 300 วินาที
- [x] ทุก publish มี attempt ID, timestamps และ lease; บันทึก progress ต่อ batch แต่ candidate vectors ยังไม่ถูกค้นจนสลับสำเร็จ
- [x] Exception เปลี่ยน attempt เป็น Failed และ cleanup แบบ best effort; attempt ที่หมด lease หรือค้างจาก process ก่อนหน้าแสดง Interrupted และ Retry สร้าง attempt ใหม่โดย Published เดิมยังตอบได้
- [x] ทดสอบ chat ระหว่าง indexing, publish ซ้อน, thread-safe model/Qdrant access, timeout, exception, stale lease/restart และ retry โดยไม่มี candidate revision หลุดสู่ retrieval

## Verification

ผ่าน Django system check, migration check, mypy และชุดทดสอบเต็ม 112 รายการ

## Comments

- 2026-10-06: Implemented single-worker threaded serving, batched and synchronized local indexing, per-attempt progress/recovery, and concurrent chat coverage that confirms uncommitted candidate vectors stay hidden.
