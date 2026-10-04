# 03: นำเข้า Document drafts จาก JSON

**What to build:** แอดมินเลือกธุรกิจและนำเข้า JSON หลายเอกสารเป็น drafts ได้ในครั้งเดียว พร้อมผลสร้างและข้ามที่ชัดเจน โดยไฟล์ผิดไม่ทิ้งข้อมูลบางส่วน

**Blocked by:** 02: เพิ่มและตรวจตัวอย่าง Document draft.

**Status:** completed

- [x] รับไฟล์ UTF-8 JSON array รวมไม่เกิน 5 MiB แต่ละรายการมี `title` และ `content` เป็น string ไม่ว่าง และมี `product`, `version` ได้โดยไม่รับ business ID จากไฟล์
- [x] ตรวจ schema, encoding, ขนาด content 256 KiB และทุกรายการก่อนเขียน; รายการหรือไฟล์ผิดทำให้ทั้ง import ล้มเหลวพร้อมตำแหน่งและเหตุผล
- [x] รายการที่ทุก field ซ้ำกันหลัง normalization ภายในไฟล์หรือกับธุรกิจเดียวกันถูกข้ามอย่าง idempotent; ชื่อเหมือนแต่ข้อมูลต่างสร้างคนละ Document และไม่แทนที่ของเดิมโดยอัตโนมัติ
- [x] Import ที่สำเร็จสร้าง Draft ทั้งชุดใน transaction เดียว ไม่ publish หรือสร้าง vectors และพากลับรายการ Draft ของธุรกิจพร้อมจำนวนสร้าง/ข้าม
- [x] มีไฟล์ตัวอย่าง JSON ที่ไม่มี secrets และทดสอบ success, duplicate, mixed invalid input, unknown/extra fields, oversized file/content และ business isolation

## Verification

ผ่าน Django system check, migration check, mypy และชุดทดสอบเต็ม 80 รายการ ทดสอบนำเข้าไฟล์ตัวอย่างจริง, ข้อผิดพลาดพร้อมตำแหน่ง, Unicode ที่ผิดในทุก field และยืนยันว่า import ไม่เรียก embedding หรือสร้าง vectors
