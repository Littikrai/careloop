# 04: เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง

**What to build:** แอดมินเผยแพร่ Document draft หนึ่งฉบับแล้วลูกค้าถามข้อมูลจากเนื้อหานั้นผ่านหน้าแชต widget หรือ API ได้ โดยระบบใช้ Q&A และ document chunks ร่วมกันและแสดงเฉพาะแหล่งที่ใช้จริง

**Blocked by:** 01: ทำให้คำตอบจาก Q&A มี contract ที่ปลอดภัย; 02: เพิ่มและตรวจตัวอย่าง Document draft.

**Status:** ready-for-agent

- [ ] หน้า publish ยืนยันธุรกิจ ชื่อเอกสาร และจำนวน chunks; งานสร้าง embeddings และ vectors ครบก่อนเปลี่ยน revision เป็น Published/Ready และข้อผิดพลาดคง draft เป็น Failed โดยไม่เปิดใช้บาง chunks
- [ ] Embedding input ของแต่ละ chunk ประกอบด้วย metadata prefix และเนื้อหาตาม token budget ส่วน record เก็บลำดับ heading ข้อความ และ vector ID ที่ไม่ซ้ำกับ Q&A หรือ revision อื่น
- [ ] Retrieval ฝังคำถามครั้งเดียว ค้น Published/Ready Q&A สูงสุด 3 รายการและ document chunks สูงสุด 6 รายการของธุรกิจเดียวกัน ตัดข้อความซ้ำ แล้วส่งสูงสุด 6 sources และ 8,000 ตัวอักษรเข้า OpenRouter
- [ ] หากไม่มี source ผ่าน threshold ระบบไม่เรียก OpenRouter; ถ้าข้อมูลขาดรุ่นหรือขัดกัน ระบบคืน clarification หรือ insufficient knowledge ตาม answer contract
- [ ] หน้าแชตและ widget แสดง title, heading และ product/version ของ document sources ที่ถูกอ้างอิง ส่วน API คืน source contract เดียวกันโดยไม่เปิดชื่อไฟล์ ข้อความดิบ score หรือ ID ภายใน
- [ ] หน้าแอดมินมี Test retrieval ที่แสดง revision, chunk text และ similarity score โดยไม่เรียก OpenRouter และทดสอบคำตอบจาก document, Q&A ร่วมกับ document, citations และ business isolation

