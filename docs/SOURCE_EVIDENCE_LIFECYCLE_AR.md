# مصالحة دورة حياة الدليل

## الغرض

تربط هذه الطبقة كل قيمة بمحاولة جمع محددة، ناشر، URL آمن، طريقة وصول، حالة
حقوق وrobots، وقت، bytes hash، Parser، Schema fingerprint، ومقام خلايا متوقع
مجمّد قبل القرار. وهي تعيد تنفيذ وظيفة predecessor داخل نواة `kubo` بدل إنشاء
أداة أو Database موازية.

## ما تمنعه

- لا يتحول 401/403 أو Paywall أو Challenge أو Robots denial إلى بيانات.
- لا تدخل bytes الخاصة بالصفحات المحجوبة في Evidence.
- لا يستمر التطبيع عند Parser/Schema drift.
- لا تدخل قيمة بعد `decision_at`، ولا يقبل Historical late retrieval دون
  `VERIFIED_ARCHIVE` مع دليل Confirmed من Grade A/B.
- لا يبدأ Revision chain من رقم أكبر من 1، ولا يقبل Gap أوCollision أوتراجعًا
  زمنيًا.
- لا يعتبر نسخ الخبر من مواقع متعددة تأكيدات مستقلة إذا كان `origin_id` واحدًا.
- لا يحسم التعارض بعدد النسخ أوالمتوسط؛ يلزم قيمة Authoritative فريدة، وإلا
  تبقى الخلية متعارضة ومفقودة.
- لا يملأ Missing values ولا يسمح للصحافة أوSocial/روابط التوجيه بإثبات حقل
  Critical رسمي.

## Evidence class

كل تشغيل يعلن واحدًا من:

- `SYNTHETIC_FIXTURE` لاختبار الكود فقط؛
- `RECORDED_AUTHORIZED_FIXTURE` لبايتات مسجلة مخولة؛
- `PROVEN_REAL_EVIDENCE` بعد بوابات الحقوق والمصدر والبايتات.

هذا الوسم لا يثبت الحقوق أوالحقيقة بمفرده. التقرير يعيد دائمًا
`model_fitting_permitted=false` و`backtest_permitted=false` و
`recommendation_permitted=false` و`financial_execution_permitted=false`.

## التشغيل الاصطناعي

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  reconcile-source-evidence \
  --input examples/synthetic_source_evidence_lifecycle.json \
  --output /tmp/source-evidence-report.json
```

يرفض الأمر الكتابة فوق ملف موجود. ينجح المثال بالحالة
`STRUCTURE_AND_RECONCILIATION_VALID_ONLY` لأن المقام الاصطناعي الوحيد مغطى،
لكن ذلك لا يثبت Company coverage أوMarket data أوPrediction quality.

## الحالات

- `STRUCTURE_AND_RECONCILIATION_VALID_ONLY`: اكتملت الخلايا المتوقعة بلا عيب
  بنيوي؛ لا تزال كل الادعاءات التشغيلية مغلقة.
- `DEGRADED_STRUCTURE_VALID_ONLY`: نجت الخلايا الحرجة، لكن هناك Source failure
  أوQuarantine أوMissing non-critical أوConflict غير حرج.
- `BLOCKED`: توجد خلية حرجة مفقودة أوغير قابلة للحسم.

تعطل مصدر واحد لا يمحو دليل مصدر آخر، لكنه يبقى ظاهرًا في
`attempt_summary`, `quarantine`, و`stop_source_families`.

الصفوف المرفوضة لا تُعاد خامًا داخل التقرير؛ يسجل `quarantine` معرّفات محدودة
وSHA-256 فقط حتى لا يعكس URL موقّعًا أوcredential غير صالح.
