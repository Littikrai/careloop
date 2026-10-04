# กำหนดบทบาท Q&A เดิมร่วมกับเอกสาร

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 02, 03

## Question

Q&A เดิมควรมีลำดับความสำคัญเหนือเอกสารในกรณีใด, จะนำเข้า Q&A ต่อได้อย่างไร, และต้องย้ายหรือเปลี่ยนข้อมูล Q&A เดิมเพื่อรองรับฐานความรู้เอกสารหรือไม่?

## Comments

Resolution: Q&A ยังคงเป็นความรู้ที่แอดมินเขียนเพื่อควบคุมคำตอบโดยตรง ส่วนเอกสารเป็นข้อมูลรายละเอียดที่ระบบแบ่งและค้นหา ทั้งสองชนิดเป็นแหล่งความรู้ระดับเดียวกันในฐานข้อมูลของธุรกิจ แต่ Q&A ทำหน้าที่เป็น curated override เฉพาะ exact normalized match ตาม [กำหนดอำนาจ Q&A โดยไม่ใช้ similarity เป็นความมั่นใจ](09-define-safe-qa-authority.md)

### ลำดับความสำคัญ

- ระบบ normalize คำถามด้วย Unicode NFC, trim, case folding และยุบช่องว่างก่อนเปรียบเทียบ หากตรงกับคำถามใน Published Q&A ให้ Q&A นั้นมีลำดับสูงสุด
- semantic match ของ Q&A เป็น context ประกอบร่วมกับเอกสารและไม่มีสิทธิ์ทับข้อมูลเอกสารอัตโนมัติ ไม่ว่า score จะสูงเท่าใด; `RAG_QA_OVERRIDE_THRESHOLD` จึงไม่มีในรุ่นแรก
- เมื่อมี authoritative Q&A ให้ส่งเข้า LLM ก่อนพร้อมป้าย `authoritative` และสั่งให้ยึดคำตอบนั้นหากเอกสารขัดกัน เอกสารที่สอดคล้องยังใช้เพิ่มรายละเอียดได้ แต่ห้ามเปลี่ยนนโยบายหรือข้อสรุปของ Q&A
- ป้องกัน Published Q&A ที่มี normalized question ซ้ำภายในธุรกิจเดียวกัน หาก semantic context ขัดกันหรือคำถามขาดชื่อสินค้า/รุ่น ให้ถาม clarification หรือคืน insufficient knowledge แทนการเลือกเอง

### ความเข้ากันได้ของข้อมูลเดิม

- ไม่ย้ายหรือแปลง Q&A เดิมเป็นเอกสาร และไม่เปลี่ยนตาราง สถานะ Draft/Published, replacement draft หรือ vector ID เดิมเพื่อเปิดใช้ document ingestion
- Published Q&A ที่มี index status Ready ใช้งานต่อได้ทันทีโดยไม่ reindex ตราบใดที่ embedding model ไม่เปลี่ยน การเปลี่ยน embedding model เป็นงาน reindex ทั้งฐานความรู้แยกต่างหาก
- retrieval layer แปลง Q&A และ document chunk เป็น source contract กลางเฉพาะตอนค้นหา โดย source ระบุชนิด `qa` หรือ `document`; ไม่สร้าง inheritance หรือ polymorphic model เพิ่มในฐานข้อมูล

### การดูแลและนำเข้า

- เมนู Q&A, การกรอกเอง และ JSON schema `question`/`answer` เดิมยังทำงานเหมือนเดิมและสร้าง Draft เท่านั้น ส่วน JSON เอกสารใช้เมนูและ schema แยกเพื่อหลีกเลี่ยงไฟล์ที่ตีความได้สองแบบ
- การแทนที่และเผยแพร่ Q&A ใช้ workflow เดิม แอดมินใช้ Q&A เมื่อจำเป็นต้องกำหนดคำตอบ นโยบาย หรือถ้อยคำเฉพาะ และใช้ Documents สำหรับรายละเอียดจำนวนมาก เช่นคู่มือและสเปกสินค้า
- ในแชต แหล่ง Q&A แสดงเป็น “Verified answer” โดยไม่เปิดเผยคำถามภายใน ใน API แหล่งนี้คืน `type: "qa"` และ label เท่านั้น ส่วนหน้า Admin แสดงคำถาม คำตอบ เหตุผล `exact`/`semantic` และ score สำหรับ semantic match เพื่อช่วยตรวจการจับคู่
