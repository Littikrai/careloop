# กำหนดรูปแบบข้อมูลต้นทางรุ่นแรก

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: none

## Question

ในรุ่นแรกแอดมินจะเพิ่มข้อมูลต้นทางรูปแบบใดบ้างระหว่างข้อความที่วางเอง, TXT/Markdown, JSON ที่มี title/content, PDF/DOCX และตารางสเปก และแต่ละรูปแบบต้องมี metadata อะไรเพื่อระบุธุรกิจ สินค้า และเวอร์ชันได้ชัดเจน?

## Comments

Resolution: รุ่นแรกให้แอดมินเลือกธุรกิจในหน้าเว็บเสมอ เพื่อไม่รับ business ID จากไฟล์และรักษาการแยกข้อมูล ใช้ข้อมูลต้นทางได้สามแบบ: ข้อความที่วางในหน้าเว็บ, ไฟล์ UTF-8 .txt หรือ .md, และไฟล์ UTF-8 JSON array สำหรับนำเข้าหลายเอกสาร

เอกสารทุกฉบับต้องมี title และ content; product และ version เป็น metadata ทางเลือกเพื่อให้แอดมินระบุสเปกได้ชัดเจน ระบบเก็บชื่อไฟล์เป็น source name เมื่อมาจากไฟล์ ตัวอย่าง JSON คือ:

```json
[
  {
    "title": "Router X500 specification",
    "content": "## Performance\nWAN throughput: 2.5 Gbps",
    "product": "Router X500",
    "version": "2026.1"
  }
]
```

กำหนดขนาดเนื้อหาหรือไฟล์รวมไม่เกิน 5 MiB ต่อการนำเข้าหนึ่งครั้ง เพื่อให้ระบบ self-hosted แบบ CPU ตรวจและแยกข้อความได้แน่นอน รุ่นแรกไม่รับ PDF, DOCX, CSV, HTML, ไฟล์สแกน/OCR หรือการแยกตารางเฉพาะทาง; ผู้ใช้วางข้อความหรือแปลงเป็น Markdown/JSON ก่อน
