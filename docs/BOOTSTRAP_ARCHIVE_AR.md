# أرشيف بدء التشغيل المعزول — عقد KU-BO-014

## الغرض

ينقل `KU-BO-014` طبقة المعرفة التاريخية من مجرد خطة سنوية إلى مساحة عمل
معزولة وقابلة للتحقق ومهيأة لتصميم الاستئناف في مرحلة لاحقة. هذه المرحلة تبني هيكل الأرشيف وعقوده
فقط؛ لا تجمع صفحات أوتقارير أوصحفًا أوبيانات شركات، ولا تدّعي أن سنة واحدة
اكتملت.

النتيجة المقصودة هي `Bootstrap Archive Scaffold` داخل معمارية المستودع، بينما
تبقى بايتات التشغيل المستقبلية خارج Git تحت مسار Runtime يختاره المشغل.

## ما الذي يعاد استخدامه؟

لا يعيد الأرشيف تعريف تاريخ الكويت أوالمصادر من الصفر. يعتمد مباشرة على
`KU-BO-013`:

- `config/historical_sources.json`: 28 تعريف مصدر وحدود السلطة والحقوق؛
- `config/historical_research_layers.json`: الطبقات التاريخية الست؛
- `HistoricalKnowledgeCatalog`: التحقق الصارم من الكتالوج؛
- `compile_research_plan`: الخطة السنوية الحتمية؛
- عقود الحدث التاريخي وتاريخ الشركة السنوي القائمة.

يُحفظ ملف واحد فقط للخطة التاريخية في مساحة العمل. لا يجوز نسخ المهام السنوية
داخل كل قسم أوإعادة تطبيق قواعد السنوات في وحدة جديدة.

## أقسام الأرشيف

يقسم العقد المحتوى المستقبلي منطقيًا إلى خمسة أقسام:

1. `KUWAIT_GENERAL_HISTORY`: تاريخ الكويت العام؛
2. `COMMERCIAL_ECONOMIC_HISTORY`: التاريخ التجاري والاقتصادي والأزمات؛
3. `COMPANY_HISTORY`: تأسيس الشركات ودورة حياتها؛
4. `LEGAL_REGULATORY_HISTORY`: القضايا والقرارات القانونية والتنظيمية؛
5. `COMMUNITY_ARCHIVAL_CONTEXT`: الإعلام التاريخي والأرشيف المجتمعي والسوشيال للتوجيه أوالمزاج.

القسم الخامس لا يثبت حقيقة رسمية. وجود منشور عام أوصفحة مؤرشفة قد يقود إلى
وثيقة أصلية، لكنه لا يثبت مؤسس شركة أوحكمًا قضائيًا أوإفصاحًا ماليًا.

## ترتيب المراحل

```text
1. BOOTSTRAP_ARCHIVE
2. COMPANY_INTELLIGENCE
3. SOURCE_WAVES
4. BOURSA_OFFICIAL_RECONCILIATION
```

الحالات الأولية مغلقة عمدًا:

```text
BOOTSTRAP_ARCHIVE
  EMPTY_ARCHIVE_PREPARED_COLLECTION_BLOCKED

COMPANY_INTELLIGENCE
  BLOCKED_PENDING_BOOTSTRAP_VALIDATION_AND_OFFICIAL_UNIVERSE

SOURCE_WAVES
  BLOCKED_PENDING_COMPANY_INTELLIGENCE

BOURSA_OFFICIAL_RECONCILIATION
  BLOCKED_PENDING_SOURCE_WAVES
```

### لماذا نحتاج بورصة الكويت قبل المرحلة الأخيرة أيضًا؟

دراسة الشركات المدرجة تحتاج في البداية إلى مرساة هوية رسمية محدودة تحدد
`security_code` والاسم القانوني وعضوية السوق في تاريخ معلوم. هذه المرساة
يستقبلها مسار `kubo-data-foundation` للتحقق بعد توريد Evidence رسمية كاملة؛
وهي غير موجودة في الـPilot الحالي، ولا تعني إجراء المصالحة الشاملة
مبكرًا.

بعد اكتمال ملفات الشركات وموجات المصادر، تعود المرحلة الرابعة إلى بورصة
الكويت وهيئة أسواق المال لإجراء `Final Official Reconciliation` للإفصاحات
والهوية والحالة والإجراءات. بهذه الطريقة لا نبني المقام من قائمة غير رسمية،
ولا نجعل المصدر الرسمي مجرد زينة في نهاية التحليل.

