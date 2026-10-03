# กำหนดวิธีทำดัชนีโดยไม่หยุดบริการแชต

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: open
Assignee: unassigned
Blocked by: 06

## Question

Docker ปัจจุบันมี Gunicorn หนึ่ง worker ขณะที่การ publish แบบ synchronous ต้องแบ่งข้อความและสร้าง embeddings บน CPU ระบบควรใช้ threads, job ภายใน process หรือ worker/queue แยกอย่างไรเพื่อให้แชตยังตอบได้ระหว่าง indexing พร้อมรองรับ retry และ restart โดยไม่ทำให้ SQLite กับ Qdrant local ถูกเปิดจากหลาย process อย่างไม่ปลอดภัย?
