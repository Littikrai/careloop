# กำหนดกติกาแบ่ง Markdown โดยรักษาหน่วยความหมาย

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: unassigned
Blocked by: 10

## Question

หลังเห็นผลเปรียบเทียบโมเดลและขนาด token แล้ว ตัวแบ่ง Markdown ควรเก็บหัวข้อ ย่อหน้า รายการสเปก ตาราง Markdown และข้อความยาวเกินเพดานเป็นหน่วยอย่างไร เพื่อไม่ให้ข้อเท็จจริงอย่าง `น้ำหนักตัวเครื่อง: 620 กรัม` ถูกแยกจนความหมายเปลี่ยน?

กำหนด target และ hard limit ที่นับ metadata กับ special tokens ด้วย วิธี pack หน่วยต่อเนื่องกัน การทำ overlap เฉพาะขอบเขตที่ปลอดภัย fallback สำหรับย่อหน้าภาษาไทยยาว และหลักฐานใน preview/test ที่ยืนยันว่าไม่มีข้อความตกหล่นหรือเริ่ม/จบกลางค่าที่มีความหมาย การตัดสินใจนี้จะทบทวนหรือแทนที่ส่วนที่เกี่ยวกับ chunking ใน [กำหนดขนาดส่วนข้อความตามข้อจำกัด embedding model](06-align-chunks-with-embedding-limit.md)

## Comments

Resolution: ใช้ `intfloat/multilingual-e5-small` และกำหนด target 224 tokens กับ hard limit เริ่มต้น 256 tokens โดย effective hard limit คือค่าต่ำสุดระหว่าง config กับ `model.max_seq_length` การนับ hard limit รวม metadata, prefix `passage: ` และ special tokens; Q&A ใช้ prefix เดียวกับเอกสาร ส่วน query ใช้ `query: `

- แยกหัวข้อเป็น metadata และรักษาย่อหน้าที่คั่นด้วยบรรทัดว่าง รายการ Markdown พร้อมบรรทัดต่อเนื่องที่เยื้อง และแถวตารางเป็นหน่วยก่อน pack ตามลำดับเดิม
- target เป็น soft goal: หน่วยที่ถัดไปพอดีกับ hard limit ยังอยู่ครบได้ แม้ chunk เกิน target; chunk จะไม่เกิน hard limit
- ถ้าหน่วยยาวเกิน hard limit ให้ตัดใกล้ sentence/ช่องว่างก่อน แล้ว fallback เป็น tokenizer offsets เมื่อข้อความไม่มี safe whitespace; numeric value กับ unit จะไม่ถูกแยก
- overlap สูงสุด 16 tokens และใช้เฉพาะขอบเขตบรรทัด/หน่วยที่ปลอดภัย โดยไม่ทำให้เกิน hard limit
- preview กับ publish เรียกกติกาเดียวกัน; tests ตรวจค่ากับหน่วย, รายการต่อเนื่อง, แถวตาราง, token budget และการไม่ตกหล่นของอักขระที่มีข้อมูล
