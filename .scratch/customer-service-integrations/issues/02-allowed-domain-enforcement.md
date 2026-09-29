# กำหนดการบังคับใช้ allowed domains ของ widget

Parent: [ช่องทางเชื่อมต่อเว็บธุรกิจ](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 01

## Question

ระบบตรวจ allowed domains, กำหนด CSP `frame-ancestors`, รองรับ localhost และแจ้งข้อผิดพลาดของการฝัง widget อย่างไร โดยไม่อ้างว่า Origin/Referer เป็นการยืนยันตัวตนของผู้เรียก?

## Comments

Resolution: แอดมินกำหนด allowed domain เป็น origin แบบเจาะจงต่อธุรกิจ (scheme, host และ port; ไม่มี path หรือ wildcard). Widget response ส่ง CSP `frame-ancestors` จากรายการนี้ ซึ่งเป็นกลไกหลักที่ browser ใช้ห้ามเว็บอื่นฝัง iframe. Development อนุญาต origin localhost ที่แอดมินเพิ่มไว้ เช่น `http://localhost:3000`; production ต้องใช้ HTTPS origin. Origin/Referer ใช้เพียงแสดง diagnostic และไม่ใช่ credential. Token ที่ถูกเปิดเองนอก iframe ไม่ทำให้ธุรกิจอื่นเข้าถึงฐานความรู้ เพราะ token ผูกกับธุรกิจเดียว.
