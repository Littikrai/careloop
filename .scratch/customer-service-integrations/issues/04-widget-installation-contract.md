# กำหนด contract การติดตั้ง widget

Parent: [ช่องทางเชื่อมต่อเว็บธุรกิจ](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 02

## Question

script tag, configuration, iframe URL, การแสดงปุ่มลอย, accessibility และ fallback ของ widget ควรมีหน้าตาและพฤติกรรมใดสำหรับเว็บที่ฝัง?

## Comments

Resolution: ระบบสร้าง script tag ที่มี embed token ให้แอดมินคัดลอก และ script สร้างปุ่มแชตลอยเปิด/ปิด iframe จาก public base URL. ค่าเริ่มต้นอยู่มุมขวาล่าง, มี accessible name, ใช้ keyboard ได้, ส่ง focus เข้าหน้าต่างเมื่อเปิดและคืนให้ปุ่มเมื่อปิด. ไม่มี third-party asset หรือ API key ใน browser. ผู้ที่ต้องกำหนด layout เองใช้ iframe URL ของ token เดียวกันได้. หาก domain ไม่ได้รับอนุญาต browser จะ block ด้วย CSP; admin เห็นรายการ allowed domains และตัวอย่าง localhost สำหรับ development.
