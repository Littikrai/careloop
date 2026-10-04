# กำหนดสัญญาผลลัพธ์ LLM ข้ามโมเดล OpenRouter

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: resolved
Assignee: root
Blocked by: none

## Question

ระบบจะบังคับให้ LLM คืน status, answer และ source IDs ที่ตรวจสอบได้อย่างไรเมื่อ OpenRouter รองรับ structured outputs เฉพาะโมเดลที่เข้ากัน และค่าเริ่มต้น `openrouter/free` อาจเลือกโมเดลต่างกันในแต่ละครั้ง; จะใช้ JSON Schema กับ `require_parameters`, กำหนด fallback หรือจัดการโมเดลที่ไม่รองรับอย่างไร?

## Comments

Resolution: ใช้ Chat Completions แบบ non-streaming และบังคับ structured output ทุกคำขอด้วย `response_format.type=json_schema`, `strict=true` และ schema ที่มีเพียง `status`, `answer`, `source_ids` พร้อม `additionalProperties=false` ตั้ง `provider.require_parameters=true` เพื่อไม่ให้ OpenRouter ส่งคำขอไปยัง endpoint ที่ไม่รองรับ parameter เหล่านี้

ปิด reasoning สำหรับงานตอบลูกค้าด้วย `reasoning: {"effort": "none", "exclude": true}` เพราะคำตอบสั้นจาก context ไม่ควรเสียเวลาและ token กับ reasoning หากโมเดลหรือ provider ที่ผู้ติดตั้งกำหนดไม่รองรับ contract ครบ ให้คำขอล้มเหลวเป็น `service_error` แทนการลดข้อกำหนดหรือพยายาม parse ข้อความอิสระ

### ผลทดลองกับ API จริง

ทดลอง payload เดียวกัน 3 ครั้งกับค่าเริ่มต้น `openrouter/free` โดยถามภาษาไทยเรื่องเวลาเปิดร้านจากสองแหล่งข้อมูล และขอ JSON Schema เดียวกันทุกครั้ง:

| ครั้ง | โมเดลที่ router เลือก | เวลา | ผล | Reasoning |
| --- | --- | ---: | --- | --- |
| 1 | `nvidia/nemotron-3-super-120b-a12b:free` | 1.75 วินาที | JSON ถูก schema แต่คืน `insufficient_knowledge` ทั้งที่มีข้อมูล | ไม่มี field/details, 0 tokens |
| 2 | `qwen/qwen3.8-27b:free` | 2.66 วินาที | ตอบเวลาเปิดร้านถูกและอ้าง `src-hours` | ไม่มี field/details, 0 tokens |
| 3 | `dots-studio/dots-3-note-preview:free` | 1.72 วินาที | ตอบเวลาเปิดร้านถูกและอ้าง `src-hours` | ไม่มี field/details, 0 tokens |

ผลยืนยันว่า JSON Schema ร่วมกับ `require_parameters` และการปิด reasoning ควบคุมรูปทรง response ได้ข้ามโมเดลที่ router เลือก แต่ `openrouter/free` ยังมีคุณภาพเชิงความหมายไม่คงที่เพราะแต่ละคำขออาจได้คนละโมเดล การปฏิเสธผิดเป็น false negative ที่ปลอดภัยกว่าการแต่งคำตอบ และไม่ควร retry จนกว่าจะได้ `answer`

### การตรวจผลและ fallback

- ระบบ parse JSON แล้วตรวจ exact keys, status enum, ชนิดข้อมูล, จำนวน source IDs และยืนยันว่า source ID ทุกตัวอยู่ใน context ของคำขอนั้น
- `answer` ใช้ข้อความจากโมเดล; `needs_clarification` ใช้คำถามสั้นจากโมเดล; `insufficient_knowledge` ทิ้งข้อความจากโมเดลและใช้ข้อความ local ที่กำหนดใน `RAG_INSUFFICIENT_MESSAGE` เพื่อให้สม่ำเสมอ
- JSON ผิด schema, source ID ปลอม, content ว่าง, HTTP error หรือโมเดลไม่รองรับ parameter เป็น `service_error` และไม่เผยรายละเอียด provider ให้ลูกค้า
- ไม่มี application-level model fallback และไม่ retry valid completion ภายในคำถามเดียว OpenRouter ทำ provider routing ได้ภายใต้ `require_parameters`; หากยังล้มเหลวให้ลูกค้าลองใหม่ภายหลัง
- คง `openrouter/free` เป็นค่าเริ่มต้นสำหรับทดลองติดตั้ง แต่เอกสารต้องระบุว่าคุณภาพอาจเปลี่ยนระหว่างคำขอ และแนะนำให้ตั้ง `OPENROUTER_MODEL` เป็น model slug คงที่สำหรับการใช้งานจริง
