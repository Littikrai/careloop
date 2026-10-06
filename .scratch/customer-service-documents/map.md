# ฐานความรู้จากเอกสารและข้อมูลร้าน

Label: `wayfinder:map`

## Destination

มีข้อสรุปพร้อมแตกเป็นงานพัฒนาสำหรับปรับการค้นหาจากไฟล์ Markdown ภาษาไทย โดยเลือก embedding model ที่รองรับข้อความยาวขึ้นจากผลทดลอง และกำหนดการแบ่งส่วนที่รักษาหัวข้อ ย่อหน้า รายการ และตารางไว้ครบ โดย PDF/OCR ยังอยู่นอกขอบเขต

## Notes

ต่อยอด Customer Service Bot ปัจจุบันที่แยกธุรกิจ ใช้ sentence-transformers และ Qdrant ในเครื่อง และ OpenRouter สำหรับเรียบเรียงคำตอบ ใช้คำศัพท์จาก CONTEXT.md และบันทึกการตัดสินใจใน ticket ก่อนแตกเป็น implementation tickets

การต่อยอดรอบนี้จำกัดที่ `.md` ใช้ AquaFlow P200 และคำถามภาษาไทยเป็นชุดทดลอง เปรียบเทียบ retrieval แยกจากคำตอบ LLM และใช้โมเดล OpenRouter ตัวเดิมตลอดการเทียบผล

## Decisions so far

- [กำหนดรูปแบบข้อมูลต้นทางรุ่นแรก](issues/01-define-first-source-formats.md): เพิ่มข้อความ, TXT/Markdown และ JSON title/content; business เลือกใน admin และ product/version เป็น metadata ทางเลือก
- [กำหนดวงจรชีวิตเอกสารและส่วนข้อความ](issues/02-define-document-and-chunk-lifecycle.md): Published เดิมทำงานจน draft revision ใหม่สร้างทุก vector สำเร็จ แล้วสลับฉบับพร้อม archive ของเดิมในครั้งเดียว
- [กำหนดสัญญาการค้นหาและตอบจากเอกสาร](issues/03-define-document-retrieval-contract.md): ค้น Q&A และส่วนข้อความเฉพาะฉบับใช้งาน จำกัด context ก่อนส่ง LLM ปฏิเสธเมื่อหลักฐานไม่พอ และคืนแหล่งอ้างอิงที่เปิดเผยได้
- [กำหนดขั้นตอนแอดมินสำหรับเพิ่มความรู้](issues/04-define-admin-knowledge-workflow.md): ใช้เมนู Documents ใน Django Admin สำหรับเพิ่มหรือ import draft, preview chunks, publish ทีละเอกสาร, ทดสอบ retrieval และแทนที่หรือ archive อย่างปลอดภัย
- [กำหนดบทบาท Q&A เดิมร่วมกับเอกสาร](issues/05-define-qa-compatibility.md): เก็บ Q&A เดิมโดยไม่ migration และใช้ร่วมกับเอกสาร โดย Q&A จะมีอำนาจเหนือกว่าเฉพาะ exact normalized match
- [กำหนดขนาดส่วนข้อความตามข้อจำกัด embedding model](issues/06-align-chunks-with-embedding-limit.md): แบ่งด้วย tokenizer ภายใน model limit, สงวน metadata budget และ rebuild ดัชนีแบบ offline พร้อม backup/rollback เมื่อเปลี่ยนโมเดลหรือ chunker
- [ทดลอง embedding model สำหรับ Markdown ภาษาไทยที่รองรับข้อความยาว](issues/10-benchmark-long-context-embedding.md): เลือก `intfloat/multilingual-e5-small` จาก retrieval benchmark; ยืนยัน retrieval improvement โดยยังไม่อ้างคุณภาพคำตอบ LLM
- [กำหนดกติกาแบ่ง Markdown โดยรักษาหน่วยความหมาย](issues/11-define-markdown-structure-aware-chunking.md): target 224, hard limit 256 รวม metadata/prefix/special tokens; pack paragraphs, list items and table rows, then safe fallback with bounded overlap
- [กำหนดสัญญาผลลัพธ์ LLM ข้ามโมเดล OpenRouter](issues/08-define-openrouter-output-contract.md): บังคับ JSON Schema และ provider compatibility, ปิด reasoning และตรวจ source IDs; free router ใช้ทดลองได้แต่แนะนำ model คงที่สำหรับงานจริง
- [กำหนดวิธีทำดัชนีโดยไม่หยุดบริการแชต](issues/07-keep-chat-responsive-during-indexing.md): ใช้ Gunicorn process เดียวแบบ gthread, serialize local Qdrant และ embedding เป็น batch พร้อม lease-based retry โดย Published เดิมยังตอบได้
- [กำหนดอำนาจ Q&A โดยไม่ใช้ similarity เป็นความมั่นใจ](issues/09-define-safe-qa-authority.md): ให้ Q&A override เฉพาะ exact normalized match; semantic score ใช้ค้นและจัดอันดับเท่านั้น และข้อมูลขัดกันต้องถามเพิ่มหรือปฏิเสธ

## Not yet specified

ยังไม่มีประเด็นที่ระบุเป็น ticket เพิ่มได้; ผล prototype อาจเปิดเผยคำถามใหม่

## Out of scope

- การเก็บบทสนทนา, feedback และ insight: อยู่ในงานอนาคตที่เลื่อนไว้
- PDF/DOCX, CSV, HTML, OCR และการแยกตารางเฉพาะทาง: ใช้การแปลงเป็นข้อความหรือ Markdown ก่อนในรุ่นแรก
- การเชื่อมระบบภายนอกแบบอัตโนมัติ: ต้องกำหนดใน effort ถัดไป
- การสร้าง FAQ suggestions อัตโนมัติจากเอกสาร: เป็นการปรับปรุงภายหลัง เพราะรุ่นแรกค้นและตอบจากเอกสารได้โดยตรง
