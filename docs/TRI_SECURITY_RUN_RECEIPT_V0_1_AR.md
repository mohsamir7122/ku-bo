# عقد إيصال التشغيل وربط المرحلة للدفعة الثلاثية v0.1

## الغرض والنطاق

يضيف `KU-BO-010` جذر ثقة تشغيليًا مستقلًا لمساحة العمل التي جهزها
`KU-BO-009`. العقد يثبت أن تشغيلًا محددًا يشير إلى **الخطة نفسها، وإعداد
النطاق نفسه، والدفعة نفسها، والأسهم الثلاثة نفسها، والنافذة نفسها**. كما
يمكنه ربط شجرة مخرجات مرحلة كاملة بذلك التشغيل.

هذا عقد مصادقة وربط فقط. لا يجمع بيانات سوق، ولا يحول الهوية المرشحة إلى
هوية رسمية، ولا يمرر أي بوابة تأهيل، ولا يجيز الدفعة التالية، ولا يثبت
Backtest أوForecast أوAccuracy أوProbability أوRecommendation.

## جذرا الثقة المستقلان

يستخدم العقد مفتاحين مستقلين كليًا:

- مفتاح Run Receipt في `KUBO_TRI_RUN_HMAC_KEY` ومعرّفه في
  `KUBO_TRI_RUN_HMAC_KEY_ID`.
- مفتاح Stage Binding في `KUBO_TRI_STAGE_HMAC_KEY` ومعرّفه في
  `KUBO_TRI_STAGE_HMAC_KEY_ID`.

كل مفتاح يُمرر وقت التشغيل فقط بصيغة `hex:` أو`base64:` ويجب أن يفك إلى
32 بايت على الأقل. لا يُقبل تطابق المفتاحين أوتطابق معرّفيهما. لا تدخل
المفاتيح في CLI arguments أوJSON أوGit، ولا تعرض CLI قيمة HMAC أوالمسارات
المطلقة في تقريرها المطبوع.

المصادقة هي `HMAC-SHA256` فوق JSON قانوني Canonical. أقصى صلاحية للإيصال
سبعة أيام، ويجب أن يقع `decision_at` بعد الإصدار وقبل الانتهاء. يُشتق
`run_date` ديناميكيًا من وقت الإصدار في `Asia/Kuwait`؛ لا يوجد تاريخ تشغيل
مثبت يدويًا داخل الكود.

## ما يربطه Run Receipt

يعيد المصدر قراءة مساحة العمل ولا يثق في Status محفوظ. يتطلب بصمتين
متوقعتين من خارج المساحة، ثم يربط:

- `run_id` و`batch_id` وتسلسل الدفعة؛ العقد الحالي مقفل على الدفعة الأولى.
- `plan/tri_security_batch_plan.json` مع SHA-256 والحجم.
- `scoped_config/manifest.json` مع SHA-256 والحجم، ثم يعيد فحص كل ملف مسجل.
- `reports/tri_security_workspace_report.json` مع SHA-256 والحجم.
- Registry والـBatch payload وبصمتيهما.
- نافذة التأهيل من `window_from` إلى `window_to` وتوقيت `Asia/Kuwait`.
- مقامًا من ثلاثة أسهم بالضبط: `KFH` و`SHIP` و`AZNOULA`، مع
  Security Code وTicker وISIN والقطاع وحالة `UNVERIFIED_SEED`.
- البوابات الاثنتي عشرة بترتيبها الأصلي، وكلها
  `PENDING_EXTERNAL_EVIDENCE`.

أي تغيير في الخطة أوManifest أوملف Scoped Config أوWorkspace Report، أوأي
خلط بين Run/Batch/Cohort/Window مختلف، يفشل مغلقًا. تعاد قراءة الملفات
الحساسة في نهاية الفحص لاكتشاف التبديل أثناء التحقق.

## عدم توافق Benchmark المقصود

