# งานพัฒนาฐานความรู้จากเอกสาร

แผนปัจจุบันมี 9 tickets สำหรับส่งมอบและปรับการค้นจากฐานความรู้เอกสาร ตามด้วย ticket ตรวจรับและอัปเดตคู่มือเป็นงานสุดท้าย โดยเลื่อนระบบ reindex แบบแยก generation ออกไป เพราะขนาดข้อมูลปัจจุบันยังเล็ก

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

## Frontier

เริ่มพร้อมกันได้ที่ **ทำให้คำตอบจาก Q&A มี contract ที่ปลอดภัย** และ **เพิ่มและตรวจตัวอย่าง Document draft** หลังงาน Document draft เสร็จจึงเริ่ม JSON import ได้ ส่วนการตอบจาก Document ต้องรอทั้ง answer contract และ Document draft

ผล prototype และกติกาแบ่ง Markdown ถูกสรุปแล้ว; tickets #07 (structure-aware chunks) และ #08 (E5 + offline rebuild) เสร็จแล้ว งานถัดไปคือ #09 ตรวจ retrieval และคำตอบภาษาไทย จากนั้น #10 ตรวจรับและอัปเดตคู่มือเป็นงานสุดท้าย

## แหล่งข้อตกลง

- [Decision map: ฐานความรู้จากเอกสารและข้อมูลร้าน](../customer-service-documents/map.md)
- [คำศัพท์โครงการ](../../CONTEXT.md)
