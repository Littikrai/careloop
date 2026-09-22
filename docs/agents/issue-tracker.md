# Issue tracker: Local Markdown

แผนและประเด็นตัดสินใจอยู่ใน `.scratch/<effort>/` โดยใช้ไฟล์ในเครื่อง ไม่ได้เผยแพร่เป็น GitHub Issues

## Wayfinding operations

- Map: `.scratch/<effort>/map.md`, label `wayfinder:map`.
- Child: `issues/NN-<slug>.md`; identity คือชื่อไฟล์ มี `Parent`, `Labels`, `Type`, `Status`, `Assignee`.
- สถานะเริ่มต้น `open`, assignee `unassigned`; claim โดยตั้ง `Status: claimed` และระบุผู้รับผิดชอบก่อนเริ่มงาน
- Blocking: `Blocked by: NN, NN`; `none` หมายถึงไม่มีตัวบล็อก สร้างไฟล์ก่อนเชื่อม dependency
- Frontier: child ที่ open, unassigned และ blocker ทุกตัว resolved; เรียงตามหมายเลข
- Resolution: เพิ่มคำตอบใต้ `## Comments` เป็น resolution comment แล้วตั้ง `Status: resolved`; map เพิ่มเพียง gist และลิงก์ชื่อประเด็น
- ระหว่างสนทนาอ้างประเด็นด้วยชื่อที่อ่านเข้าใจ ไม่ใช้หมายเลขอย่างเดียว
- สเปก MVP จะสร้างหลังตัดสินใจครบ การสร้าง map ยังไม่ถือว่าสเปกเสร็จ
