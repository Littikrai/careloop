# กำหนดขนาดส่วนข้อความตามข้อจำกัด embedding model

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: none

## Question

เมื่อ embedding model ปัจจุบันอ่านได้สูงสุด 128 tokens แต่สเปกเดิมกำหนดส่วนข้อความยาวถึง 1,200 ตัวอักษร ระบบควรแบ่งเนื้อหาและ metadata ด้วย tokenizer ของโมเดลอย่างไร, ควรสงวน token สำหรับ title/product/version/heading เท่าใด, overlap เท่าใด และต้อง reindex อย่างไรเมื่อเปลี่ยน embedding model เพื่อไม่ให้ท้ายข้อความถูกตัดทิ้งโดยไม่รู้ตัว?

## Comments

Resolution: เปลี่ยนจากการแบ่งตามจำนวนตัวอักษรเป็น token-aware chunking ด้วย tokenizer ของ `EMBEDDING_MODEL` ที่โหลดอยู่ ข้อความทุกส่วนต้องผ่านการตรวจจำนวน token ก่อน encode และห้ามพึ่ง truncation ภายใน sentence-transformers

### หลักฐานจาก runtime ปัจจุบัน

ตรวจ `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` ใน Docker ได้ `max_seq_length=128` และ special tokens 2 ตัว ตัวอย่างยาว 1,200 ตัวอักษรใช้ 311 tokens สำหรับภาษาไทยและ 356 tokens สำหรับภาษาอังกฤษ ส่วน metadata ตัวอย่าง title/product/version/heading ใช้ 24 tokens ดังนั้นข้อกำหนดเดิม 1,200 ตัวอักษรมีข้อมูลช่วงท้ายถูกตัดแน่นอน

### กติกาการแบ่งส่วนข้อความ

- เพิ่ม config `DOCUMENT_CHUNK_MAX_TOKENS` ค่าเริ่มต้น 256 และคำนวณ effective limit เป็นค่าต่ำสุดระหว่าง config กับ `model.max_seq_length`; โมเดลปัจจุบันจึงใช้ 128 tokens
- นับ special tokens จาก tokenizer จริง แล้วหักออกจาก effective limit ก่อนจัด budget
- สร้าง metadata prefix แบบกระชับจาก product, version, title และ heading ตามลำดับ ใช้ token ได้สูงสุด `min(32, floor(effective_limit / 4))` เก็บค่าฉบับเต็มในฐานข้อมูลและ context สำหรับ LLM แต่ตัดเฉพาะ prefix ที่ใช้สร้าง embedding หากยาวเกิน budget
- body ใช้ token ที่เหลือทั้งหมด โมเดลปัจจุบันที่ metadata ใช้เต็ม 32 tokens จะเหลือ body 94 tokens หลังหัก special tokens
- แบ่งตาม heading และย่อหน้าก่อน จากนั้น pack หน่วยที่ต่อเนื่องกันจนถึง body budget หน่วยที่ยาวเกินใช้ tokenizer offset ตัดเป็น token windows
- overlap ใช้ `min(16, body_budget / 5)` tokens จากท้าย body ก่อนหน้า โดยไม่คัดลอก metadata prefix ซ้ำเข้า body และไม่ข้ามขอบเขตเอกสาร
- ก่อนเรียก encode ต้องยืนยันว่า metadata prefix รวม body และ special tokens ไม่เกิน effective limit หากเกินให้การ publish ล้มเหลวพร้อมข้อผิดพลาด แทนการตัดข้อความเงียบ ๆ

### การเปลี่ยน embedding model

เก็บ index signature ที่ประกอบด้วย model ID, embedding dimension, max sequence length และ chunker version การเพิ่ม document ingestion ครั้งแรกให้รับรอง vectors ของ Q&A เดิมด้วย signature ของโมเดลปัจจุบัน จึงไม่บังคับ reindex หากผู้ติดตั้งยังใช้โมเดลเดิม

การเปลี่ยน model หรือ chunker version เป็น maintenance operation ที่ reindex Q&A และเอกสารทั้งหมด ไม่เปลี่ยนกลางการทำงานของ web process คำสั่ง reindex สร้าง Qdrant generation ใหม่แยกจากชุด active และสลับ generation ของแต่ละธุรกิจเมื่อสร้างครบเท่านั้น หากล้มเหลวให้เก็บ generation เดิมไว้เพื่อย้อนกลับ หลังสำเร็จจึงลบ vectors รุ่นเก่าแบบ best effort ผู้ติดตั้งต้องหยุด web, เปลี่ยน config, รันคำสั่ง reindex และเปิด web ใหม่ตามขั้นตอนใน README
