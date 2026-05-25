# Elite Drawing Analyzer  (EDA)

نظام تحليل رسومات هندسية مبني على نواة برمجية صارمة — مش تخمين.
الهدف: قراءة أي ملف تصميم (DWG/DXF/PDF/IFC/صورة)، استخراج كل عنصر فيه،
تصنيفه (كاميرا، حساس دخان، رشاش، كابل، ماسورة، …)،
ومقارنة الحصر بالمرسوم، والتحقق من المسافات والمسارات وفق أكواد السلامة.

> ⚠️ **تنبيه سلامة**: النظام **لا يحل محل** المهندس المرخّص. كل finding بحالة
> `critical` أو `major` لازم تتم مراجعته يدوياً قبل التنفيذ. الكود مبني
> ليُظهر أين النظام **غير متأكد** بدلاً من تقديم إجابة كاذبة بثقة.

---

## المعمار

```
elite_drawing_analyzer/
├── core/
│   ├── ingest.py         # DXF / DWG / PDF / IFC / Image → نموذج موحّد
│   ├── vectorize.py      # ترميم الخطوط المقطعة/الباهتة من الصور
│   └── ocr.py            # OCR للجداول والـ legends
├── intelligence/
│   ├── knowledge_base.py # SQLite — كل ما يعرفه النظام
│   └── classifier.py     # تصنيف الرموز (3 طبقات + تعلّم)
├── reasoning/
│   ├── spatial.py        # مسافات وتغطية و LOS
│   ├── compliance.py     # تطبيق أكواد NFPA/IBC على المرسوم
│   └── schedule_match.py # الحصر vs الرسم
├── pipeline.py           # السلسلة الكاملة
└── cli.py
```

## التشغيل السريع

```bash
# 1) المتطلبات
pip install ezdxf pymupdf opencv-python pytesseract ifcopenshell numpy
# (اختياري) ODA File Converter لقراءة DWG مباشرة

# 2) تحليل ملف
python -m elite_drawing_analyzer.cli analyze drawing.pdf --json report.json

# 3) مقارنة بالحصر
echo '[{"item":"smoke detector","qty":24},{"item":"sprinkler","qty":40}]' > boq.json
python -m elite_drawing_analyzer.cli analyze plan.dxf --schedule boq.json

# 4) تعليم النظام رمز جديد
python -m elite_drawing_analyzer.cli teach crops/my_camera.png camera_dome

# 5) إحصائيات قاعدة المعرفة
python -m elite_drawing_analyzer.cli stats
```

## استخدام برمجي

```python
from elite_drawing_analyzer.pipeline import analyze_file
from elite_drawing_analyzer.intelligence.knowledge_base import KnowledgeBase

kb = KnowledgeBase()
report = analyze_file("project.dwg", kb=kb,
                     schedule=[{"item":"sprinkler","qty":40}])
report.print_summary()
report.save_json("report.json")
```

## كيف يتعلم النظام

1. كل تصنيف يُسجَّل في جدول `decisions` مع confidence.
2. لما المستخدم يصحّح: `kb.confirm(decision_id, correct=False, correction="camera_dome")`
3. الـ `teach()` بيضيف crop مع label إلى `symbol_examples` كـ embedding.
4. المرة الجاية، الـ classifier يستخدم الـ k-NN على كل الأمثلة المتراكمة.
5. كل ما زادت الأمثلة، زادت الدقة. النظام **ينمو** مع كل ملف.

## قواعد السلامة المُضمّنة (نقطة بداية — راجع كود مشروعك)

| الكود     | القاعدة                            | القيمة         |
|-----------|------------------------------------|----------------|
| NFPA 72   | smoke_detector max spacing         | 9.1 m          |
| NFPA 72   | heat_detector max spacing          | 7.0 m          |
| NFPA 72   | manual pull travel distance        | 60 m           |
| NFPA 13   | sprinkler light hazard spacing     | 4.6 m          |
| NFPA 13   | max area per sprinkler             | 20.9 m²        |
| NFPA 101  | exit max travel (sprinklered)      | 61 m           |
| NEC       | panel front clearance              | 0.9 m          |
| MEP       | cable from hot pipe                | 0.3 m          |

كلها قابلة للتعديل من قاعدة البيانات: `kb.set_rule(...)`.

## حدود معروفة (الصدق أهم من الادعاء)

- DWG يحتاج ODA File Converter (مجاني) لتحويله DXF أولاً.
- OCR العربي يحتاج تثبيت بيانات tesseract العربية: `apt install tesseract-ocr-ara`.
- التصنيف بـ HOG embeddings باعتدال — لدقة أعلى استخدم CLIP/DINO
  (الـ Embedder interface مفتوحة للتبديل).
- الـ pipeline الحالي لا يستنتج "غرفة" من plan تلقائياً (يحتاج room segmentation).
- المسافات في الـ raster تعتمد على معايرة (scale) — لازم تتحدد للمشروع.

## مسار التطوير المقترح

1. **CLIP / DINO embedder** بدل HOG → قفزة كبيرة في دقة التصنيف.
2. **Room segmentation** بـ U-Net على plans → تطبيق قواعد الكود لكل غرفة.
3. **Graph-based egress routing** بدل LOS التقريبي.
4. **MEP clash detection** ثلاثي الأبعاد لما يوجد IFC.
5. **Web UI** يعرض الـ findings فوق الـ drawing مع buttons للتصحيح
   (يغذّي حلقة التعلم تلقائياً).
