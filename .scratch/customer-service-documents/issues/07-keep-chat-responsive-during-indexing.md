# กำหนดวิธีทำดัชนีโดยไม่หยุดบริการแชต

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 06

## Question

Docker ปัจจุบันมี Gunicorn หนึ่ง worker ขณะที่การ publish แบบ synchronous ต้องแบ่งข้อความและสร้าง embeddings บน CPU ระบบควรใช้ threads, job ภายใน process หรือ worker/queue แยกอย่างไรเพื่อให้แชตยังตอบได้ระหว่าง indexing พร้อมรองรับ retry และ restart โดยไม่ทำให้ SQLite กับ Qdrant local ถูกเปิดจากหลาย process อย่างไม่ปลอดภัย?

## Comments

Resolution: รุ่นแรกคง web process เดียวและการ publish แบบ synchronous แต่เปลี่ยน Gunicorn เป็น `gthread` หนึ่ง worker สาม threads โดยตั้งจำนวน threads ผ่าน config ได้และตรวจว่าไม่น้อยกว่าสาม หนึ่ง thread จึงรับงาน publish ขณะที่อีกสอง thread ยังรับ chat และ health/admin requests ได้ ไม่เพิ่ม background job, process แยก หรือ queue ในรุ่นนี้

เหตุผลสำคัญคือ Qdrant local ใช้ exclusive lock ต่อ storage path และแจ้งให้ใช้ Qdrant server หากต้องการเปิดพร้อมกันหลาย instance ส่วน `force_disable_check_same_thread` ของ client กำหนดให้แอปต้องรับผิดชอบ thread safety เอง การเพิ่ม Gunicorn workers หรือ indexer process จึงขัดกับ storage ปัจจุบัน ส่วน Gunicorn รองรับ thread pool ผ่าน `gthread` โดยตรง

### ขอบเขต concurrency

- อนุญาต publish ได้ครั้งละหนึ่งเอกสารต่อ installation ด้วย process-local non-blocking lock หากมีงานอยู่ คำขอถัดไปหยุดทันทีและแจ้งว่าให้ลองใหม่ ไม่ต่อคิวในหน่วยความจำ
- สร้าง Qdrant local client ด้วย `force_disable_check_same_thread=True` และใช้ `RLock` กลางครอบทั้งการสร้าง client และทุก operation ได้แก่ search, create, upsert และ delete เพื่อไม่ให้ client เดียวถูกอ่านและเขียนพร้อมกัน ช่วง lock ต้องสั้นและห้ามครอบการแบ่งข้อความหรือ database transaction
- ใช้ lock แยกสำหรับ SentenceTransformer เพราะใช้ model instance ร่วมกัน แชต encode ทีละคำถาม ส่วน document encode เป็น batch ค่าเริ่มต้น 16 chunks และคืน lock หลังทุก batch ดังนั้นแชตอาจรอจบได้ไม่เกินหนึ่ง batch แทนการรอทั้งเอกสาร
- ระหว่างแต่ละ batch ให้ upsert vectors ของ batch นั้นแล้วคืน Qdrant lock จึงเปิดช่วงให้ chat search แทรกได้ งาน index มีสิทธิ์ใช้ CPU ร่วมกับ chat ดังนั้น latency อาจสูงขึ้นแต่ service ยังรับ request ได้
- SQLite transaction ใช้เฉพาะการ claim attempt, บันทึกสถานะ batch และสลับ Published/Archived ช่วงสั้น ๆ ห้ามถือ transaction ระหว่าง tokenize, encode หรือ Qdrant I/O

### เพดานและการหยุดอย่างปลอดภัย

- เพิ่ม `DOCUMENT_MAX_CHUNKS` ค่าเริ่มต้น 256 และแสดงจำนวนใน preview หากเกินให้ publish ล้มก่อนสร้าง embeddings พร้อมขอให้แยกเอกสาร ขีดจำกัด content 256 KiB ยังใช้ตอนรับข้อมูล แต่ไม่ได้รับประกันว่าจะ publish ได้หาก tokenizer สร้าง chunks เกินเพดาน
- ใช้ batch size ค่าเริ่มต้น 16 และ time budget ค่าเริ่มต้น 240 วินาที ภายใต้ Gunicorn timeout 300 วินาที ตรวจ budget ระหว่าง batch; เมื่อเกินให้หยุดและบันทึก Failed เพื่อเหลือเวลาทำ cleanup และตอบ admin
- ค่าทั้งสาม (`GUNICORN_THREADS`, `DOCUMENT_EMBED_BATCH_SIZE`, `DOCUMENT_INDEX_TIME_BUDGET_SECONDS`) ตั้งจาก environment ได้ แต่จำนวน Gunicorn workers ต้องคงเป็นหนึ่งตราบใดที่ใช้ Qdrant local

### Retry และ restart

- ทุก publish สร้าง `attempt_id`, `started_at` และ lease expiry บน Draft ก่อนทำงาน Vector ID ของ candidate generation ผูกกับ revision และ attempt จึงไม่ชนกับ Published เดิมหรือ retry ครั้งใหม่
- บันทึก progress หลังแต่ละ batch โดยไม่ทำให้ candidate ถูกค้นหา Chat ยังค้นเฉพาะ revision Published ตามสัญญาเดิม เมื่อครบทุก batch จึงสลับ revision ใน transaction เดียว
- ข้อผิดพลาดที่จับได้เปลี่ยน attempt เป็น Failed และลบ candidate vectors แบบ best effort ปุ่ม Retry สร้าง attempt ใหม่และทำใหม่ทั้งเอกสาร ไม่ resume จาก batch เดิม เพื่อลด state ที่ต้องพิสูจน์ความถูกต้อง
- หาก container หรือ worker หยุดกะทันหัน attempt จะค้าง Pending แต่ Published เดิมยังทำงาน เมื่อ lease หมด หน้า admin แสดง Interrupted และ Retry สามารถ claim งานใหม่แบบ atomic พร้อมลบ vectors ของ attempt เก่าแบบ best effort ไม่ต้องมี startup worker หรือ timer

แนวทางนี้ตั้งใจสำหรับ installation ขนาดเล็กที่ใช้ local storage หากต้องการหลาย web workers, หลายงาน indexing พร้อมกัน หรืองานที่เกินเพดาน ให้ย้าย Qdrant เป็น server และใช้ durable job queue ใน effort ถัดไป แทนการขยายกลไกนี้

หลักฐาน: [Qdrant local source ระบุ exclusive storage lock และให้ใช้ server เมื่อจำเป็นต้อง concurrent access](https://github.com/qdrant/qdrant-client/blob/master/qdrant_client/local/qdrant_local.py), [QdrantClient ระบุว่าผู้เรียกต้องจัดการ thread safety เมื่อปิด same-thread check](https://github.com/qdrant/qdrant-client/blob/master/qdrant_client/qdrant_client.py), และ [Gunicorn อธิบาย `gthread` กับ `--threads`](https://docs.gunicorn.org/en/stable/settings.html#threads)
