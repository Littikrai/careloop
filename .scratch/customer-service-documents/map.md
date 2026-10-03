# ฐานความรู้จากเอกสารและข้อมูลร้าน

Label: `wayfinder:map`

## Destination

มีสเปกพร้อมพัฒนาสำหรับให้เจ้าของธุรกิจเพิ่มข้อมูลร้าน คู่มือ และสเปกสินค้าเป็นเอกสารต้นทาง ระบบแยกส่วนข้อความเพื่อค้นหาและตอบคำถามได้ โดยยังรักษา Q&A ที่ดูแลเองไว้สำหรับคำตอบที่ต้องควบคุม

## Notes

ต่อยอด Customer Service Bot ปัจจุบันที่แยกธุรกิจ ใช้ sentence-transformers และ Qdrant ในเครื่อง และ OpenRouter สำหรับเรียบเรียงคำตอบ ใช้คำศัพท์จาก CONTEXT.md และบันทึกการตัดสินใจใน ticket ก่อนแตกเป็น implementation tickets

## Decisions so far

- [กำหนดรูปแบบข้อมูลต้นทางรุ่นแรก](issues/01-define-first-source-formats.md): เพิ่มข้อความ, TXT/Markdown และ JSON title/content; business เลือกใน admin และ product/version เป็น metadata ทางเลือก
- [กำหนดวงจรชีวิตเอกสารและส่วนข้อความ](issues/02-define-document-and-chunk-lifecycle.md): Published เดิมทำงานจน draft revision ใหม่สร้างทุก vector สำเร็จ แล้วสลับฉบับพร้อม archive ของเดิมในครั้งเดียว
- [กำหนดสัญญาการค้นหาและตอบจากเอกสาร](issues/03-define-document-retrieval-contract.md): ค้น Q&A และส่วนข้อความเฉพาะฉบับใช้งาน จำกัด context ก่อนส่ง LLM ปฏิเสธเมื่อหลักฐานไม่พอ และคืนแหล่งอ้างอิงที่เปิดเผยได้

## Not yet specified

ไม่มี

## Out of scope

- การเก็บบทสนทนา, feedback และ insight: อยู่ในงานอนาคตที่เลื่อนไว้
- PDF/DOCX, CSV, HTML, OCR และการแยกตารางเฉพาะทาง: ใช้การแปลงเป็นข้อความหรือ Markdown ก่อนในรุ่นแรก
- การเชื่อมระบบภายนอกแบบอัตโนมัติ: ต้องกำหนดใน effort ถัดไป
- การสร้าง FAQ suggestions อัตโนมัติจากเอกสาร: เป็นการปรับปรุงภายหลัง เพราะรุ่นแรกค้นและตอบจากเอกสารได้โดยตรง
