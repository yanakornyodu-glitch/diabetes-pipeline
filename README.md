# Diabetes Risk Data Pipeline (Kaggle → PostgreSQL → Google Sheets → Data Studio)

Automated data pipeline สำหรับชุดข้อมูลสุขภาพผู้ป่วย 100,000 คน (`diabetes_dataset_with_notes.csv` จาก Kaggle)
ดึงข้อมูลลง PostgreSQL บน Docker → แปลงข้อมูลด้วย Pandas → ส่งตารางสรุปขึ้น Google Sheets → ทำ Dashboard บน Data Studio

```
Kaggle CSV ──ingest.py──▶ PostgreSQL raw_data ──transform.py──▶ PostgreSQL production ──publish.py──▶ Google Sheets ──▶ Data Studio
                                      (Docker)                                  run_pipeline.py = ทั้งหมดในคำสั่งเดียว
```

## โครงสร้างโปรเจกต์

| ไฟล์ | หน้าที่ |
|---|---|
| `docker-compose.yml` | PostgreSQL 16 บน Docker (มี volume เก็บข้อมูลถาวร) |
| `config.py` | อ่านค่าการตั้งค่าจาก `.env` และสร้าง database engine |
| `ingest.py` | อ่าน CSV → ตาราง `raw_data.diabetes_dataset_with_notes` |
| `transform.py` | Cleaning, Feature Engineering, Aggregation → schema `production` |
| `publish.py` | อ่านตารางสรุปจาก `production` → เขียนลง Google Sheets ตารางละ 1 worksheet |
| `run_pipeline.py` | เรียก ingest → transform → publish ต่อกันในคำสั่งเดียว |

## วิธีรัน

### 1. เตรียมเครื่อง
ต้องมี Python 3.10+ และ Docker Desktop (เปิดโปรแกรมไว้ก่อนรัน)

```powershell
# Windows PowerShell
git clone https://github.com/yanakornyodu-glitch/diabetes-pipeline.git
cd diabetes-pipeline
python -m pip install -r requirements.txt
copy .env.example .env
```

```bash
# macOS / Linux
git clone https://github.com/yanakornyodu-glitch/diabetes-pipeline.git && cd diabetes-pipeline
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### 2. ดาวน์โหลดข้อมูลจาก Kaggle
ดาวน์โหลด `diabetes_dataset_with_notes.csv` จากหน้า dataset บน Kaggle แล้ววางไว้ที่ `data/diabetes_dataset_with_notes.csv`
(ไฟล์ CSV ไม่ถูก commit ขึ้น Git)

### 3. เปิด PostgreSQL
```bash
docker compose up -d
docker compose ps        # รอจนสถานะเป็น healthy
```

### 4. ตั้งค่า Google API Credentials (ทำครั้งเดียว)
1. ไปที่ https://console.cloud.google.com → สร้าง Project ใหม่
2. **APIs & Services → Library** → เปิด **Google Sheets API** และ **Google Drive API**
3. **APIs & Services → Credentials → Create Credentials → Service account** → ตั้งชื่อ → Done
4. คลิก service account ที่สร้าง → แท็บ **Keys → Add key → Create new key → JSON** → ไฟล์จะถูกดาวน์โหลด
5. เปลี่ยนชื่อไฟล์เป็น `credentials.json` แล้ววางไว้ที่ root ของโปรเจกต์ (**ห้าม commit**, อยู่ใน `.gitignore` แล้ว)
6. สร้าง Google Sheet ใหม่ → กด **Share** → ใส่อีเมลของ service account (`...@...iam.gserviceaccount.com` ดูได้ใน `credentials.json` ช่อง `client_email`) → สิทธิ์ **Editor**
7. คัดลอก ID ของชีตจาก URL `https://docs.google.com/spreadsheets/d/<ID>/edit` ไปใส่ `SPREADSHEET_ID=` ในไฟล์ `.env`

### 5. รัน pipeline
```bash
python run_pipeline.py                 # ingest → transform → publish
python run_pipeline.py --skip-publish  # ทดสอบเฉพาะฝั่ง local
```
รันแต่ละขั้นแยกได้: `python ingest.py`, `python transform.py`, `python publish.py`

ตรวจผลใน PostgreSQL:
```bash
docker exec -it diabetes-postgres psql -U pipeline -d diabetes -c "\dt production.*"
```

## Transformation ที่ทำ (`transform.py`)

