# عقد هوية الشركة وملفها اليومي

## الغرض

تضيف هذه الطبقة مقامًا صريحًا للشركات والأوراق الفعالة في بورصة الكويت، ثم
تربط ملف كل شركة بهوية effective-dated وبحقائق Point-in-Time قابلة للتتبع. وهي
تعمل فوق `kubo.identity` وعقود التاريخ السنوي الموجودة، ولا تنشئ Security Master
أوHistory engine بديلًا.

## مكونات ملف الشركة

كل ملف يضم الأقسام الإلزامية التالية حتى لو كانت بعض قيمها مفقودة:

- البيانات الأساسية والاسم والحالة ورقم التسجيل؛
- القطاع والنشاط؛
- أحدث الفترة والحقائق المالية؛
- السعر المرجعي وتوقيته والسيولة والتذبذب؛
- الإفصاحات الجوهرية؛
- التوزيعات والإجراءات الرأسمالية؛
- الإدارة والملكية عند توافر مصدر قانوني؛
- المخاطر الرئيسية.

لكل قسم `expected_fields` مجمّد و`critical_fields` لا يجوز إضعاف الحد الأدنى
منها. كل حقل متوقع له Fact واحد فقط. القيمة المفقودة تظل `null` وتتطلب
`missing_reason` وصفًا مطابقًا في `data_gaps`; ولا يسمح بوجود Gap لقيمة محلولة.

## الهوية والدليل

- يرفض المدقق فترات Security Identity المتداخلة وISIN/Ticker collisions.
- يجب أن يساوي مقام `expected_security_codes` الهوية الفعالة عند حالة `EXACT`.
- يربط كل Fact محلول بـEvidence معروف وSHA-256 وتواريخ نشر/حدث/توفر/وصول
  منفصلة، مع توثيق التاريخ المفقود صراحة.
- لا يدخل أي Fact أوEvidence أصبح متاحًا بعد `as_of`. Historical late retrieval
  يحتاج `VERIFIED_ARCHIVE` مؤكدًا من Grade A/B.
- لا يثبت الحقل Critical إلا دليل Confirmed من Grade A/B ودور رسمي/أولي.
- `source_quality.resolved_fields` يعاد اشتقاقه من روابط الأدلة ولا يُقبل كادعاء
  ذاتي، والمصدر الذي قدّم Evidence مقبولًا يجب أن يبقى `AVAILABLE`.

## التشغيل الاصطناعي

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  validate-company-dossier-bundle \
  --universe examples/synthetic_issuer_universe.json \
  --dossier examples/synthetic_company_dossier.json \
  --output /tmp/company-dossier-report.json
```

المثال Fixture اصطناعي لا يمثل شركة حقيقية. نجاحه بالحالة
`STRUCTURE_VALID_ONLY` يثبت بنية البرامج فقط. التقرير يبقي دائمًا
`real_collection_complete=false`, `company_universe_complete=false`,
`training_permitted=false`, `backtest_permitted=false`,
`recommendation_permitted=false`, و`financial_execution_permitted=false`.

## الحالات

- `STRUCTURE_VALID_ONLY`: المقام الاصطناعي/المسجل متسق بلا فجوة.
- `STRUCTURE_VALID_ONLY_WITH_EXPLICIT_GAPS`: الفجوات غير الحرجة موثقة بالكامل.
- `BLOCKED`: هوية/مقام غير مكتمل، ملف ناقص، أوحقل Critical مفقود.

لا تعني أي حالة اكتمال جمع شركات الكويت أوصلاحية تدريب/اختبار/توصية.
