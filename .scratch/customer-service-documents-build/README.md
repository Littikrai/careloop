# งานพัฒนาฐานความรู้จากเอกสาร

แผนนี้ส่งมอบการค้นจากฐานความรู้เอกสาร รวม 10 tickets โดยเลื่อนระบบ reindex แบบแยก generation ออกไป เพราะขนาดข้อมูลปัจจุบันยังเล็ก

## งานตามลำดับ

- [ทำให้คำตอบจาก Q&A มี contract ที่ปลอดภัย](issues/01-safe-qa-answer-contract.md)
- [เพิ่มและตรวจตัวอย่าง Document draft](issues/02-document-draft-preview.md)
- [นำเข้า Document drafts จาก JSON](issues/03-document-json-import.md)
- [เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง](issues/04-publish-document-answer-with-sources.md)
- [แทนที่ Archive และลบ Document อย่างปลอดภัย](issues/05-safe-document-lifecycle.md)
- [รักษาแชตให้ใช้งานได้ระหว่าง indexing](issues/06-responsive-indexing.md)
- [รักษาโครงสร้าง Markdown ใน preview และการค้นคืน](issues/07-markdown-structure-aware-chunks.md)
- [ใช้ embedding model ที่เลือกและ rebuild ดัชนีระหว่าง maintenance](issues/08-long-context-embedding-model.md)
- [ตรวจผลค้นหาและคำตอบจาก Markdown ภาษาไทย](issues/09-verify-markdown-retrieval.md)

## ตรวจรับและปิดงาน

- [ตรวจรับฐานความรู้จากเอกสารและอัปเดตคู่มือ](issues/10-document-knowledge-release.md)

## สถานะ

Tickets #01–#10 เสร็จครบแล้ว ไม่มีการ์ดค้าง การตรวจรับสุดท้ายบันทึกไว้ใน [ticket #10](issues/10-document-knowledge-release.md) และผลทดสอบคำถาม AquaFlow 10 ข้ออยู่ใน [test report](../../test-results/aquaflow-p200-qwen3.8-flash.json)

ผล prototype และกติกาแบ่ง Markdown ถูกสรุปไว้ใน decision map; tickets #07 (structure-aware chunks), #08 (E5 + offline rebuild), #09 (ตรวจ retrieval และคำตอบภาษาไทย) และ #10 (ตรวจรับและอัปเดตคู่มือ) เสร็จแล้ว

## แหล่งข้อตกลง

- [Decision map: ฐานความรู้จากเอกสารและข้อมูลร้าน](../customer-service-documents/map.md)
- [คำศัพท์โครงการ](../../CONTEXT.md)
