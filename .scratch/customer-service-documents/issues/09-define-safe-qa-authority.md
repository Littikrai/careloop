# กำหนดอำนาจ Q&A โดยไม่ใช้ similarity เป็นความมั่นใจ

Parent: [ฐานความรู้จากเอกสารและข้อมูลร้าน](../map.md)
Labels: `wayfinder:grilling`
Type: HITL
Status: open
Assignee: unassigned
Blocked by: none

## Question

เนื่องจาก cosine similarity ไม่ใช่ค่าความมั่นใจและ threshold เดียวอาจให้ผลต่างกันตามภาษา ข้อมูล และ embedding model รุ่นแรกควรให้ Q&A override เอกสารเฉพาะ exact normalized match, ใช้ flag ที่แอดมินกำหนด หรือคง semantic override ที่ต้องผ่านการปรับเทียบอย่างไร เพื่อไม่ให้ Q&A ที่คล้ายแต่คนละสินค้าไปทับสเปกที่ถูกต้อง?
