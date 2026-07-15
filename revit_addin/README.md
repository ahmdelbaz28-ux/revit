# BazSpark Revit Bridge — Add-in للـ BAZspark

## الوظيفة
يربط هذا الـ Add-in بين خادم BAZspark السحابي ومنصة Revit على جهاز المهندس عبر **Named Pipe** آمن.
يضمن أن جميع أوامر Revit API تُنفَّذ **على Main Thread** الصحيح باستخدام `IExternalEventHandler`.

---

## متطلبات البناء

| المتطلب | الإصدار |
|---------|---------|
| Visual Studio | 2022 أو أحدث |
| .NET Framework | 4.8 |
| Revit SDK | 2022 / 2023 / 2024 / 2025 |
| Newtonsoft.Json | 13.x |

---

## خطوات البناء

```powershell
# 1. تحديد مسار Revit SDK
$env:REVIT_API_PATH = "C:\Program Files\Autodesk\Revit 2024"

# 2. بناء المشروع
cd revit_addin\BazSparkRevitBridge
dotnet restore
dotnet build -c Release

# 3. نسخ الملفات لمجلد Add-ins الخاص بـ Revit
$addinsPath = "$env:APPDATA\Autodesk\Revit\Addins\2024"
New-Item -ItemType Directory -Force -Path $addinsPath
Copy-Item "bin\Release\BazSparkRevitBridge.dll" $addinsPath
Copy-Item "bin\Release\Newtonsoft.Json.dll"     $addinsPath
Copy-Item "BazSparkRevitBridge.addin"           $addinsPath
```

---

## خطوات التشغيل

1. **بناء وتثبيت** الـ Add-in بالخطوات أعلاه
2. **فتح Revit** — ستظهر رسالة تأكيد "BAZspark Bridge started"
3. **تشغيل Local Agent** على نفس الجهاز:
   ```bash
   python scripts/local_agent.py --revit-mode named_pipe
   ```
4. الآن يمكن لـ BAZspark السحابي إرسال أوامر Revit حقيقية عبر:
   - السحابة → WebSocket → Local Agent → Named Pipe → C# Add-in → Revit API

---

## بروتوكول الاتصال

كل أمر هو JSON يُرسَل على Named Pipe `\\.\pipe\bazspark_revit`:

```json
{
  "command_id": "uuid-v4",
  "action": "create_wall",
  "params": {
    "x1": 0, "y1": 0,
    "x2": 5000, "y2": 0,
    "height": 3000
  }
}
```

**الرد:**
```json
{
  "success": true,
  "data": { "id": 123456, "length_mm": 5000.0 }
}
```

---

## الأوامر المدعومة

| `action` | الوصف | `params` الأساسية |
|----------|--------|------------------|
| `get_info` | معلومات الملف الحالي | — |
| `list_elements` | قائمة العناصر | `category` (اختياري) |
| `create_wall` | إنشاء جدار | `x1,y1,x2,y2,height` (mm) |
| `create_floor` | إنشاء بلاطة | `points: [[x,y],...]` (mm) |
| `place_family_instance` | وضع عنصر (باب/نافذة) | `family, x, y` (mm) |
| `delete_element` | حذف عنصر | `id` |
| `get_parameter` | قراءة معامل | `id, name` |
| `set_parameter` | تعديل معامل | `id, name, value` |
| `list_views` | قائمة الـ Views | — |
| `save` | حفظ المستند | — |

---

## الأمان

- الـ Pipe محلي فقط (`\\.\\pipe\\`) — لا يمكن الوصول إليه من الشبكة
- يتحقق Local Agent من صحة الـ API Key قبل أي أمر
- جميع المعاملات (Transactions) محمية داخل try/catch مع rollback تلقائي

