# 02: เพิ่มและตรวจตัวอย่าง Document draft

**What to build:** แอดมินสร้าง Document draft จากข้อความที่วางหรือไฟล์ TXT/Markdown แล้วตรวจ metadata เนื้อหาที่ normalize และ chunk preview ได้ก่อนเผยแพร่ โดยข้อมูลยังไม่ออกสู่แชต

**Blocked by:** None (can start immediately).

**Status:** completed

- [x] Document แยกตามธุรกิจและมี logical identity กับ revisions; draft บังคับ `business`, `title`, `content` และรองรับ `product`, `version`, `source name` เป็นข้อมูลทางเลือกตามชนิดข้อมูล
- [x] แอดมินสร้าง draft จากข้อความหรือไฟล์ UTF-8 `.txt`/`.md` ได้ ไฟล์หนึ่งฉบับไม่เกิน 256 KiB และข้อความผิด encoding หรือเกินขนาดถูกปฏิเสธพร้อมเหตุผล
- [x] หน้า draft แสดงเนื้อหาที่ normalize แล้ว จำนวนตัวอักษร metadata และ chunk preview ตามลำดับ โดย preview ไม่สร้าง vector และไม่ทำให้ document ถูกค้นพบ
- [x] Chunker แบ่งตาม heading/ย่อหน้าแล้วใช้ tokenizer ของ embedding model, สงวน token budget สำหรับ metadata และ special tokens, overlap ตามสเปก และปฏิเสธ chunk ที่เกิน model limit แทนการปล่อยให้ถูก truncate
- [x] Draft แก้ไขได้ ส่วน Published/Archived ที่จะเพิ่มภายหลังต้องรองรับการเป็น read-only โดยโครงสร้างข้อมูลไม่ต้องย้าย Document เดิมใหม่
- [x] ทดสอบข้อความไทย/อังกฤษ, heading/list/Markdown table, metadata ยาว, token window ยาวเกินหนึ่ง chunk, upload ผิดชนิด/encoding/ขนาด และการแยกธุรกิจ

## Verification

ผ่าน Django system check, migration check, mypy และชุดทดสอบเต็ม 72 รายการ ทดสอบ chunk preview กับ tokenizer ของ embedding model จริงโดยทุก chunk อยู่ภายใน model limit และยืนยันว่า preview ไม่สร้าง vector
