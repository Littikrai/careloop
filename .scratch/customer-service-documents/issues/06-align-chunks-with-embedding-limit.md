# กำหนดขนาดส่วนข้อความตามข้อจำกัด embedding model

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: open
Assignee: unassigned
Blocked by: none

## Question

เมื่อ embedding model ปัจจุบันอ่านได้สูงสุด 128 tokens แต่สเปกเดิมกำหนดส่วนข้อความยาวถึง 1,200 ตัวอักษร ระบบควรแบ่งเนื้อหาและ metadata ด้วย tokenizer ของโมเดลอย่างไร, ควรสงวน token สำหรับ title/product/version/heading เท่าใด, overlap เท่าใด และต้อง reindex อย่างไรเมื่อเปลี่ยน embedding model เพื่อไม่ให้ท้ายข้อความถูกตัดทิ้งโดยไม่รู้ตัว?
