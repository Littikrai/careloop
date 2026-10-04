# 07: สร้างดัชนีใหม่เมื่อ embedding model หรือ chunker เปลี่ยน

**What to build:** ผู้ติดตั้งเปลี่ยน embedding model หรือ chunker configuration แล้วสร้างดัชนี Q&A และ Documents ใหม่ได้ด้วย maintenance workflow โดยแชตไม่ใช้ vectors ที่สร้างด้วยสัญญาคนละรุ่น

**Blocked by:** 05: แทนที่ Archive และลบ Document อย่างปลอดภัย; 06: รักษาแชตให้ใช้งานได้ระหว่าง indexing.

**Status:** ready-for-agent

- [ ] เก็บ index signature จาก model ID, embedding dimension, max sequence length และ chunker version และตรวจไม่ให้ runtime ใช้โมเดลกับ active generation ที่ signature ไม่ตรงกัน
- [ ] มี maintenance command ที่ผู้ติดตั้งรันขณะหยุด web เพื่อ reindex Published Q&A และ Document revisions จากข้อมูลต้นฉบับไปยัง Qdrant generation ใหม่
- [ ] สลับ active generation แยกตามธุรกิจเมื่อทุก vector ของธุรกิจนั้นพร้อมเท่านั้น และลบ generation เก่าแบบ best effort หลังสำเร็จ
- [ ] Failure หรือ interruption ไม่เปลี่ยน active generation ไม่ทำลายต้นฉบับ และสั่ง retry ได้โดยไม่ผสม vectors ต่าง model/chunker
- [ ] การตั้งค่าโมเดลเดิมของ installation ปัจจุบันได้รับ signature โดยไม่บังคับ reindex ที่ไม่จำเป็น ส่วนการเปลี่ยนค่ามีข้อความและขั้นตอน restart/reindex ที่ชัดเจน
- [ ] ทดสอบ model/chunker signature เหมือนและต่าง, dimension เท่ากันแต่ model ID ต่าง, partial failure, retry, generation swap และ retrieval ของหลายธุรกิจหลัง reindex

