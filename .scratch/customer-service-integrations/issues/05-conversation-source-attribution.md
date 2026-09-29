# กำหนดการบันทึกแหล่งที่มาของบทสนทนา

Parent: [ช่องทางเชื่อมต่อเว็บธุรกิจ](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 03, 04

## Question

เมื่อเพิ่มบทสนทนาและ feedback ระบบต้องเก็บ source จาก widget/API และ integration identifier อย่างไร เพื่อให้ insight แยกช่องทางได้โดยไม่เก็บตัวตนลูกค้าเกินจำเป็น?

## Comments

Resolution: เมื่อ ticket บทสนทนาถูกพัฒนา Conversation เก็บ `source` เป็น `widget` หรือ `api` และเก็บ integration record ID ของ embed token หรือ API key ที่รับ request โดยไม่เก็บค่า token/key หรือ identifier ของลูกค้า. การดู insight สามารถ aggregate ตาม source และ integration record ได้. การรับ customer identifier, history ข้าม session และ retention ยังคงเป็นประเด็นแยกในแผนหลัก.
