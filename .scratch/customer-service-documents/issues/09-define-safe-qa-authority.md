# กำหนดอำนาจ Q&A โดยไม่ใช้ similarity เป็นความมั่นใจ

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: none

## Question

เนื่องจาก cosine similarity ไม่ใช่ค่าความมั่นใจและ threshold เดียวอาจให้ผลต่างกันตามภาษา ข้อมูล และ embedding model รุ่นแรกควรให้ Q&A override เอกสารเฉพาะ exact normalized match, ใช้ flag ที่แอดมินกำหนด หรือคง semantic override ที่ต้องผ่านการปรับเทียบอย่างไร เพื่อไม่ให้ Q&A ที่คล้ายแต่คนละสินค้าไปทับสเปกที่ถูกต้อง?

## Comments

Resolution: รุ่นแรกให้ Q&A เป็น authoritative override เฉพาะเมื่อคำถามลูกค้าตรงกับคำถามของ Published Q&A หลัง normalize แบบ deterministic เท่านั้น ยกเลิก `RAG_QA_OVERRIDE_THRESHOLD` และห้ามตีความ cosine similarity เป็นความมั่นใจ ไม่เพิ่ม authoritative flag เพราะ flag บอกได้เพียงว่าแอดมินเชื่อคำตอบ แต่ไม่ได้พิสูจน์ว่าคำถามลูกค้าหมายถึงสินค้า รุ่น หรือ intent เดียวกัน

### การจับคู่ที่มีอำนาจ

- Normalize ทั้งคำถามลูกค้าและคำถาม Q&A ด้วย Unicode NFC, trim, Unicode case folding และยุบ whitespace ทุกชนิดเป็นช่องว่างเดียว ไม่ลบคำ เครื่องหมายวรรคตอน หรือตัวเลข เพราะอาจเป็นส่วนของชื่อรุ่นหรือความหมาย
- ตรวจ exact normalized match ในฐานข้อมูลก่อนสร้าง embedding หากพบหนึ่งรายการ ให้ทำเครื่องหมาย source นั้นเป็น `authoritative` โดยไม่ใช้ vector score ตัดสิน
- Published Q&A ภายในธุรกิจเดียวกันต้องมี normalized question ไม่ซ้ำกัน การ publish หรือ replacement ที่ชนกับรายการใช้งานอยู่ต้องถูกปฏิเสธพร้อมชี้รายการที่ชน จึงไม่มี authoritative Q&A มากกว่าหนึ่งรายการต่อคำถาม
- รุ่นแรกไม่เพิ่ม alias model แอดมินที่ต้องการรองรับถ้อยคำแน่นอนหลายแบบสร้าง Q&A หลายรายการที่ใช้คำตอบเดียวกันได้ แต่แต่ละคำถามยังต้องไม่ซ้ำหลัง normalize

### Semantic retrieval ที่เหลือ

- หากไม่พบ exact match ให้ค้น Q&A และ document chunks ด้วย semantic retrieval ตามปกติ Q&A ที่พบด้วย similarity เป็นหลักฐานระดับเดียวกับเอกสารและไม่มีสิทธิ์ override ไม่ว่า score สูงเท่าใด
- `RAG_SCORE_THRESHOLD` ยังคงใช้ตัดผู้สมัครที่ห่างเกินไปเพื่อจำกัด context เท่านั้น ไม่แสดงหรืออธิบายว่าเป็น probability หรือ confidence
- เมื่อ semantic Q&A กับเอกสารขัดกัน หรือผลลัพธ์กล่าวถึงหลายสินค้า/รุ่นโดยคำถามระบุไม่พอ ให้ LLM คืน `needs_clarification`; หากถามเพิ่มแล้วยังเลือกข้อเท็จจริงไม่ได้ให้คืน `insufficient_knowledge`
- หน้า Test retrieval ของแอดมินแสดงเหตุผลการจับคู่เป็น `exact` หรือ `semantic` พร้อม similarity score เฉพาะรายการ semantic และคำอธิบายว่า score ใช้จัดอันดับ ไม่ใช่ความมั่นใจ

### การประกอบคำตอบ

- เมื่อมี exact authoritative Q&A ให้ส่ง source นี้เป็นรายการแรกและระบุใน prompt ว่าข้อสรุปหรือนโยบายของมันมีอำนาจเหนือ source อื่น เอกสารที่ค้นได้ใช้เสริมรายละเอียดที่ไม่ขัดกันเท่านั้น
- หากเอกสารขัดกับ authoritative Q&A ให้ตอบตาม Q&A และอ้าง “Verified answer”; ความขัดแย้งควรปรากฏในหน้า admin test เพื่อให้แอดมินแก้ฐานความรู้ แต่ไม่เปิดรายละเอียดภายในแก่ลูกค้า
- ถ้าไม่มี exact match ห้ามส่งป้าย `authoritative` ให้ source ใด Structured output และการตรวจ source IDs ใช้สัญญาเดิม

กติกานี้ทำให้พฤติกรรมเหมือนกันข้ามภาษาและ embedding model โดยแลกกับการที่คำถามถอดความจะไม่ override อัตโนมัติ ซึ่งเหมาะกับรุ่นแรกมากกว่าการเปิดทางให้คำตอบผิดสินค้าอย่างมั่นใจ หากอนาคตต้องการ semantic authority ให้ทำเป็นงานประเมินแยกที่มีชุดคำถามจริงต่อธุรกิจและวัด false-positive ก่อนเปิดใช้
