# ช่องทางเชื่อมต่อเว็บธุรกิจ

Label: `wayfinder:map`

## Destination

มีสเปกพร้อมพัฒนาสำหรับ widget ที่เว็บธุรกิจฝังได้และ Chat API สำหรับ backend ของธุรกิจ โดยแยกธุรกิจ ปกป้อง credential และรองรับการทดสอบบน localhost.

## Notes

โดเมนนี้ต่อยอด Customer Service Bot ที่มีธุรกิจ ฐานความรู้ และหน้าแชตอยู่แล้ว ใช้คำศัพท์ใน `CONTEXT.md` และบันทึกผลเป็น decision documents ก่อนแตกเป็น implementation tickets.

## Decisions so far

- [กำหนดวงจรชีวิตของ embed token และ API key](issues/01-integration-credential-lifecycle.md): ธุรกิจมี token สาธารณะและ key ลับแบบ hash; rotate key มีช่วงเปลี่ยนผ่าน 24 ชั่วโมง และ revoke มีผลทันที
- [กำหนดการบังคับใช้ allowed domains ของ widget](issues/02-allowed-domain-enforcement.md): ใช้ exact origin ต่อธุรกิจและ CSP `frame-ancestors`; localhost เป็น allowed origin สำหรับ development
- [กำหนด contract ของ Chat API](issues/03-chat-api-contract.md): backend-only Bearer API มี endpoint synchronous เดียวและ error/status ที่กำหนดชัด
- [กำหนด contract การติดตั้ง widget](issues/04-widget-installation-contract.md): script ปุ่มลอยและ direct iframe ใช้ embed token เดียวกัน พร้อม accessibility พื้นฐาน
- [กำหนดการบันทึกแหล่งที่มาของบทสนทนา](issues/05-conversation-source-attribution.md): Conversation ระบุ widget/API และ integration record โดยไม่เก็บ secret หรือตัวระบุลูกค้า
- ใช้ widget script ที่สร้างปุ่มแชตลอย และมี iframe โดยตรงสำหรับผู้ที่วางตำแหน่งเอง
- Chat API เป็น backend-only และรับ credential ผ่าน `Authorization: Bearer <api-key>`
- ธุรกิจมี embed token แบบสาธารณะ และ API key แบบลับที่เก็บ hash แสดงค่าเต็มครั้งเดียว พร้อม rotate/revoke
- widget จำกัด allowed domains ต่อธุรกิจ; production ใช้ HTTPS ส่วน development รองรับ `localhost`
- บันทึกแหล่งที่มาของคำถามเป็น `widget` หรือ `api` เพื่อใช้กับบทสนทนาและ insight

## Not yet specified

- การผูกตัวระบุลูกค้าจาก backend กับบทสนทนา และนโยบายเก็บรักษาข้อมูล
- รูปแบบ streaming, webhook, quota/billing และ SDK ของ API
- การเชื่อมช่องทาง third-party เช่น LINE, Facebook Messenger และ WhatsApp

## Out of scope

- การสร้างบัญชีหรือสิทธิ์ admin แยกต่อธุรกิจ: เจ้าของระบบคนเดียวจัดการทุกธุรกิจตามขอบเขตปัจจุบัน
