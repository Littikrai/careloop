# กำหนดวงจรชีวิตเอกสารและส่วนข้อความ

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 01

## Question

เอกสารต้นฉบับ ส่วนข้อความที่ระบบแยก และ vector ของแต่ละธุรกิจควรมีสถานะ Draft/Published/Archived และการแทนที่เวอร์ชันอย่างไร เพื่อให้สเปกเก่าไม่ถูกนำมาตอบหลังเผยแพร่ฉบับใหม่?

## Comments

Resolution: เอกสารหนึ่งรายการเป็นข้อมูลต้นทางเชิงตรรกะที่มี revision ภายในเพิ่มขึ้นตามลำดับ โดยแต่ละ revision มีสถานะ Draft, Published หรือ Archived และเอกสารหนึ่งรายการมี Published ได้สูงสุดหนึ่ง revision กับ Draft สำหรับแก้ไขได้สูงสุดหนึ่ง revision ในเวลาเดียวกัน ค่า `version` ที่แอดมินกรอกเป็น metadata สำหรับอธิบายสินค้า ไม่ใช้ตัดสินลำดับ revision

- เอกสารใหม่เริ่มเป็น Draft แอดมินแก้เนื้อหาและ metadata ได้ และยังไม่ถูกใช้ตอบลูกค้า
- การแก้ Published จะสร้าง Draft revision ใหม่จากข้อมูลเดิม ไม่แก้ฉบับที่ลูกค้ากำลังใช้งานโดยตรง
- ตอน publish ระบบตรวจข้อมูล แบ่งข้อความ และสร้าง vector ของทุกส่วนภายใต้ revision ใหม่ก่อน ระหว่างนี้ Published เดิมยังใช้งานตามปกติ
- เมื่อทุกส่วนสร้าง vector สำเร็จ ระบบจึงสลับ revision ใหม่เป็น Published และเปลี่ยน Published เดิมเป็น Archived ใน transaction เดียว หากขั้นตอนใดล้มเหลว Draft จะอยู่ในสถานะ index failed พร้อมข้อความผิดพลาด และ Published เดิมไม่เปลี่ยน
- การ archive โดยแอดมินทำให้ revision หยุดถูกค้นหาทันที หากไม่มีฉบับแทน เอกสารนั้นจะไม่มีข้อมูลให้แชตใช้ การนำกลับมาใช้ต้องสร้าง Draft revision ใหม่แล้ว publish

ส่วนข้อความเป็นข้อมูลที่ระบบสร้างจาก revision และแก้โดยตรงไม่ได้ แต่ละส่วนมีลำดับและข้อความของตนเอง พร้อม vector ID ที่ไม่ซ้ำข้าม revision สถานะการทำดัชนีใช้ Pending, Ready หรือ Failed แยกจากสถานะ revision การค้นหาใช้เฉพาะส่วนที่ Ready และมี parent revision เป็น Published ของธุรกิจเดียวกันเท่านั้น

หลังสลับหรือ archive ระบบลบ vector เก่าแบบ best effort หาก Qdrant ลบไม่สำเร็จ vector อาจค้างอยู่ได้ แต่ต้องไม่ถูกค้นคืน เพราะ query จำกัดรายการ active vector IDs จากฐานข้อมูลเสมอ การลบถาวรใช้ได้กับ Draft หรือ Archived และใช้หลักการกรอง vector ค้างแบบเดียวกัน
