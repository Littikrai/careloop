# กำหนดขั้นตอนแอดมินสำหรับเพิ่มความรู้

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 01, 02, 03

## Question

หน้า admin ควรจัดการเพิ่ม แก้ไข ตรวจ preview เผยแพร่ และแทนที่เอกสารของสินค้าอย่างไร เพื่อให้เจ้าของร้านที่มีข้อมูลยาวเริ่มใช้งานได้โดยไม่ต้องคิดคำถามล่วงหน้า?

## Comments

Resolution: รุ่นแรกเพิ่มเมนู Documents แยกจาก Q&A ภายใน Django Admin เดิม แอดมินเลือกธุรกิจทุกครั้ง และเริ่มสร้างฐานความรู้จากเนื้อหาที่มีอยู่ได้โดยไม่ต้องสร้างคำถามก่อน

### การเพิ่มข้อมูล

- แบบฟอร์มเอกสารมี `business`, `title`, `content` เป็นข้อมูลบังคับ และ `product`, `version` เป็นข้อมูลทางเลือก บันทึกครั้งแรกเป็น Draft เสมอ
- รองรับสามทางเข้า: วางข้อความในแบบฟอร์ม, อัปโหลด `.txt`/`.md` หนึ่งไฟล์โดยใช้ชื่อไฟล์เป็น title เริ่มต้น, และนำเข้า JSON array หลายเอกสารตาม schema ที่กำหนดไว้
- JSON ตรวจทั้งไฟล์ก่อนเขียนข้อมูล แล้วสร้าง Draft ทั้งชุดใน transaction เดียว รายการซ้ำกันทุก field ให้ข้าม แต่ไม่จับคู่หรือแทนที่เอกสารเดิมจากชื่อโดยอัตโนมัติ เพราะชื่อไม่ใช่ identity ที่ปลอดภัย
- ไฟล์หนึ่งครั้งยังจำกัดรวม 5 MiB และ content ของแต่ละเอกสารจำกัด 256 KiB หลังเข้ารหัส UTF-8 หากยาวกว่านั้น Admin จะแจ้งให้แยกเป็นเอกสารตามสินค้า รุ่น หรือหัวข้อ

### การตรวจและเผยแพร่

- หน้า Draft แสดงเนื้อหาที่ normalize แล้ว metadata จำนวนตัวอักษร และ preview ของส่วนข้อความตามลำดับก่อน publish โดย preview ยังไม่สร้าง vector
- ปุ่ม Publish มีหน้ารับรองชื่อธุรกิจ ชื่อเอกสาร และจำนวนส่วนข้อความ แล้วประมวลผลทีละเอกสารแบบ synchronous พร้อม batch embeddings เพื่อคง Docker Compose เดิมที่ใช้ SQLite, Qdrant local และ web process เดียว
- การนำเข้าหลายเอกสารไม่ publish อัตโนมัติ และรุ่นแรกไม่มี bulk publish เพื่อไม่ให้คำขอเดียวผูก web process นานเกินไป
- เมื่อสำเร็จ Admin แสดงจำนวนส่วนข้อความและเวลาเผยแพร่ เมื่อไม่สำเร็จยังคงเป็น Draft/Failed พร้อมข้อความผิดพลาดที่อ่านได้และปุ่ม Retry publish โดย Published revision เดิมไม่เปลี่ยน
- หน้า Published มีช่อง Test retrieval ให้พิมพ์คำถามและดูส่วนข้อความที่ค้นได้ ชื่อ revision และ similarity score โดยไม่ต้องเรียก OpenRouter

### การแก้ไข แทนที่ และนำออก

- Draft แก้เนื้อหาและ metadata ได้โดยตรง Published และ Archived เป็น read-only
- คำสั่ง Create replacement draft คัดลอก Published เป็น revision ใหม่ภายใต้เอกสารเดิม และไม่อนุญาต draft ทดแทนซ้ำ การ publish draft นี้ใช้การสลับ revision ที่ตัดสินใจไว้แล้ว
- คำสั่ง Archive ต้องมีหน้ารับรองและหยุดการค้นหาทันที หากต้องการนำกลับมาใช้ให้สร้าง draft revision ใหม่จาก Archived แล้ว publish
- ลบถาวรได้เฉพาะ Draft หรือ Archived; Published ต้อง archive ก่อน เพื่อป้องกันการนำความรู้ออกจากแชตโดยไม่ตั้งใจ

รายการ Documents แสดง title, business, product, version, revision, status, index status และ updated time พร้อมตัวกรองตาม business/status/index status และค้นจาก title/product/content หลัง import ให้พากลับมายังรายการ Draft ที่กรองตามธุรกิจนั้น พร้อมสรุปจำนวนที่สร้าง ข้าม หรือผิดพลาด
