"""Build REPORT.pdf from REPORT.md (Markdown -> HTML -> PDF via headless Chrome/Edge).

Usage:  python build_report.py
Needs:  pip install markdown  + Google Chrome or Microsoft Edge installed.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "REPORT.md"
HTML_OUT = ROOT / "build" / "REPORT.html"
PDF_OUT = ROOT / "REPORT.pdf"

ARCH = """

<figure class="arch">
<div class="vflow">
  <div class="node"><b>1 · Source: Kaggle</b><span><code>diabetes_dataset_with_notes.csv</code> · 100,000 แถว × 17 คอลัมน์</span></div>
  <div class="step">▼ <b>ingest.py</b> — pandas + SQLAlchemy</div>
  <div class="node db"><b>2 · Data Warehouse: PostgreSQL 16 (Docker)</b>
    <div class="schemas">
      <div class="schema">schema raw_data<small>diabetes_dataset_with_notes<br>ข้อมูลดิบตามต้นฉบับ</small></div>
      <div class="hstep"><b>transform.py</b><br>pandas ▶</div>
      <div class="schema">schema production<small>patients_clean<br>+ 12 ตารางสรุป</small></div>
    </div>
  </div>
  <div class="step">▼ <b>publish.py</b> — gspread + gspread-dataframe · ส่งเฉพาะตารางสรุป ~32,000 cells</div>
  <div class="schemas">
    <div class="node"><b>3 · Google Sheets</b><span>1 ตาราง = 1 worksheet</span></div>
    <div class="hstep"><b>connector</b><br>▶</div>
    <div class="node"><b>4 · Data Studio</b><span>Dashboard เชิงโต้ตอบ</span></div>
  </div>
</div>
<div class="runall"><code>python run_pipeline.py</code> = ingest → transform → publish ในคำสั่งเดียว</div>
<figcaption>รูปที่ 1 สถาปัตยกรรมข้อมูลของโปรเจกต์</figcaption>
</figure>

