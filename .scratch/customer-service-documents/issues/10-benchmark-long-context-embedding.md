# ทดลอง embedding model สำหรับ Markdown ภาษาไทยที่รองรับข้อความยาว

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:prototype`
Type: HITL
Status: resolved
Assignee: root
Blocked by: none

## Question

เมื่อเทียบ embedding model ปัจจุบันกับตัวเลือกที่รองรับ context ยาวขึ้น เช่น `intfloat/multilingual-e5-small` บนเอกสาร Markdown ภาษาไทยและเครื่อง CPU ผลค้นหาและคำตอบดีขึ้นพอที่จะเปลี่ยนค่าเริ่มต้นหรือไม่ และขนาด chunk แบบใดให้ผลเหมาะสม?

ทำ prototype ด้วยเอกสาร AquaFlow P200 และชุดคำถามทดสอบที่ครอบคลุมคำถามสเปกตรงตัว คำถามภาพรวม การถามด้วยถ้อยคำต่างกัน และคำถามที่ไม่มีข้อมูล เปรียบเทียบ retrieval โดยดู chunk ที่ได้จริงก่อนเทียบคำตอบ ใช้ OpenRouter model และ prompt เดิมกับทุกชุด บันทึกเวลา embedding/การค้นหาและข้อกำหนด prefix ของแต่ละโมเดล

ผลลัพธ์ต้องแยกให้เห็นว่าความต่างมาจาก model หรือ token budget/chunk size พร้อมข้อเสนอว่าจะทดลองหรือเลือกค่าใดต่อ ไม่ reindex ฐานข้อมูลที่ผู้ใช้กำลังใช้งานใน prototype นี้

การนำโมเดลที่เลือกไปใช้จริงต้องต่อกับ implementation ticket [ใช้ embedding model ที่เลือกและ rebuild ดัชนีระหว่าง maintenance](../../customer-service-documents-build/issues/08-long-context-embedding-model.md) โดยใช้ offline rebuild พร้อม backup/rollback ตามขนาดข้อมูลปัจจุบัน ไม่สร้าง zero-downtime generation workflow ใน prototype นี้

## Comments

Resolution: เลือก `intfloat/multilingual-e5-small` เป็นค่าเริ่มต้นจากผล retrieval ภาษาไทย และใช้ prefix `passage: ` กับความรู้ที่ index กับ `query: ` กับคำถาม

- MiniLM ที่ 128 tokens ได้ Hit@3 7/8 และ MRR@6 0.671
- E5 บน chunks เดิมได้ Hit@3 8/8 และ MRR@6 0.917
- E5 ที่ 256-token budget ได้ 7 chunks, Hit@3 8/8 และ MRR@6 0.938
- คำถามตัวอย่างที่ไม่มีคำตอบยังค้นพบ chunk ที่ไม่เกี่ยวข้อง จึงต้องใช้ threshold และ LLM contract แยกต่างหาก
- คำขอสร้างคำตอบสามกรณีผ่าน OpenRouter ล้มเหลว จึงใช้ผลนี้ตัดสินเฉพาะ embedding/retrieval ไม่ได้อ้างว่าได้ยืนยันคุณภาพคำตอบ LLM แล้ว
