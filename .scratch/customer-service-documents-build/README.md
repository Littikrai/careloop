# งานพัฒนาฐานความรู้จากเอกสาร

ผู้ใช้อนุมัติการแบ่งงาน 8 tickets และ dependency ตาม decision map แล้ว งานแต่ละใบเป็น vertical slice ที่ตรวจสอบได้ด้วยตัวเอง

## งานตามลำดับ

- [ทำให้คำตอบจาก Q&A มี contract ที่ปลอดภัย](issues/01-safe-qa-answer-contract.md)
- [เพิ่มและตรวจตัวอย่าง Document draft](issues/02-document-draft-preview.md)
- [นำเข้า Document drafts จาก JSON](issues/03-document-json-import.md)
- [เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง](issues/04-publish-document-answer-with-sources.md)
- [แทนที่ Archive และลบ Document อย่างปลอดภัย](issues/05-safe-document-lifecycle.md)
- [รักษาแชตให้ใช้งานได้ระหว่าง indexing](issues/06-responsive-indexing.md)
- [สร้างดัชนีใหม่เมื่อ embedding model หรือ chunker เปลี่ยน](issues/07-safe-knowledge-reindex.md)
- [ตรวจรับฐานความรู้จากเอกสารและอัปเดตคู่มือ](issues/08-document-knowledge-release.md)

## Frontier

เริ่มพร้อมกันได้ที่ **ทำให้คำตอบจาก Q&A มี contract ที่ปลอดภัย** และ **เพิ่มและตรวจตัวอย่าง Document draft** หลังงาน Document draft เสร็จจึงเริ่ม JSON import ได้ ส่วนการตอบจาก Document ต้องรอทั้ง answer contract และ Document draft

## แหล่งข้อตกลง

- [Decision map: ฐานความรู้จากเอกสารและข้อมูลร้าน](../customer-service-documents/map.md)
- [คำศัพท์โครงการ](../../CONTEXT.md)

