# Canonicalization Functor Layer (CFL) v2.1

## 0. المبدأ السيادي
There is only one semantic truth space; all other CAD systems are projections into it, not peers of it.

Revit = Canonical BIM Ontology (Authority Anchor).
All other CAD = Projection Spaces only.

## 1. هيكل الطبقات الثلاث (Three-Layer Architecture)

### Layer 1: Parsing Layer (Syntactic Ingestion)
- يستقبل بيانات خام من أي CAD (AutoCAD, Rhino, ArchiCAD)
- يستخرج إحداثيات، طبقات، بلوكات
- لا يقوم بأي تفسير دلالي
- Output: RawGeometricFragments

### Layer 2: Interpretation Layer (Semantic Hypothesis Generation)
- يحاول matching مع الأنطولوجيا المعتمدة
- يستخدم probabilistic ontology alignment
- يولد فرضيات دلالية مع درجة ثقة (Confidence Score 0-100%)
- Output: CandidateSemanticFragments + ConfidenceScore

### Layer 3: Canonicalization Layer (Truth Fixation)
- يطبق Π_cad على CandidateSemanticFragments
- يرفض، يقبل، أو يعزل
- Output: CanonicalFragment أو QuarantineRecord

## 2. مقياس الفقد الدلالي الهيكلي (Structured Loss Vector)

SLM ليس رقماً واحداً، بل متجه خسارة هيكلي (Structured Loss Vector):

| البعد | المعنى |
|-------|--------|
| unrecognized_ratio | نسبة العناصر غير المعترف بها في الأنطولوجيا |
| safety_critical_loss | هل هناك عنصر Safety-Critical مفقود أو مشوه؟ (bool) |
| topology_ambiguity | درجة الغموض في العلاقات الطوبولوجية (0-1) |
| semantic_distance | المسافة الدلالية عن أقرب عقدة في Canonical Ontology Graph |

## 2.1 نطاقات الفقد السياقية (Contextual Loss Bands - CLB)

| Band | الشرط | الإجراء |
|------|-------|---------|
| L0: Fully Canonical | safety_critical_loss = false ∧ semantic_distance < threshold | ✅ ACCEPT |
| L1: Canonical Under Local Repair | safety_critical_loss = false ∧ semantic_distance ∈ [threshold, 2×threshold] | ⚠️ QUARANTINE |
| L2: Ambiguous (Safety-Critical) | safety_critical_loss = true ∨ topology_ambiguity > limit | 🔴 REJECT |
| L3: Non-Canonical | unrecognized_ratio > 30% | 🔴 REJECT |

**مبدأ حاسم:** إذا كان safety_critical_loss = true، النظام يرفض فوراً بغض النظر عن أي نسبة أخرى. لا يوجد "رقم" يمكنه التغاضي عن سلامة الأرواح.

لا يوجد "اجتهاد" في السلامة. Quarantine تعني: لا يُصدر إثبات حتى يراجع بشري.

## 3. دالة الإسقاط (Π_cad)
Π_cad: CAD_Geometry → (CandidateSet, LossVector, FailureMode)
- تعيد LossVector بدلاً من None مباشرة
- FailureMode يصف سبب الفشل (إن وجد) لضمان explainability
- لا تعيد None أبداً؛ تعيد دائماً تشخيصاً قابلاً للتدقيق

## 4. الأنطولوجيا كمخطط بياني (Typed Ontology Graph)
- Nodes: Canonical Entities (SmokeDetector, HeatDetector, ManualCallPoint, FireDoor, SolidWall, MerkleZone)
- Edges: Allowed Semantic Transformations (e.g., "translates_to", "blocks_path_of")
- Mapping: Functorial alignment بين الـ CAD geometry والـ Canonical Graph

لا يُستخدم قاموس ثابت (Static Dictionary)، بل Ontology Graph يمكن تمديده عبر إضافة Nodes/Edges جديدة بموجب Governance Process.

## 5. قواعد التحويل الحتمي (Canonical Serialization)
- جميع الإحداثيات تُقرب إلى 6 خانات عشرية
- المصفوفات تُفرز أبجدياً قبل الهاش
- أي عنصر بدون دلالة كاملة يُسجل في SLM
- Quarantine records تُوقع بختم SHA256 أيضاً

## 6. التوافق مع المعمارية المجمدة
- CFL يعمل كطبقة وسيطة بين المصادر غير البيمية (AutoCAD) و SEL/GEL
- لا يعدل SEL أو GEL
- لا يغير الأنطولوجيا الأساسية (Revit/BIM)
- يلتزم بالـ Architecture Freeze