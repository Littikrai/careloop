# 08: ใช้ embedding model ที่เลือกและ rebuild ดัชนีระหว่าง maintenance

**What to build:** ผู้ติดตั้งเลือกใช้ embedding model ที่ผ่านการทดลองได้ โดยทั้งคำถามและเอกสารสร้างเวกเตอร์ใน space เดียวกัน และสร้างดัชนีความรู้เดิมใหม่ได้ใน maintenance window ที่ยอมรับช่วงหยุดแชตได้

**Blocked by:** 07: รักษาโครงสร้าง Markdown ใน preview และการค้นคืน; [ทดลอง embedding model สำหรับ Markdown ภาษาไทยที่รองรับข้อความยาว](../../customer-service-documents/issues/10-benchmark-long-context-embedding.md).

**Status:** complete

- [x] ค่าเริ่มต้นเป็น `intfloat/multilingual-e5-small` โดยผู้ติดตั้งเปลี่ยนผ่าน `EMBEDDING_MODEL`
- [x] การฝังคำถามใช้ `query: ` และเอกสาร/Q&A ใช้ `passage: `; โมเดลอื่นที่ไม่ใช่ multilingual E5 ไม่ได้รับ prefix นี้
- [x] การเปลี่ยน model หรือ chunker ใช้ full rebuild แบบ offline จาก Published Q&A และ Documents; web เริ่มทำงานหลัง rebuild สำเร็จและ index signature ตรง config
- [x] ก่อน rebuild สำรอง SQLite และ local Qdrant; failure คง source records เดิมไว้และ retry จาก source ซ้ำได้ โดยยังเก็บ backup เดิมไว้ rollback พร้อมคำสั่ง restore ที่ชัดเจน
- [x] ยอมรับ downtime และไม่สร้าง generation swap แบบ zero-downtime; คู่มืออธิบาย CPU, config, backup, rebuild และ rollback
