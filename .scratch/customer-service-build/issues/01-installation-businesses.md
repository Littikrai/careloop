# 01: ติดตั้งระบบและจัดการธุรกิจ

**What to build:** ผู้ติดตั้งเริ่มระบบด้วย Docker Compose บน CPU ได้ แอดมินล็อกอิน สร้างหลายธุรกิจ และเปิดลิงก์หน้าเว็บแชตเฉพาะธุรกิจได้ โดยข้อมูลคงอยู่หลังเริ่มระบบใหม่

**Blocked by:** None (can start immediately).

**Status:** implemented-awaiting-container-verification

- [x] มีขั้นตอนตั้งค่าครั้งแรกและสร้างบัญชี admin ที่ใช้งานได้จริง โดยไม่ใช้รหัสผ่านสาธารณะตายตัว
- [x] admin ล็อกอิน/ออกจากระบบได้ และดูแลทุกธุรกิจในการติดตั้งเดียวกันได้; user ไม่ต้องสมัครบัญชีหรือล็อกอิน
- [x] admin สร้างและดูรายการธุรกิจได้ แต่ละธุรกิจมีลิงก์หน้าแชตที่ระบุธุรกิจชัดเจน; user เข้าถึงหน้าหรือการดำเนินการของ admin ไม่ได้
- [x] หน้าแชตที่ยังไม่มีความรู้แสดงสถานะตามจริง โดยไม่อ้างว่าตอบด้วย LLM ได้แล้ว
- [x] ข้อมูลธุรกิจและบัญชี admin ยังคงอยู่หลัง restart; secrets ไม่ถูกส่งไปยังหน้าเว็บสาธารณะ
- [x] ตรวจเส้นทางติดตั้ง → ล็อกอิน → สร้างสองธุรกิจ → เปิดลิงก์แชต รวมถึงการเรียกงาน admin โดยไม่ล็อกอิน

## รายละเอียดที่ต้องสรุปก่อนดำเนินงานส่วนที่เกี่ยวข้อง

ก่อนเลือกส่วนประกอบ ให้สรุปชุดเว็บ/ฐานข้อมูลและรูปแบบ config จากประเด็นชุดเทคโนโลยีและค่าเริ่มต้นพร้อมติดตั้ง ไม่ถือว่าผู้ใช้เลือก framework หรือ vector database รายใดแล้ว; ระบบปฏิบัติการที่ยังไม่ได้ทดลองต้องระบุว่าไม่ผ่านการยืนยัน

## Implementation and verification

- Implemented Django authentication/admin, persistent SQLite businesses and separate public empty-state chat pages, Docker/Compose configuration, setup script and installation guide.
- Runtime choices recorded in `docs/decisions/initial-runtime.md`; no vector database choice was needed for this slice.
- Passed: five Django integration tests, including separate-process disk persistence; mypy; Django system/migration checks; pip dependency checks; actual Gunicorn/WhiteNoise HTTP smoke for login and static assets; setup secret generation and non-overwrite check.
- Parallel code-review: Standards 0 findings; Spec 0 findings. Baseline was the empty tree because the repository had no previous commits.
- [ ] Run Docker Compose build/startup, create admin interactively, verify health and restart/volume persistence in an environment with Docker. Docker is absent here; Windows/Linux installation is also unverified. This ticket is not marked fully verified or closed.
