# 06: รักษาแชตให้ใช้งานได้ระหว่าง indexing

**What to build:** ระหว่างแอดมินเผยแพร่ Document บน CPU แชตยังรับคำถามได้ และงานที่ล้มเหลวหรือถูกตัดด้วย container restart สามารถลองใหม่โดยไม่ทำให้ Published revision เสียหาย

**Blocked by:** 04: เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง; 05: แทนที่ Archive และลบ Document อย่างปลอดภัย.

**Status:** ready-for-agent

- [ ] Docker ใช้ Gunicorn `gthread` หนึ่ง worker และอย่างน้อยสาม threads โดยจำนวน threads ตั้งค่าจาก environment ได้ แต่ไม่เปิดหลาย workers ขณะใช้ Qdrant local
- [ ] Qdrant local client เปิดใช้ข้าม thread ภายใต้ `RLock` เดียวสำหรับการสร้าง client/search/create/upsert/delete และ SentenceTransformer มี lock แยก; document embeddings ทำเป็น batch ค่าเริ่มต้น 16 แล้วคืน lock ทุก batch
- [ ] Publish ได้ครั้งละหนึ่งเอกสารต่อ installation; งานซ้อนถูกปฏิเสธทันทีพร้อมข้อความลองใหม่ และ SQLite transaction ไม่ครอบ tokenize, embedding หรือ Qdrant I/O
- [ ] Preview/publish ปฏิเสธเอกสารเกิน `DOCUMENT_MAX_CHUNKS` ค่าเริ่มต้น 256 และหยุดอย่างปลอดภัยเมื่อเกิน indexing time budget ค่าเริ่มต้น 240 วินาทีภายใต้ timeout 300 วินาที
- [ ] ทุก publish มี attempt ID, timestamps และ lease; บันทึก progress ต่อ batch แต่ candidate vectors ยังไม่ถูกค้นจนสลับสำเร็จ
- [ ] Exception เปลี่ยน attempt เป็น Failed และ cleanup แบบ best effort; lease ที่หมดหลัง restart แสดง Interrupted และ Retry สร้าง attempt ใหม่ทั้งฉบับโดย Published เดิมยังตอบได้
- [ ] ทดสอบ chat ระหว่าง indexing, publish ซ้อน, thread-safe model/Qdrant access, timeout, exception, stale lease/restart และ retry โดยไม่มี candidate revision หลุดสู่ retrieval

