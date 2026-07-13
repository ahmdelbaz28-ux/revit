# 🔑 دليل مفاتيح API في BAZSPARK

هذا الدليل يشرح كيفية الحصول على مفتاح API لتسجيل الدخول، وكيفية توليد مفاتيح جديدة للمستخدمين الآخرين.

---

## 📋 المحتويات

1. [ما هو مفتاح API؟](#-ما-هو-مفتاح-api)
2. [كيف أحصل على مفتاح API لتسجيل الدخول؟](#-كيف-أحصل-على-مفتاح-api-لتسجيل-الدخول)
3. [الأدوار المتاحة (Roles)](#-الأدوار-المتاحة-roles)
4. [كيفية توليد مفاتيح جديدة للمستخدمين](#-كيفية-توليد-مفاتيح-جديدة-للمستخدمين)
5. [إدارة المفاتيح الموجودة](#-إدارة-المفاتيح-الموجودة)
6. [الأسئلة الشائعة](#-الأسئلة-الشائعة)

---

## 🤔 ما هو مفتاح API؟

في BAZSPARK، **مفتاح API** (API Key) هو:
- **اسم المستخدم وكلمة المرور معاً** — بدلاً من نظام تقليدي بالاسم/كلمة المرور
- **نص طويل** يبدأ بـ `fireai_` متبوع بـ 32 حرف عشوائي (مثل: `fireai_aB3xK9...`)
- **سري** — يُحفظ كـ hash (SHA-256 + bcrypt) ولا يمكن استرجاعه بعد التوليد
- **مرتبط بدور** (admin / engineer / viewer) يحدد صلاحيات المستخدم

### لماذا API Key بدلاً من اسم مستخدم/كلمة مرور؟

| الميزة | API Key | اسم مستخدم/كلمة مرور |
|--------|---------|---------------------|
| الأمان | عالي (32+ حرف عشوائي) | متوسط (يعتمد على المستخدم) |
| البساطة | حقل واحد | حقلين |
| البرمجة | سهل (header واحد) | معقد (tokens/sessions) |
| الإلغاء | فوري (delete key) | معقد (revoke tokens) |

---

## 🚀 كيف أحصل على مفتاح API لتسجيل الدخول؟

### الطريقة 1: اطلب المفتاح من المسؤول (Admin)

إذا كنت **مستخدم عادي**، اسأل م. أحمد الباز (المسؤول) أن يولد لك مفتاح:
1. حدد دورك المطلوب:
   - `engineer` — إذا كنت مهندس تصميم
   - `viewer` — إذا كنت مراجع فقط
2. سيُرسل لك المفتاح بصيغة: `fireai_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
3. احفظه في مكان آمن — **لا يمكن استرجاعه لاحقاً**

### الطريقة 2: إذا كنت المسؤول (Admin)

المسؤول لديه مفتاح admin رئيسي محفوظ في **HuggingFace Space secrets** تحت اسم `FIREAI_API_KEY`. لمعرفة هذا المفتاح:

1. اذهب إلى: https://huggingface.co/spaces/ahmdelbaz28/BAZSPARK/settings
2. في قسم **Variables and secrets**، ابحث عن `FIREAI_API_KEY`
3. **ملاحظة**: القيمة مخفية — إذا لم تكن تعرفها، ستحتاج إلى إعادة تعيينها (انظر أدناه)

#### إعادة تعيين مفتاح Admin (إذا فقدته)

```bash
# 1. توليد مفتاح جديد عشوائي قوي
python3 -c "import secrets; print(f'fireai_{secrets.token_urlsafe(32)}')"

# 2. انسخ الناتج (مثل: fireai_aB3xK9mZ7...)
# 3. اذهب إلى HF Space settings
# 4. حدّث FIREAI_API_KEY بالقيمة الجديدة
# 5. أعد تشغيل الـ Space (Settings → Restart Space)
```

⚠️ **تحذير**: إعادة تعيين مفتاح Admin سيُبطل جميع الجلسات الحالية.

---

## 👥 الأدوار المتاحة (Roles)

| الدور | الوصف | الصلاحيات |
|------|-------|----------|
| **admin** | مسؤول النظام | كل الصلاحيات + إدارة المفاتيح + إعداد النظام |
| **engineer** | مهندس تصميم | إنشاء/تعديل المشاريع، الحسابات، التصدير، التقارير |
| **viewer** | مراجع | عرض المشاريع والتقارير فقط (بدون تعديل) |

### أمثلة على استخدام كل دور:

- **admin**: م. أحمد الباز (المالك) — يحتاج لإدارة المستخدمين والإعدادات
- **engineer**: مهندسي التصميم في الشركة — يحتاجون لتصميم أنظمة الإنذار وحساب NFPA 72
- **viewer**: المراجعون (AHJ / الطلب) — يحتاجون لمراجعة التقارير بدون تعديل

---

## 🔧 كيفية توليد مفاتيح جديدة للمستخدمين

### المتطلبات الأساسية

1. لديك **مفتاح admin** (من الخطوات السابقة)
2. Python 3.8+ مثبت على جهازك
3. اتصال إنترنت (للوصول للـ backend على HuggingFace)

### الطريقة 1: استخدام السكربت الجاهز (موصى به)

```bash
# 1. نزل السكربت من المستودع
git clone https://github.com/ahmdelbaz28-ux/BAZspark.git
cd BAZspark

# 2. توليد مفتاح engineer لمستخدم جديد
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --role engineer \
  --description "م. محمد أحمد - قسم التصميم"

# 3. الناتج سيكون مثل:
# ✅ API Key Generated Successfully!
# 🔑 YOUR API KEY:
#    fireai_xK9mZ7pQ3aB8cD2eF4gH6iJ8kL0mN2oP4qR6sT8uV0wX2yZ4
```

### الطريقة 2: استخدام curl مباشرة

```bash
# توليد مفتاح engineer
curl -X POST "https://ahmdelbaz28-bazspark.hf.space/api/v1/admin/keys" \
  -H "X-API-Key: fireai_ADMIN_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "engineer",
    "description": "م. سارة أحمد - قسم المراجعة"
  }'

# الناتج (JSON):
# {
#   "success": true,
#   "data": {
#     "key": "fireai_xK9mZ7pQ3aB8cD2eF4gH6...",
#     "role": "engineer",
#     "description": "م. سارة أحمد - قسم المراجعة",
#     "warning": "Store this key securely. It cannot be retrieved later."
#   }
# }
```

### الطريقة 3: استخدام Python مباشرة

```python
import requests

BACKEND = "https://ahmdelbaz28-bazspark.hf.space"
ADMIN_KEY = "fireai_ADMIN_KEY_HERE"

response = requests.post(
    f"{BACKEND}/api/v1/admin/keys",
    headers={"X-API-Key": ADMIN_KEY, "Content-Type": "application/json"},
    json={
        "role": "engineer",
        "description": "م. خالد علي - تصميم"
    }
)

data = response.json()
if data["success"]:
    print(f"المفتاح الجديد: {data['data']['key']}")
    print("⚠️ احفظه الآن — لا يمكن استرجاعه لاحقاً!")
```

### أمثلة عملية

#### مثال 1: توليد 5 مفاتيح لفريق تصميم

```bash
ADMIN="fireai_ADMIN_KEY_HERE"

for i in 1 2 3 4 5; do
  python3 scripts/generate_api_key.py \
    --admin-key "$ADMIN" \
    --role engineer \
    --description "Engineer #$i - Design Team"
done
```

#### مثال 2: توليد مفتاح viewer لمراجع خارجي (AHJ)

```bash
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --role viewer \
  --description "AHJ Reviewer - Cairo Fire Department"
```

#### مثال 3: توليد مفتاح admin احتياطي

```bash
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --role admin \
  --description "Backup Admin - Emergency Access"
```

---

## 🛠️ إدارة المفاتيح الموجودة

### عرض جميع المفاتيح

```bash
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --list
```

**الناتج:**
```
📋 Listing all API keys...

  Found 5 API key(s):

  #    Role         Description                    Key Hash (first 16 chars)
  ---- ------------ ------------------------------ ------------------------
  1    admin        Default admin key (from FIREI  a1b2c3d4e5f6g7h8...
  2    engineer     م. محمد أحمد - قسم التصميم     9i8j7k6l5m4n3o2p1...
  3    engineer     م. سارة أحمد - قسم المراجعة    0z9y8x7w6v5u4t3s2...
  4    viewer       AHJ Reviewer - Cairo Fire De   1a2b3c4d5e6f7g8h9...
  5    admin        Backup Admin - Emergency Acc   i0j9k8l7m6n5o4p3q2...
```

### حذف مفتاح (إلغاء وصول مستخدم)

```bash
# انسخ الـ hash من أمر --list أعلاه
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --delete "a1b2c3d4e5f6g7h9i0j9k8l7m6n5o4p3q2r1s3t4"
```

### عرض الأدوار والصلاحيات

```bash
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --roles
```

---

## ❓ الأسئلة الشائعة

### س: نسيت مفتاحي — هل يمكنني استرجاعه؟
**ج: لا.** المفاتيح تُحفظ كـ hash فقط (للأمان). اطلب من المسؤول توليد مفتاح جديد لك، ثم احذف القديم.

### س: كم مفتاح يمكنني توليده؟
**ج: لا يوجد حد.** لكن كل مفتاح يستهلك مساحة صغيرة في ملف `db/api_keys.json`.

### س: هل تنتهي صلاحية المفاتيح؟
**ج: لا** — المفاتيح لا تنتهي تلقائياً. المسؤول فقط يمكنه حذفها.

### س: هل المفاتيح مرتبطة بجهاز معين؟
**ج: لا** — يمكن استخدام المفتاح من أي جهاز/متصفح.

### س: كيف أؤمن مفاتيحي؟
**ج:**
1. استخدم مدير كلمات مرور (1Password, Bitwarden, KeePass)
2. لا تشارك المفتاح في بريد إلكتروني غير مشفر
3. استخدم وصفاً واضحاً لكل مفتاح (اسم المستخدم/القسم)
4. احذف المفاتيح غير المستخدمة فوراً

### س: ماذا يحدث إذا تسرب مفتاح؟
**ج:** المسؤول يحذفه فوراً:
```bash
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN_KEY_HERE" \
  --delete "COMPROMISED_KEY_HASH"
```
بعد الحذف، المفتاح لا يعمل خلال ثوانٍ (يتم invalidate الكاش).

### س: هل يمكنني تغيير دور مفتاح موجود؟
**ج: نعم**، عبر API:
```bash
curl -X PUT "https://ahmdelbaz28-bazspark.hf.space/api/v1/admin/keys/KEY_HASH" \
  -H "X-API-Key: fireai_ADMIN_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"role": "engineer"}'
```

### س: الموقع يظهر "Invalid API key" — ما المشكلة؟
**ج:** أسباب محتملة:
1. المفتاح خاطئ — تأكد من نسخه كاملاً
2. المفتاح محذوف — اطلب مفتاحاً جديداً
3. المفتاح يحتوي مسافات زائدة — انسخه بدون مسافات
4. تجاوزت حد المحاولات (5 محاولات/5 دقائق) — انتظر 5 دقائق

### س: كيف أختبر أن مفتاحي يعمل؟
**ج:**
```bash
# استبدل YOUR_KEY بمفتاحك
curl -H "X-API-Key: YOUR_KEY" \
  "https://ahmdelbaz28-bazspark.hf.space/api/v1/auth/me"

# إذا كان صحيحاً، سترى:
# {"success": true, "data": {"role": "engineer", ...}}

# إذا كان خاطئاً، سترى:
# {"detail": "Invalid API key", ...}
```

---

## 🔐 الأمان

### كيف تُحفظ المفاتيح في الـ backend؟

```
المستخدم يدخل: fireai_xK9mZ7pQ3aB8cD2eF4gH6iJ8kL0mN2oP4qR6sT8uV0wX2yZ4
                          ↓
              SHA-256 HMAC lookup key (32 bytes)
                          ↓
              bcrypt hash (cost factor 12) — بطيء جداً ضد brute force
                          ↓
              يُحفظ في db/api_keys.json (hash فقط، لا plaintext)
```

### معدل المحاولات (Rate Limiting)

- **5 محاولات فاشلة** لكل IP → حظر 5 دقائق
- **100 طلب/دقيقة** لكل مفتاح صالح
- هذا يحمي من هجمات brute force

---

## 📞 الدعم

| المشكلة | التواصل |
|---------|---------|
| نسيت مفتاح admin | م. أحمد الباز — engineering@bazspark.com |
| طلب مفتاح جديد | م. أحمد الباز — engineering@bazspark.com |
| مشكلة تقنية | [GitHub Issues](https://github.com/ahmdelbaz28-ux/BAZspark/issues) |
| خطأ في النظام | [GitHub Issues](https://github.com/ahmdelbaz28-ux/BAZspark/issues) |

---

## 📝 ملخص سريع

```bash
# توليد مفتاح مهندس جديد
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN" \
  --role engineer \
  --description "اسم المهندس"

# عرض كل المفاتيح
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN" \
  --list

# حذف مفتاح
python3 scripts/generate_api_key.py \
  --admin-key "fireai_ADMIN" \
  --delete "KEY_HASH"
```

**تذكر**: المفتاح يُظهر مرة واحدة فقط عند التوليد — احفظه فوراً!