إعداد Benchmark الموروث من Pilot الخماسي لا يغطي قطاعات الدفعة الثلاثية؛
قطاعا `Industrials` و`Utilities` غير موجودين ضمن السلاسل القطاعية المطلوبة.
لذلك يثبت الإيصال صراحة:

```text
scope_state = CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT
comparison_scope = NAMED_TRI_SECURITY_COHORT
benchmark_qualification_allowed = false
five_security_scope_allowed = false
full_market_scope_allowed = false
```

اختفاء عدم التوافق أوتبديل المقام إلى خمسة أسهم أوالسوق الكامل يُعد ترقية
ادعاء غير مصرح بها ويُرفض. الإيصال لا يصلح هذا الإعداد ولا يدّعي جاهزية
Benchmark؛ إصلاح النطاق يحتاج عقدًا ومراجعة منفصلين.

## ما يربطه Stage Binding

تكون شجرة المرحلة خارج مساحة العمل، ويجب أن تحتوي `manifest.json` قانونيًا
من Schema `3.0`. يثبت الربط:

- SHA-256 وحجم Manifest.
- قائمة كل Artifact معلن وبصمته وحجمه.
- بصمة الجرد المعلن وعدده.
- بصمة **كل الملفات الموجودة في شجرة المرحلة** وعددها وحجمها الإجمالي،
  بما يكشف الملفات الزائدة غير المعلنة.
- Run Receipt نفسه، وبصمته، ومحتواه غير الموقع، ومصدره.
- Run/Batch/Cohort/Window/Plan/Scoped Config/Benchmark binding كاملًا.
- `stage_id` واحدًا من المراحل الثماني المسموح بها.

هذا ربط سلامة Bytes مستقل فقط في KU-BO-010. لا يثبت أن Semantics المرحلة
تطابق Run/Cohort/Window؛ الحقل
`binding_proves_stage_matches_run_scope=false` مقصود، ويصبح هذا التحقق إلزاميًا
داخل كل Importer وفي المصالحة ضمن KU-BO-011.

المراحل المسموح بها هي:

```text
OFFICIAL_FOUNDATION
STATUS_CORPORATE
CA_ENRICHMENT
STATUS_HISTORY
RESEARCH_PRICE_HISTORY
BENCHMARK_HISTORY
OFFICIAL_EOD
FINAL_DATA_FOUNDATION_RECONCILIATION
```

عند التحقق تُعاد مصادقة Run Receipt بمفتاحه، ثم Stage Binding بمفتاح مستقل،
ثم تعاد قراءة شجرة المرحلة كاملة. إضافة ملف أوحذفه أوتغيير بايتاته أوManifest
أوخلط إيصال تشغيل آخر يفشل مغلقًا. الروابط الرمزية والملفات الخاصة والمسارات
المتجاوزة للجذر لا تُقبل.

## الفصل المكاني ومنع الاستبدال

- Run Receipt يُكتب خارج Prepared Workspace.
- Stage Output تكون خارج Prepared Workspace.
- Stage Binding يُكتب خارج Prepared Workspace وخارج Stage Output.
- الجذور المتداخلة في أي اتجاه تُرفض.
- مجلد الإخراج يجب ألا يكون موجودًا مسبقًا؛ لا توجد كتابة فوق نتيجة قديمة.
- كل JSON مصادق عليه يجب أن يكون Canonical وألا يحتوي حقولًا مجهولة.

## أوامر CLI

بعد تجهيز الدفعة الأولى، استخدم الأوامر الآتية مع قيم HMAC في متغيرات البيئة
وقت التشغيل فقط:

```bash
kubo-data-foundation issue-tri-security-run-receipt \
  --workspace-root /external/runtime/tri-001 \
  --output-root /external/receipts/run-001 \
  --expected-batch-plan-sha256 <sha256> \
  --expected-scoped-config-manifest-sha256 <sha256> \
  --receipt-id <receipt-id> \
  --issuer-id <issuer-id> \
  --issued-at <aware-iso-instant> \
  --expires-at <aware-iso-instant>

kubo-data-foundation verify-tri-security-run-receipt \
  --receipt-path /external/receipts/run-001/tri_security_run_receipt.json \
  --workspace-root /external/runtime/tri-001 \
  --expected-batch-plan-sha256 <sha256> \
  --expected-scoped-config-manifest-sha256 <sha256> \
  --decision-at <aware-iso-instant> \
  --expected-run-id <run-id> \
  --expected-batch-id tri-001-kfh-ship-aznoula
```

