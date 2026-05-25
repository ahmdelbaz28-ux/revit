# تحويل ملفات DWG إلى DXF

FireAI V5.1.2 يقرأ صيغة **DXF** فقط. لتحويل ملفات DWG:

---

## باستخدام AutoCAD (الأسهل)

1. افتح الملف في AutoCAD
2. File → Export → Save As
3. اختر **DXF** كصيغة الملف
4. احفظ

---

## باستخدام BricsCAD

1. File → Save As
2. اختر DXF (*.dxf)
3. Optionally: File → Save As → DXF 2010+ (recommended)

---

## باستخدام LibreDWG (مجاني - Linux)

```bash
# للتثبيت (Ubuntu/Debian)
sudo apt update
sudo apt install libredwg-tools

# للتحويل
dxf-out --file project.dwg --output project.dxf
```

**ملاحظة**: LibreDWG قد لا تكون متاحة في جميع بيئات التشغيل.

---

## باستخدام ODA File Converter (Windows مجاني)

1. حمّل من: https://www.opendesign.com/guestfiles/oda_file_converter
2. شغّل التطبيق
3. اختر DWG → DXF
4. اضغط Convert

---

## تحقق من التحويل

بعد التحويل، تأكد أن الملف يُقرأ:

```python
from parsers.dxf_parser import DXFParser

parser = DXFParser()
result = parser.parse("project.dxf")
print(f"Rooms: {result.room_count}")
```

---

## ملاحظات هامة

- **DXF 2010+** يفضل (يدعم Splines و Arcs)
- تأكد من **INSUNITS** في الملف (أو استخدم auto-detection)
- للتحويل بالجملة، استخدم Batch DXFOut script

---

*FireAI V5.1.2 - DXF only for safety-critical fire detection.*