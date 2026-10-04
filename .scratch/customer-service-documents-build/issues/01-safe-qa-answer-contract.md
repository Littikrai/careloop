# 01: ทำให้คำตอบจาก Q&A มี contract ที่ปลอดภัย

**What to build:** ลูกค้าที่ถามผ่านหน้าแชต widget หรือ API ได้คำตอบจาก Q&A เดิมผ่านผลลัพธ์ OpenRouter ที่ตรวจสอบโครงสร้างและแหล่งข้อมูลได้ โดย Q&A จะมีอำนาจเหนือแหล่งอื่นเฉพาะคำถามที่ตรงกันหลัง normalize เท่านั้น

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] OpenRouter ถูกเรียกด้วย strict JSON Schema ที่รองรับ `answer`, `needs_clarification` และ `insufficient_knowledge` พร้อม `answer` และ `source_ids`; request ปิด reasoning และกำหนดให้ provider รองรับ parameters ที่ส่งไป
- [ ] ระบบตรวจ schema, status และ source IDs หลังตอบกลับ; ID ที่ไม่ได้ส่งเป็น context หรือ payload ผิดรูปแบบเป็น `service_error` โดยไม่เดาคำตอบหรือ retry ไปยังโมเดลอื่นอัตโนมัติ
- [ ] ระบบ normalize คำถามด้วย Unicode NFC, trim, case folding และยุบ whitespace แล้วให้ Published Q&A เป็น authoritative เฉพาะ exact normalized match; semantic score ใช้ค้นและจัดอันดับเท่านั้น
- [ ] การ publish หรือ replacement ปฏิเสธ Published Q&A ที่มี normalized question ซ้ำภายในธุรกิจเดียวกัน โดยไม่กระทบ Q&A ที่ใช้งานอยู่
- [ ] หน้าแชตและ widget แสดง “Verified answer” สำหรับแหล่ง Q&A ที่ LLM อ้างอิง และ Chat API คืน `sources` โดยไม่เปิดเผยคำถามภายใน score หรือ ID ภายใน
- [ ] ทดสอบ exact/semantic/conflicting Q&A, คำถามกำกวม, insufficient knowledge, malformed OpenRouter output, reasoning ที่ไม่ควรถูกส่งกลับ และการแยกข้อมูลระหว่างธุรกิจ