إصدار Stage Binding والتحقق منه يحتاجان متغيرات المفتاحين:

```bash
kubo-data-foundation issue-tri-security-stage-binding \
  --receipt-path /external/receipts/run-001/tri_security_run_receipt.json \
  --workspace-root /external/runtime/tri-001 \
  --stage-root /external/stages/official-foundation-001 \
  --output-root /external/receipts/stage-001 \
  --expected-batch-plan-sha256 <sha256> \
  --expected-scoped-config-manifest-sha256 <sha256> \
  --expected-stage-manifest-sha256 <sha256> \
  --expected-run-id <run-id> \
  --expected-batch-id tri-001-kfh-ship-aznoula \
  --binding-id <binding-id> \
  --stage-id OFFICIAL_FOUNDATION \
  --bound-at <aware-iso-instant>

kubo-data-foundation verify-tri-security-stage-binding \
  --binding-path /external/receipts/stage-001/tri_security_stage_binding.json \
  --receipt-path /external/receipts/run-001/tri_security_run_receipt.json \
  --workspace-root /external/runtime/tri-001 \
  --stage-root /external/stages/official-foundation-001 \
  --expected-batch-plan-sha256 <sha256> \
  --expected-scoped-config-manifest-sha256 <sha256> \
  --expected-stage-manifest-sha256 <sha256> \
  --decision-at <aware-iso-instant> \
  --expected-stage-id OFFICIAL_FOUNDATION \
  --expected-run-id <run-id> \
  --expected-batch-id tri-001-kfh-ship-aznoula
```

لا تمرر `--pilot-config-dir` إلى أوامر الإيصال؛ تُشتق Scoped Config من مساحة
العمل وتُثبت ببصمتها الخارجية المتوقعة.

## حدود الادعاء والمرحلة التالية

القيمة الثابتة للإيصالين هي:

```text
AUTHENTICATED_BINDING_NOT_MARKET_EVIDENCE
```

نجاح الإصدار أوالتحقق يثبت سلامة الربط والمصادقة فقط. لا تزال أوامر الاستيراد
القائمة والمصالحة النهائية لا تشترط هذا الإيصال في `KU-BO-010`. المهمة
`KU-BO-011` هي الحد الأدنى التالي: فرض Run Receipt وStage Binding قبل الكتابة
في كل مسارات الهوية والحالة والأسعار وEOD، وحملهما إلى المصالحة النهائية من
دون إنشاء تعريف Readiness موازٍ أوأضعف.

يبقى `KU-BO-008-D01` مفتوحًا. لا يختار هذا العقد طريقة تقدم نافذة Outcome
خلال التعليق، ولا يحسم الحد الأقصى للتمديد أوالحالة النهائية أوNon-fill أو
Corporate Actions. لذلك لا يسمح بأي تقييم حقيقي حتى يصدر قرار product-specific
صريح وفق `docs/codex/USER_DECISIONS.md`.

## الملفات المرجعية

- `src/kubo/tri_security_receipts.py`: بناء الإيصالين والتحقق منهما.
- `schemas/tri-security-run-receipt.schema.json`: عقد Run Receipt الصارم.
- `schemas/tri-security-stage-binding.schema.json`: عقد Stage Binding الصارم.
- `tests/test_tri_security_receipts.py`: اختبارات المصادقة والتلاعب والخلط
  والمسارات وعدم التوافق ونطاق الثلاثة.
- `docs/TRI_SECURITY_PILOT_V0_3_AR.md`: إعداد الدفعة ومساحة العمل السابقة.