- **Cleaning:** ตัดช่องว่างในข้อความ, บังคับชนิดข้อมูล (ค่าผิดรูปแบบ → NaN), เติม missing (ตัวเลข = median, หมวดหมู่ = label), ตัดค่าที่เป็นไปไม่ได้, ลบแถวซ้ำ (14 แถว), เปลี่ยนชื่อคอลัมน์เป็น snake_case (`race:Asian` → `race_asian`)
- **Feature Engineering:** `race` (รวม one-hot 5 คอลัมน์เป็นคอลัมน์เดียว), `age_group`, `bmi_category` (WHO), `hba1c_band` (เกณฑ์ ADA), `glucose_band`, `smoking_group`, `comorbidity_group`, `risk_marker_count`, `is_us_state`, `diabetes_status`, `note_length`
  - `risk_marker_count` (0–6) = จำนวนข้อที่เข้าเกณฑ์: อายุ ≥ 45, BMI ≥ 30, ความดันสูง, โรคหัวใจ, HbA1c ≥ 5.7, glucose ≥ 126
- **Aggregation:** อัตราการเป็นเบาหวานแยกตามแต่ละมิติ (ดูตารางด้านล่าง)
- **Joining:** dataset นี้มีไฟล์เดียว จึงใช้การ merge ตาราง mapping ประวัติการสูบบุหรี่ (`smoking_history` → `smoking_group`) และรวมตารางย่อยของโรคร่วมด้วย concat

## ตารางใน schema `production`

| ตาราง | แถว | ใช้ตอบ | ส่งขึ้น Sheets |
|---|---|---|---|
| `patients_clean` | 99,986 | ตารางหลักระดับผู้ป่วย | ไม่ส่ง (ใหญ่และมีข้อความยาว) |
| `kpi_summary` | 1 | KPI รวม (สำรอง) | ส่ง |
| `diabetes_by_age_group` | 7 | Q1 | ส่ง |
| `diabetes_by_bmi_category` | 6 | Q2 | ส่ง |
| `diabetes_by_comorbidity` | 8 | Q3 | ส่ง |
| `diabetes_by_lab_matrix` | 12 | Q4 (heatmap) | ส่ง |
| `diabetes_by_hba1c_band`, `diabetes_by_glucose_band` | 3 / 4 | สำรอง | ส่ง |
| `lab_scatter_sample` | 5,000 | สำรอง (สุ่มกลุ่มละ 2,500 สำหรับ scatter) | ส่ง |
| `diabetes_by_smoking` | 6 | Q5 | ส่ง |
| `diabetes_by_state` | 54 | สำรอง (รายรัฐ) | ส่ง |
| `diabetes_by_demographic` | 83 | สำรอง (อายุ × เพศ × เชื้อชาติ) | ส่ง |
| `diabetes_by_risk_markers` | 7 | สำรอง (กลุ่มเป้าหมายคัดกรอง) | ส่ง |

Dashboard ใช้ 5 ตารางที่ตอบ Q1–Q5 ส่วนตาราง "สำรอง" ส่งขึ้นไปด้วยเพื่อตรวจสอบและต่อยอด
ส่งขึ้น Sheets รวมประมาณ 32,000 cells (ลิมิตของ Google Sheets คือ 10 ล้าน cells)

## Troubleshooting

| อาการ | วิธีแก้ |
|---|---|
| `connection refused` port 5432 | ยังไม่ได้ `docker compose up -d` หรือ port ชนกับ Postgres ที่ติดตั้งในเครื่อง → เปลี่ยน `POSTGRES_PORT=5433` ใน `.env` |
| `SpreadsheetNotFound` | ยังไม่ได้แชร์ชีตให้อีเมล service account หรือ `SPREADSHEET_ID` ผิด |
| `APIError 403 ... has not been used` | ยังไม่ได้เปิด Sheets API / Drive API ใน Cloud project |
| `APIError 429` | ชน quota → รอ 1 นาทีแล้วรันใหม่ (`publish.py` retry ให้อัตโนมัติแล้ว) |
| `No module named 'gspread'` (หรือ sqlalchemy) | ยังไม่ได้ติดตั้งไลบรารี → `python -m pip install -r requirements.txt` |
| `No such file or directory: 'credentials.json'` | ไฟล์ไม่ได้อยู่ในโฟลเดอร์ที่รัน หรือ Windows ตั้งชื่อเป็น `credentials.json.json` → `dir *.json*` เพื่อตรวจ |
