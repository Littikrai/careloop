# กำหนด contract ของ Chat API

Parent: [ช่องทางเชื่อมต่อเว็บธุรกิจ](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: 01

## Question

Chat API รุ่นแรกต้องรับและตอบข้อมูลใด มี HTTP status และ error shape ใด และจะผูก API key กับธุรกิจและ rate limit อย่างไร โดยมีเฉพาะคำถาม/คำตอบแบบ synchronous?

## Comments

Resolution: มี `POST /api/v1/chat` เพียง endpoint เดียว รับ `Authorization: Bearer <api-key>` และ JSON `{ "question": "..." }`. API key ระบุธุรกิจโดยตรง; ไม่มี business ID จาก caller. คำตอบสำเร็จเป็น JSON ที่มี `answer` และ `status`; validation ใช้ 422, key ไม่มี/ไม่ถูกต้อง/ถูกเพิกถอนใช้ 401, เกิน rate limit ใช้ 429, และ RAG/LLM ใช้งานไม่ได้ใช้ 503 พร้อม error code ที่ไม่เปิดเผยรายละเอียดภายใน. รุ่นแรกเป็น synchronous, ไม่รับ CORS browser call, ไม่รับ streaming, webhook, หรือ customer identifier. Rate limit แยกตาม API key และมีค่าตั้งต้นใน config.
