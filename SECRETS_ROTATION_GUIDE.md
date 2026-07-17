# 🔐 BAZSPARK Secrets Rotation Guide
**خطورة:** عالية  
**الهدف:** تمرير جميع الأسرار الحساسة المستخدمة في المشروع  
**تاريخ:** 2026-07-17

## ⚠️ تنبيه أمني عاجل

**يجب تدوير جميع الأسرار المذكورة أدناه فوراً** لأنها تمت مشاركتها في قنوات الاتصال ولا يمكن ضمان سريتها.

---

## 📋 قائمة الأسرار للتدوير

### 1. 🔥 Firebase / FireAI
- `FIREAI_API_KEY`
- `FIREAI_SESSION_SECRET`

**الإجراء:**
```bash
# توليد سر جديد للجلسة
python3 -m backend.session_secret generate

# أو استخدام OpenSSL
openssl rand -hex 64
```

### 2. 🗄️ Supabase (❌ حالياً غير صالح - يجب إنشاء مشروع جديد)
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

**الإجراء:**
1. اذهب إلى [Supabase Dashboard](https://app.supabase.com)
2. أنشئ مشروع جديد
3. انسخ Project URL و anon/public key و service_role key
4. حدث `.env` و `vercel.json` و `render.yaml`

### 3. 🧠 Langfuse
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

**الإجراء:**
1. اذهب إلى [Langfuse Cloud](https://cloud.langfuse.com)
2. Settings → API Keys → Generate new key pair
3. احذف المفاتيح القديمة بعد تحديث الكود

### 4. 🤖 NVIDIA API
- `NVIDIA_API_KEY`

**الإجراء:**
1. اذهب إلى [NVIDIA API Catalog](https://build.nvidia.com)
2. Generate new API key
3. حدث `.env`

### 5. 📧 Resend (Email Service)
- `RESEND_API_KEY`

**الإجراء:**
1. اذهب إلى [Resend Dashboard](https://resend.com)
2. API Keys → Create new key
3. احذف المفتاح القديم

### 6. 📦 Box Integration
- `BOX_CLIENT_ID`
- `BOX_CLIENT_SECRET`
- `BOX_DEVELOPER_TOKEN`

**الإجراء:**
1. اذهب إلى [Box Developer Console](https://developer.box.com)
2. أنشئ تطبيق جديد
3. أعد تعيين Developer Token
4. حدث `.env`

### 7. ▲ Vercel
- `VERCEL_DEPLOY_TOKEN`
- `VERCEL_PROJECT_ID`
- `VERCEL_TEAM_ID`

**الإجراء:**
1. اذهب إلى [Vercel Dashboard](https://vercel.com/account/tokens)
2. Create new token
3. احذف التوكن القديم

### 8. 🤗 Hugging Face
- `HF_TOKEN`

**الإجراء:**
1. اذهب إلى [Hugging Face Settings](https://huggingface.co/settings/tokens)
2. Create new token
3. احذف التوكن القديم

### 9. ⚡ Daytona
- `DAYTONA_API_TOKEN`

**الإجراء:**
1. اذهب إلى Daytona Dashboard
2. Generate new API token
3. احذف التوكن القديم

### 10. 📋 Codesandbox VPS
- `CODESANDBOX_TOKEN`

**الإجراء:**
1. اذهب إلى Codesandbox settings
2. Regenerate API token
3. حدث `.env`

### 11. ☁️ Cloudflare (3 tokens)
- `CLOUDFLARE_USER_TOKEN_1`
- `CLOUDFLARE_USER_TOKEN_2`
- `CLOUDFLARE_USER_TOKEN_3`

**الإجراء:**
1. اذهب إلى [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. لكل توكن: Create Token → اختر قالب مخصص → احذف القديم بعد التحديث

### 12. 🐙 GitHub
- `GH_PAT` (Personal Access Token)

**الإجراء:**
1. اذهب إلى [GitHub Settings](https://github.com/settings/tokens)
2. Generate new token
3. احذف التوكن القديم

### 13. 🗄️ Neon PostgreSQL
- `NEON_DATABASE_URL`

**الإجراء:**
1. اذهب إلى [Neon Dashboard](https://console.neon.tech)
2. اختر المشروع → Connection string → Copy new connection string
3. حدث `.env`

---

## 🔄 إجراءات التدوير الفوري

### الخطوة 1: إنشاء بيئة آمنة للعمل
```bash
# إنشاء نسخة احتياطية من .env الحالي
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)

# تغيير صلاحيات الملف
chmod 600 .env.backup.*
```

### الخطوة 2: تحديث .env بالقيم الجديدة
```bash
# بعد توليد جميع الأسرار الجديدة، حدث .env
# ثم احذف الملفات الاحتياطية بعد التحقق
rm .env.backup.*
```

### الخطوة 3: تحديث بيئات الإنتاج
```bash
# Vercel
vercel env add FIREAI_API_KEY production
vercel env add SUPABASE_URL production
# كرر لجميع المتغيرات

# Render
# اذهب إلى Render Dashboard → Environment → Update variables

# Hugging Face Spaces
# Settings → Variables and secrets → Update all secrets
```

### الخطوة 4: التحقق من عدم تسريب الأسرار
```bash
# تأكد من أن .env في .gitignore
grep "^\.env$" .gitignore

# تحقق من عدم وجود أسرار في السجل
git log --all --pretty=format:"%H %s" --grep="password\|secret\|token\|key" | head -20

# البحث عن أسرار محتملة في الكود
git grep -E "(api_key|secret|token|password|private_key)\s*[:=]" | grep -v ".py:" | head -20
```

### الخطوة 5: تعديل بسيط في .gitignore (إضافة)
```gitignore
# إضافة هذه الأسطر إلى .gitignore
.env.backup.*
*.secret
secrets/
config/secrets.json
```

<task_progress>
- [x] قراءة ملف .env لفهم الإعدادات الحالية
- [x] التأكد من تجاهل .env في .gitignore
- [x] إنشاء .env.example مع قوالب آمنة
- [x] التحقق من عدم وجود أسرار مكتوبة ثابتاً في الكود
- [x] إنشاء SECRETS_ROTATION_GUIDE.md
- [ ] تحديث .gitignore لقبول الأنماط الجديدة
- [ ] تحديث PRODUCTION_DEPLOYMENT_GUIDE.md
- [ ] إنشاء POLICY.md للأمان
- [ ] دفع آمن للتغييرات
</task_progress>
</write_to_file>