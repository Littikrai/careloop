# 05: แทนที่ Archive และลบ Document อย่างปลอดภัย

**What to build:** แอดมินแก้ไขความรู้ใน Document ผ่าน replacement revision หรือหยุดใช้ด้วย Archive/Delete ได้ โดยลูกค้าเห็นฉบับเก่าจนฉบับใหม่พร้อมและไม่เห็น stale vectors หลังสลับ

**Blocked by:** 04: เผยแพร่ Document และตอบพร้อมแหล่งอ้างอิง.

**Status:** completed

- [x] Document หนึ่งรายการมี Published revision และ editable Draft replacement ได้อย่างละไม่เกินหนึ่ง; Create replacement draft คัดลอกข้อมูลเดิมและไม่แก้ Published โดยตรง
- [x] การ publish replacement สร้าง chunks/vectors ใหม่ทั้งหมดก่อน แล้วสลับ revision ใหม่เป็น Published และฉบับเดิมเป็น Archived ใน database transaction เดียว
- [x] หาก validation, embedding หรือ Qdrant ล้มเหลว Published เดิมยังถูกค้นได้ Draft แสดง Failed/error และสามารถลอง publish ใหม่ได้
- [x] Archive มีหน้ารับรองและหยุด revision จาก retrieval ทันที; การนำกลับมาใช้สร้าง Draft ใหม่ ส่วนการลบถาวรทำได้เฉพาะ Draft หรือ Archived
- [x] Vector cleanup หลัง replace/archive/delete เป็น best effort และ retrieval จำกัด active vector IDs จากฐานข้อมูลเสมอ จึงไม่คืน stale vectors แม้ cleanup ล้มเหลว
- [x] ทดสอบ replace สำเร็จ/ล้มเหลว, archive โดยไม่มีตัวแทน, restore ผ่าน draft ใหม่, deletion rules, stale vector filtering และการแยกธุรกิจ

## Verification

ผ่าน Django system check, migration check, mypy และชุดทดสอบเต็ม 101 รายการ
