# 09: ตรวจผลค้นหาและคำตอบจาก Markdown ภาษาไทย

**What to build:** ผู้ดูแลตรวจได้ว่าคำถามภาษาไทยค้นพบหลักฐานจากเอกสาร Markdown ถูกต้อง และลูกค้าได้รับคำตอบที่อ้างอิงข้อมูลได้หลังเปลี่ยน chunker และ embedding model

**Blocked by:** 08: ใช้ embedding model ที่เลือกและ rebuild ดัชนีระหว่าง maintenance.

**Status:** completed

- [x] ชุดคำถาม 10 ข้อครอบคลุมคำถามภาพรวม สเปกตรงตัว คำถามต่างถ้อยคำ คำถามหลายส่วน ข้อจำกัดสินค้า และข้อมูลที่ไม่มีในเอกสาร
- [x] Retrieval ผ่านทั้ง 10 ข้อ; chunk ที่มี `น้ำหนักตัวเครื่อง: 620 กรัม` อยู่ครบใน preview และผลค้นหา
- [x] ทดสอบผ่าน iframe widget ด้วย `qwen/qwen3.8-flash` และ prompt ที่บันทึก hash ไว้: 9 ข้อมีคำตอบพร้อมแหล่งอ้างอิง และข้อเดซิเบลถูกปฏิเสธ; ทุกคำตอบเป็นภาษาไทยและไม่มี source ID ภายใน
- [x] คู่มืออธิบายเพิ่ม/import Markdown, preview, Test retrieval และ maintenance rebuild

## Verification

ทดสอบใน isolated Docker Compose project โดยส่ง HTTP ผ่าน embedded iframe endpoint และหน้า admin Test retrieval ของ Gunicorn process เดียว ผลครบ 10/10 retrieval, 10/10 answer/refusal expectations; Chat API smoke ผ่าน 1 ข้อ รายละเอียดคำถาม คำตอบ แหล่งที่ค้นพบ latency และ system prompt hash อยู่ใน [ผลทดสอบ](../../../test-results/aquaflow-p200-qwen3.8-flash.json) โดยไม่บันทึก embed token หรือ API key
