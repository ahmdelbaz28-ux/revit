# Noise Ontology Contract (NOC) v1.0
## Governed Classification of Uncertainty in Regulatory CAD Systems

## 0. المبدأ الدستوري
Noise is not discovered; it is declared. Every classification of a geometric, semantic, or topological anomaly as "noise" is a semantic decision with regulatory consequences. This contract ensures that the system's noise filters do not silently evolve into a source of false rejection or, worse, a tool for intentional exclusion of valid design intent.

## 1. حوكمة تصنيف الضوضاء (Noise Classification Governance)
لا يمكن لمرشح الضوضاء في SFM-CIL أن يعمل بقواعد ارتجالية. جميع قواعد التصنيف تُعرّف في هذا العقد وتُجمّد. أي تعديل عليها هو تعديل على "أنطولوجيا الضوضاء" ويحتاج إلى دورة حوكمة كاملة.

**الأنواع الثلاثة المحكومة:**
- **Geometric Noise:** يُعرّف حصريًا على أنه انحراف رقمي أقل من 6 خانات عشرية. أي شيء أكبر هو "خطأ في التصميم" وليس "ضوضاء".
- **Semantic Noise:** يُعرّف حصريًا على أنه عنصر لا يطابق أي عقدة في Typed Ontology Graph. العقدة "غير المعترف بها" لا تُصنف كضوضاء بل كـ "عنصر غير معترف به" وتُرسل إلى Quarantine.
- **Topological Noise:** يُعرّف حصريًا على أنه علاقة طوبولوجية لا يمكن إثبات صحتها ضمن admissible region A ⊂ M. لا يُعاد تصنيفها تلقائيًا.

## 2. بروتوكول الحفاظ على قصد التصميم (Design Intent Preservation Protocol)
قبل أن يُصنف أي عنصر على أنه "ضوضاء"، يجب أن يثبت النظام أنه:
1. حاول جميع مسارات المطابقة الدلالية الممكنة في Typed Ontology Graph.
2. فشل في تحقيق الحد الأدنى من Confidence Score.
3. أصدر Quarantine Record موثقًا يصف سبب الفشل.

لا يجوز لعنصر أن يختفي من النظام صامتًا. "الضوضاء" التي لم تُسجل في Quarantine هي ثغرة في الحوكمة.

## 3. تطور المرشح القابل للتدقيق (Auditable Filter Evolution)
أي إضافة قاعدة جديدة لتصنيف الضوضاء تُعتبر "تحديثًا لأنطولوجيا الضوضاء" ويجب أن تُرفق بـ:
1. Proof of Semantic Continuity (PSC) لإثبات أن القاعدة الجديدة لا تكسر توافق الإثباتات القديمة.
2. Compatibility Break Register (CBR) إذا تسببت في رفض عناصر كانت مقبولة سابقًا.

لا يُسمح بكسر التوافق الصامت أبدًا.

## 4. الخلاصة
يحول هذا العقد "تصنيف الضوضاء" من عملية تقنية إلى عملية حوكمة دلالية. النظام لم يعد يرفض "الضوضاء" لأنه لا يفهمها، بل يُقر بأنه لا يفهمها ويُخضع هذا الإقرار للمراجعة والتدقيق.