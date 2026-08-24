# تسليم KU-BO إلى Codex

تاريخ التسليم: 2026-08-24

## حالة الجاهزية

المستودع جاهز لبدء **مرحلة Codex التالية** من خلال عقد قابل للفحص. هذه الجاهزية
تعني أن المهمة والمسارات والحدود والتجميد محددة؛ ولا تعني أن Collector أو نموذجًا
حيًا أو توصيات يومية أصبحت جاهزة.

نفّذ أولًا من جذر المستودع:

```bash
python scripts/validate_codex_live_bootstrap.py --project-root . --json
```

النتيجة المطلوبة:

```text
PASS_HANDOFF_CONTRACT
READY_FOR_CODEX_EXECUTION
live runtime: NOT_IMPLEMENTED
scheduler: DISABLED_UNTIL_AUTHORIZED
Factor 9: RESEARCH_ASSET_PENDING_ADMISSION
```

أي اختلاف يوقف العمل حتى يُفهم سببه؛ لا يُعدّل Expected value لتجاوز الفشل.

## الجملة التي يبدأ بها المستخدم في المنزل

```text
اقرأ CODEX_START_HERE.md ونفّذ CURRENT_TASK كاملًا على فرع المهمة. ابدأ بمدقق
Codex، ثم افحص AI Rebuild بصورة خاصة، وأنشئ Manifest قبول Factor 9، ونفّذ Daily
dry-run والتجميد والاختبارات. افتح Draft PR ولا تدمج ولا تنشر بيانات Drive.
```

لا يحتاج المستخدم إلى إعادة شرح تاريخ المشروع؛ `CODEX_START_HERE.md` وملفات
`docs/codex/` وملف bootstrap هي ذاكرة التشغيل الرسمية.

## AI Rebuild

الجذر الخاص هو `AI Rebuild`. المسارات التي أُعدت لـKU-BO هي:

```text
00_Indexes/KU_BO
02_Google_Drive/KU_BO/PRIVATE_CONVERSATION_ARCHIVE
02_Google_Drive/KU_BO/AUTHORIZED_EXPORTS
04_Curated_Core/KU_BO/00_Manifests
04_Curated_Core/KU_BO/01_Factor9_Research
04_Curated_Core/KU_BO/02_Event_Evidence
04_Curated_Core/KU_BO/03_Market_Data
04_Curated_Core/KU_BO/04_Model_Freezes
04_Curated_Core/KU_BO/05_Daily_Reports
90_Quarantine_Duplicates/KU_BO
99_Reports/KU_BO
```

Codex يكتشف معرفات هذه المجلدات وقت التشغيل من Connector المخول. لا يكتبها في
Git أو Documentation أو Logs عامة. كل نقل إلى Curated Core يحتاج Hash وProvenance
وحقوقًا ومراجعة، ولا تُحذف النسخ المكررة؛ تُنقل أولًا إلى Quarantine.

## ترتيب Daily dry-run

1. التحقق من جلسة السوق والحصول على Run lock.
2. فحص الوصول المصرح للمصادر.
3. جمع الأدلة وحفظ البايتات الخاصة وبصماتها.
4. Validation وتطبيع Point-in-Time.
5. بناء Event/Factor snapshot.
6. تشغيل Champion السابق المعتمد فقط.
7. ختم تقرير البحث اليومي.
8. إنضاج وتقييم نتائج التقارير السابقة.
9. تدريب Challengers في مساحة منفصلة بعد فتح بوابة التدريب.
10. إنشاء Draft change proposals دون دمج ذاتي.

إذا لم توجد Freeze صالحة من جلسة سابقة، فالنتيجة `ABSTAIN` أو إيقاف التقرير؛ لا
يُستخدم Challenger اليوم نفسه كحل بديل.

## التوقيت

الوقت الأساسي 15:07 الكويت والـWatchdog عند 15:37. Workflow الظل يختبر العقود
فقط وهو مغلق افتراضيًا خلف `KUBO_DAILY_SHADOW_ENABLED`. كما أن GitHub scheduling
best-effort ولا يضمن التنفيذ في الدقيقة نفسها. تفعيل Workflow لا يفتح Network
collection ولا التدريب ولا التوصيات تلقائيًا.

## مخرجات المرحلة الأولى

المرحلة التالية تنتج Private inventory وFactor 9 admission report وDaily dry-run
receipts واختبارات. لا تنتج أسماء أسهم للشراء أو أسعار دخول وخروج.

المنتجات الأربعة تصبح تقارير بحث فقط بعد اكتمال Data Plane وChampion freeze.
الانتقال إلى توصيات أو Quotes تنفيذية يحتاج بيانات رسمية/مرخصة، اختبارًا مقفلًا
500-600 حدث، prospective validation، وسياسة مخاطر وقرار استخدام منفصل.

## التطوير الذاتي الآمن

Codex مسموح له أن يقرأ النتائج، يسجل Failure mode، يبني Challenger، ويقترح تعديل
كود أو وزن في Task branch. ليس مسموحًا له أن يغير Champion الجاري، يعيد كتابة
تقرير قديم، يدمج PR، أو يختار الأوزان على Locked test. بهذه الحدود يصبح التطوير
مستمرًا وقابلًا للرجوع بدل أن يكون تعديلًا حيًا غير قابل للتدقيق.
