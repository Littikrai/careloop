# กำหนดสัญญาผลลัพธ์ LLM ข้ามโมเดล OpenRouter

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: open
Assignee: unassigned
Blocked by: none

## Question

ระบบจะบังคับให้ LLM คืน status, answer และ source IDs ที่ตรวจสอบได้อย่างไรเมื่อ OpenRouter รองรับ structured outputs เฉพาะโมเดลที่เข้ากัน และค่าเริ่มต้น `openrouter/free` อาจเลือกโมเดลต่างกันในแต่ละครั้ง; จะใช้ JSON Schema กับ `require_parameters`, กำหนด fallback หรือจัดการโมเดลที่ไม่รองรับอย่างไร?