"""

CSS = """
@page { size: A4; margin: 20mm 18mm 20mm 18mm;
  @bottom-center { content: counter(page); font: 10pt 'Leelawadee UI','Sarabun',sans-serif; color:#52514e; } }
@page :first { @bottom-center { content: none; } }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: 'Leelawadee UI','Sarabun','Tahoma',sans-serif; font-size: 12.5pt; line-height: 1.6;
  color: #1b1b1a; background: #fff; margin: 0; }
code { font-family: Consolas,'Courier New',monospace; font-size: .86em; background: #f1f0ed;
  padding: .05em .3em; border-radius: 3px; }
pre { background: #f6f5f2; border: 1px solid #e2e0da; border-radius: 6px; padding: 10px 14px;
  font-size: 10pt; line-height: 1.45; overflow: hidden; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
h1 { display: none; }
h2 { font-size: 18pt; color: #104281; margin: 1.4em 0 .5em; padding-bottom: .2em;
  border-bottom: 2px solid #2a78d6; break-after: avoid; }
h2.newpage { break-before: page; margin-top: 0; padding-top: 6px; }
h3 { font-size: 14pt; color: #1c5cab; margin: 1.2em 0 .4em; break-after: avoid; }
p { margin: .4em 0; padding-top: 3px; }
p:has(+ ul), p:has(+ table) { break-after: avoid; }
ul, ol { margin: .3em 0 .6em; padding-left: 1.4em; }
li { margin: .1em 0; padding-top: 3px; }
strong { color: #0b0b0b; }
table { width: 100%; border-collapse: collapse; margin: .6em 0 1em; font-size: 10.5pt; line-height: 1.45; }
th { background: #104281; color: #fff; text-align: left; padding: 6px 8px; font-weight: 600; }
td { padding: 5px 8px; border-bottom: 1px solid #e2e0da; vertical-align: top; }
tr:nth-child(even) td { background: #f7f9fc; }
tr { break-inside: avoid; }
blockquote { margin: .6em 0; padding: 6px 14px; border-left: 4px solid #86b6ef; background: #f2f7fd; color: #33322f; }
hr { display: none; }
a { color: #1c5cab; text-decoration: none; }
.todo { background: #fff1b8; padding: 0 .25em; border-radius: 3px; }

/* cover */
.cover { height: 255mm; display: flex; flex-direction: column; justify-content: center; break-after: page; }
.cover .kicker { color: #2a78d6; font-weight: 600; letter-spacing: .04em; font-size: 12pt; }
.cover .title { font-size: 28pt; line-height: 1.3; font-weight: 700; color: #0d366b; margin: 10px 0 6px; }
.cover .sub { font-size: 15pt; color: #52514e; margin-bottom: 34px; }
.cover .bar { width: 80px; height: 5px; background: #2a78d6; border-radius: 3px; margin-bottom: 30px; }
.cover table { width: auto; font-size: 12.5pt; }
.cover td { border: none; background: none !important; padding: 3px 18px 3px 0; }
.cover td:first-child { color: #52514e; white-space: nowrap; }
.cover .stack { margin-top: 40px; font-size: 11pt; color: #52514e; }

/* contents */
.toc { break-after: page; }
.toc ol { font-size: 13pt; line-height: 2; }
.toc .map td:first-child { white-space: nowrap; }

/* figures */
figure { margin: 1em 0 1.2em; break-inside: avoid; }
figcaption { font-size: 10.5pt; color: #52514e; margin-bottom: 6px; font-weight: 600; }
.arch figcaption { text-align: center; margin: 8px 0 0; }
.chart { border: 1px solid #e2e0da; border-radius: 8px; padding: 10px 14px 8px; background: #fcfcfb; }
.chart .lbl { font: 12.5px 'Leelawadee UI','Sarabun',sans-serif; fill: #33322f; }
.chart .val { font: 600 12.5px 'Leelawadee UI','Sarabun',sans-serif; fill: #0b0b0b; }
.chart .axis { stroke: #8a8984; stroke-width: 1; }
.shot { text-align: center; margin: .8em 0 1.2em; }
.shot img { max-width: 100%; max-height: 80mm; border: 1px solid #e2e0da; border-radius: 6px; }
.shot figcaption { margin: 6px 0 0; font-weight: 600; }
.fig-note { font-size: 9pt; color: #6b6a66; margin-top: 2px; }
.vflow { width: 78%; margin: 0 auto; }
.node { border: 1.5px solid #2a78d6; border-radius: 8px; padding: 7px 10px; text-align: center;
  font-size: 10pt; line-height: 1.4; background: #f2f7fd; flex: 1 1 0; }
.node b { display: block; color: #0d366b; font-size: 10.5pt; }
.node span { display: block; color: #52514e; }
.node.db { background: #fff; }
.schemas { display: flex; align-items: center; gap: 8px; margin-top: 5px; }
.schema { flex: 1 1 0; border: 1px solid #86b6ef; border-radius: 6px; background: #f2f7fd; padding: 5px;
  font-weight: 600; color: #1c5cab; font-size: 10pt; }
.schema small { display: block; font-weight: 400; color: #52514e; font-size: 9pt; }
.hstep { flex: 0 0 auto; font-size: 9pt; color: #1c5cab; text-align: center; line-height: 1.3; }
.step { text-align: center; font-size: 9.5pt; color: #33322f; padding: 5px 0; }
.step b { color: #1c5cab; }
.runall { text-align: center; margin-top: 10px; font-size: 10.5pt; }
"""


def cover(meta: dict) -> str:
    return f"""
<section class="cover">
  <div class="kicker">PROJECT REPORT · KAGGLE DATA EDITION</div>
  <div class="title">Automated Data Pipeline<br>วิเคราะห์ปัจจัยเสี่ยงโรคเบาหวาน</div>
  <div class="sub">Kaggle → PostgreSQL (Docker) → Pandas → Google Sheets → Data Studio</div>
  <div class="bar"></div>
  <table>
    <tr><td>สมาชิกกลุ่ม</td><td>{meta['members']}</td></tr>
    <tr><td>ชุดข้อมูล</td><td><code>diabetes_dataset_with_notes.csv</code> (100,000 แถว)</td></tr>
    <tr><td>GitHub</td><td>{meta['github']}</td></tr>
    <tr><td>Data Studio</td><td>{meta['studio']}</td></tr>
    <tr><td>วันนำเสนอ</td><td>21 พฤศจิกายน 2569</td></tr>
  </table>
</section>
<section class="toc">
  <h2 style="margin-top:0">สารบัญ</h2>
  <ol>
    <li>ที่มาและความสนใจ</li><li>สถาปัตยกรรมข้อมูล</li><li>เครื่องมือที่ใช้และขั้นตอนการทำงาน</li>
    <li>การตั้งค่า Google API Credentials</li><li>คำถามทางธุรกิจและ Dashboard</li><li>Insight ที่ค้นพบ</li>
    <li>ข้อจำกัดของข้อมูลและการวิเคราะห์</li><li>สรุป</li><li>ลิงก์ส่งงาน</li>
  </ol>
  <h3>หัวข้อตามที่โจทย์กำหนด</h3>
  <table class="map">
    <tr><th>หัวข้อที่ต้องมีในรายงาน</th><th>อยู่ในบทที่</th></tr>
    <tr><td>อธิบายปัญหา/ความสนใจ (ที่มาของชุดข้อมูล Kaggle)</td><td>1</td></tr>
    <tr><td>สถาปัตยกรรมข้อมูลที่ออกแบบ</td><td>2</td></tr>
    <tr><td>เครื่องมือที่ใช้ และขั้นตอนการทำงานอย่างละเอียด</td><td>3</td></tr>
    <tr><td>ขั้นตอนการตั้งค่า Google API Credentials</td><td>4</td></tr>
    <tr><td>คำถามทางธุรกิจที่ตั้งไว้ และ Insight ที่ค้นพบจาก Dashboard</td><td>5, 6</td></tr>
  </table>
</section>
"""


def build_html() -> str:
    md = SRC.read_text(encoding="utf-8")

    # header blockquote -> cover page data
    m = re.search(r"\*\*สมาชิก:\*\*\s*(.+?)\s*·", md)
    members = ", ".join(re.findall(r"\[([^\]]+)\]", m.group(1))) if m else ""
    g = re.search(r"\*\*GitHub:\*\*\s*(\S+)", md)
    s = re.search(r"\*\*Data Studio Report:\*\*\s*(.+?)\s*·", md)
    meta = {
        "members": "<br>".join(x.strip() for x in members.split(",")),
        "github": g.group(1) if g else "",
        "studio": s.group(1) if s else "",
    }
    md = re.sub(r"\A# .*?\n---\n", "", md, flags=re.S)  # drop title + header block

    # ASCII architecture diagram -> HTML diagram
    md = re.sub(r"```\n┌.*?```", lambda _: ARCH, md, count=1, flags=re.S)

    # Python-Markdown needs a blank line before a list; also give "→" conclusions their own paragraph
    out = []
    for line in md.split("\n"):
        prev = out[-1] if out else ""
        starts_list = re.match(r"\s*([-*]|\d+\.)\s", line) and not re.match(r"\s*([-*]|\d+\.)\s", prev)
        if prev.strip() and not prev.lstrip().startswith(("|", "<", "```")) and \
                (starts_list or line.startswith("→")):
            out.append("")
        out.append(line)
    md = "\n".join(out)

    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    body = re.sub(r"https?://[^\s<]+", lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', body) \
        if "<a " not in body else body
    fig_no = iter(range(2, 100))
    body = re.sub(r'<p><img alt="([^"]*)" src="([^"]+)" ?/?></p>',
                  lambda m: f'<figure class="shot"><img src="{m.group(2)}" alt="{m.group(1)}">'
                            f'<figcaption>รูปที่ {next(fig_no)} {m.group(1)}</figcaption></figure>', body)
    # start major sections on a new page
    for n in ("2", "3", "5", "6"):
        body = body.replace(f"<h2>{n}. ", f'<h2 class="newpage">{n}. ', 1)

    cov = cover(meta)
    html = f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<base href="{ROOT.as_uri()}/">
<title>รายงานโปรเจกต์ Diabetes Data Pipeline</title>
<style>{CSS}</style></head><body>{cov}{body}</body></html>"""
    # highlight unfilled placeholders like [ใส่ลิงก์ ...]
    html = re.sub(r"\[(ใส่ลิงก์[^\]]*)\]", r'<span class="todo">[\1]</span>', html)
    return html


def find_browser() -> str:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("ไม่พบ Chrome/Edge สำหรับแปลงเป็น PDF")


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    HTML_OUT.parent.mkdir(exist_ok=True)
    HTML_OUT.write_text(build_html(), encoding="utf-8")
    tmp_pdf = HTML_OUT.with_suffix(".pdf")
    tmp_pdf.unlink(missing_ok=True)
    subprocess.run([
        find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--virtual-time-budget=15000", f"--print-to-pdf={tmp_pdf}", HTML_OUT.as_uri(),
    ], check=True)
    if not tmp_pdf.exists():
        sys.exit("Chrome/Edge ไม่ได้สร้างไฟล์ PDF")
    try:
        tmp_pdf.replace(PDF_OUT)
    except PermissionError:
        sys.exit(f"เขียนทับ {PDF_OUT.name} ไม่ได้ (ไฟล์เปิดค้างอยู่ในโปรแกรมอื่น) ปิดไฟล์แล้วรันใหม่ "
                 f"หรือใช้ไฟล์ที่ {tmp_pdf}")
    print(f"Wrote {PDF_OUT}")


if __name__ == "__main__":
    main()
