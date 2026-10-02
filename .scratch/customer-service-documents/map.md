# ฐานความรู้จากเอกสารและข้อมูลร้าน

Label: `wayfinder:map`

## Destination

มีสเปกพร้อมพัฒนาสำหรับให้เจ้าของธุรกิจเพิ่มข้อมูลร้าน คู่มือ และสเปกสินค้าเป็นเอกสารต้นทาง ระบบแยกส่วนข้อความเพื่อค้นหาและตอบคำถามได้ โดยยังรักษา Q&A ที่ดูแลเองไว้สำหรับคำตอบที่ต้องควบคุม

## Notes

ต่อยอด Customer Service Bot ปัจจุบันที่แยกธุรกิจ ใช้ sentence-transformers และ Qdrant ในเครื่อง และ OpenRouter สำหรับเรียบเรียงคำตอบ ใช้คำศัพท์จาก CONTEXT.md และบันทึกการตัดสินใจใน ticket ก่อนแตกเป็น implementation tickets

## Decisions so far

- [กำหนดรูปแบบข้อมูลต้นทางรุ่นแรก](issues/01-define-first-source-formats.md): เพิ่มข้อความ, TXT/Markdown และ JSON title/content; business เลือกใน admin และ product/version เป็น metadata ทางเลือก

## Not yet specified

- การ sync ข้อมูลจาก URL, CMS หรือระบบสินค้าภายนอก
- การแสดงแหล่งอ้างอิงหรือหัวข้อเอกสารในคำตอบลูกค้า
- การสร้าง FAQ suggestions อัตโนมัติจากเอกสารและขั้นตอนตรวจรับ

## Out of scope

- การเก็บบทสนทนา, feedback และ insight: อยู่ในงานอนาคตที่เลื่อนไว้
- PDF/DOCX, CSV, HTML, OCR และการแยกตารางเฉพาะทาง: ใช้การแปลงเป็นข้อความหรือ Markdown ก่อนในรุ่นแรก
- การเชื่อมระบบภายนอกแบบอัตโนมัติ: ต้องกำหนดใน effort ถัดไป