## Source Crosswalk

الكتالوج التاريخي وشبكة المصادر الحالية يستخدمان مساحتي أسماء مختلفتين. لا
يوجد تطابق مباشر بين معرّفات المصادر التاريخية الثمانية والعشرين ومعرّفات
الشبكة التشغيلية. لذلك يضيف العقد Crosswalk مرجعيًا يربط، عند الإمكان:

```text
historical_source_id -> network_source_ids
```

حالات الربط هي:

- `DECLARED_MAPPING_ONLY`: تقارب دلالي معلن فقط؛
- `PARTIAL_DECLARED_MAPPING`: السطح الشبكي يغطي جزءًا من معنى المصدر التاريخي؛
- `UNMAPPED_DEFINED_ONLY`: لا يوجد نظير تشغيلي مسجل.

كل صف يحمل `collection_allowed=false`. الربط لا يثبت Connector أوParser أوحق
وصول أوتغطية أرشيفية أوحالة `LIVE_OPERATIONAL`. ومن أمثلة الحدود المهمة أن
صفحة وزارة التجارة العامة لا تثبت وحدها اكتمال السجل التجاري، وأن صفحة صحيفة
حالية لا تثبت اكتمال أرشيف كل سنواتها.

## شكل مساحة العمل

تُنشأ مساحة العمل تحت مسار Runtime جديد غير موجود مسبقًا. البنية المحجوزة
تشمل:

```text
control/
historical/
manifests/
stages/
raw/
  primary_official/
  primary_archive/
  intergovernmental/
  editorial/
  community/
  routing_only/
normalized/
  events/
  economic/
  companies/
  legal_regulatory/
receipts/
  capture/
  search/
  rights/
indexes/
  year/
  company/
quarantine/
reports/
```

في `KU-BO-014` تظل مجلدات Evidence فارغة. الملفات المنشورة هي Control
artifacts فقط: الخطة، Bindings المدخلات، Snapshot الإعداد، وصف الأرشيف، وصف
المراحل، Manifest التحكم، وتقرير التهيئة.

يمكن أن يكون المسار داخل Checkout بشرط أن يقع تحت `runtime/` المستبعد من Git،
أوأن يكون Runtime خارجيًا. لا يسمح العقد بإنشاء الهدف داخل أي مسار آخر من
شجرة المشروع، ولا ينشئه فوق هدف سابق.

```bash
mkdir -p runtime
PYTHONPATH=src python -m kubo --project-root . \
  prepare-bootstrap-archive \
  --as-of 2026-08-14 \
  --output-root runtime/bootstrap-2026-08-14

PYTHONPATH=src python -m kubo validate-bootstrap-archive \
  --archive-root runtime/bootstrap-2026-08-14
```

## الحتمية والبصمات

يُشتق `archive_id` من المحتوى القانوني Canonical للخطة ومدخلات الإعداد. لا
يجوز لوقت التشغيل وحده أن يغير هوية الخطة. يسجل التقرير وقت الإعداد بوصفه
Metadata، بينما تربط SHA-256 كل Control artifact بالبايتات التي نُشرت فعلًا.

عند التحقق يعاد فتح الشجرة من القرص، وتُعاد قراءة الملفات من Snapshot محدودة،
وتحسب البصمات مرة أخرى. لا يكفي أن يصرح Manifest بأن ملفًا سليم.

## النشر الذري وعدم الاستبدال

إنشاء الأرشيف عملية `Atomic no-overwrite`:

- يجب أن يكون المسار الهدف جديدًا؛
- تكتب الملفات أولًا في Staging شقيقة مخفية؛
- يعاد فحص الأب والهدف والشجرة قبل Commit؛
- ينشر المجلد بعملية No-replace؛
- عند الفشل تزال Staging الآمنة ولا يظهر هدف جزئي؛
- لا يُستبدل أرشيف موجود، حتى لو حمل الاسم نفسه.

هذا الشرط يمنع خلط تشغيلين أوفقدان أثر قديم بسبب إعادة تشغيل الأمر.

