# กำหนดวงจรชีวิตของ embed token และ API key

Parent: [ช่องทางเชื่อมต่อเว็บธุรกิจ](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: none

## Question

embed token และ API key ของแต่ละธุรกิจต้องมีข้อมูลประกอบ รูปแบบการสร้าง การแสดงครั้งเดียว การเก็บ hash การ rotate/revoke และผลต่อ integration ที่กำลังใช้งานอย่างไร?

## Comments

Resolution: แต่ละธุรกิจมี embed token สาธารณะหนึ่งค่าและ API key ลับหนึ่งค่าที่ active ได้ในเวลาเดียวกัน API key แสดงค่าเต็มเพียงครั้งเดียวและระบบเก็บเฉพาะ hash. การ rotate สร้าง key ใหม่และให้ key เก่าทำงานต่อ 24 ชั่วโมงเพื่อให้ backend เปลี่ยนค่าได้; admin เพิกถอน key เก่าก่อนครบกำหนดได้ทันที. การ revoke embed token มีผลทันทีและทำให้ widget เดิมใช้งานไม่ได้จนกว่าจะติดตั้ง token ใหม่.