حد الثقة هنا هو العملية المالكة لمساحة Staging. لا يدعي العقد مقاومة كود خبيث
يعمل في اللحظة نفسها بصلاحيات المستخدم نفسه أو`root` ويعيد كتابة الشجرة بين
آخر تحقق ونداء إعادة التسمية؛ لذلك يظل التحقق المستقل بعد الاستلام إلزاميًا.
أما تغييرات الشجرة أثناء التحقق العادي فتُرفض عبر Snapshot نهائية كاملة.
والضمان هنا Atomic visibility وعدم الاستبدال على نظام الملفات، وليس ضمان
الاستمرار بعد انقطاع كهربائي؛ لا يسجل الإصدار 1.0 ادعاء Crash durability
لإدخالات المجلد ونداء Rename عبر كل المنصات.

أقدم `as_of` مقبول للـScaffold هو `1980-01-01`، وهي أول سنة تصبح عندها
الطبقات الست كلها معرفة بنطاق غير سالب. ويُقاس حد المستقبل بتاريخ الكويت، لا
بتاريخ UTC المضيف.

## Manifest فارغ لا يعني «لا توجد أحداث»

Manifest هذه المرحلة يميز بين:

- `control_artifacts`: ملفات العقود والتخطيط؛
- `evidence_artifacts`: مصفوفة فارغة إلزاميًا.

الحالة `SCAFFOLD_ONLY_NO_EVIDENCE` تعني أن الجمع لم يبدأ. لا تعني أن البحث
اكتمل أوأن سنة ما خالية من الأحداث. الوصول لاحقًا إلى
`NO_VERIFIED_EVENT_FOUND` يحتاج Receipts كاملة لكل مصدر واستعلام وصفحة وربطها
بEvidence hashes، وفق عقد KU-BO-013.

## بوابة Company Intelligence

لا تنتج الخطة الحالية Task مستقلًا لكل شركة؛ مهام `COMPANY_YEAR` ما زالت
قوالب سنوية تحمل Placeholders إلى أن يصل تعداد رسمي. قبل فتح المرحلة الثانية
يجب توفير:

- Official listed-company universe بتاريخ فعالية معلوم؛
- `security_code` وهوية قانونية Effective-dated؛
- مصالحة الاسم والرمز وISIN؛
- دليل العضوية الرسمي وبصمته؛
- تقرير تحقق مستقل يرفض النقص والتكرار والهوية المعتمدة على Ticker فقط.

عندها فقط يمكن توسيع السنة إلى Company-Year work items وبناء Dossier لكل شركة.

## ما لا تفعله هذه المرحلة

- لا تنفذ Capture أوSearch حيًا؛
- لا تحمل PDF أوصفحات ويب؛
- لا تجمع بيانات شخصية أوقضايا؛
- لا تفحص حسابات Social Media؛
- لا تبني Company Intelligence؛
- لا تنفذ Source Waves؛
- لا تصالح إفصاحات بورصة الكويت؛
- لا تولد Factor أوScore أوForecast؛
- لا تنتج Probability أوRecommendation أوExecution instruction؛
- لا تثبت Backtest readiness أوFull-market coverage.

## حدود Git وRuntime

يدخل Git:

- الكود؛
- Configs والعقود؛
- JSON Schemas؛
- الاختبارات وFixtures الاصطناعية المصرح بها؛
- الوثائق وتقارير Handoff المنزوعة البيانات الخاصة.

يبقى خارج Git:

- Raw historical bytes؛
- صفحات الصحف وPDF والنسخ المؤرشفة؛
- Court/registry exports؛
- Social content؛
- Credentials وCookies وSessions؛
- Licensed datasets؛
- Runtime archive workspaces.

التخزين الخارجي ليس مصدر حقيقة بذاته. كل Fact مستقبلية تحتاج Original source،
URL، توقيتًا، حقوقًا، Capture hash، Content hash، ودور Evidence صالحًا.

## حالة المرحلة

```text
TASK: KU-BO-014
STATUS: IN_PROGRESS
MODE: EMPTY_SCAFFOLD_ONLY
MERGE_ALLOWED: NO
HISTORICAL_EVIDENCE_COUNT: 0
COMPANY_COUNT: 0
EVENT_COUNT: 0
COLLECTION_ALLOWED: false
```

لا تسجل هذه الوثيقة نجاحًا للاختبارات. تضاف الأعداد والـCommit والـPR والـCI
إلى Handoff فقط بعد تنفيذها على الرأس الدقيق للمرحلة.
