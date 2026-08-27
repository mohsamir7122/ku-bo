# مراجعة Factor 9 وبوابات إدخاله

تاريخ المراجعة: 2026-08-24

## النتيجة

`Factor 9` أصل بحثي مهم يجب الحفاظ عليه، لكنه ليس Dataset تدريبية معتمدة ولا
نموذجًا صالحًا للتوقع أو التنفيذ حاليًا. حالته المقفلة هي:

```text
RESEARCH_ASSET_PENDING_ADMISSION
promotion ceiling: RESEARCH_INPUT_ONLY
```

## ما تمت مراجعته في Drive

شملت المراجعة التقرير الرئيسي، خريطة مصادر V2، تقارير استخراج أسعار Mubasher،
تقارير Validation وCleaning، عينة Training-ready، ومكتبة الأحداث التاريخية.
الأسماء الفنية المرجعية تشمل:

- `07_factor9_master_report.md`
- `V2_FACTOR9_DATA_NEED_SOURCE_MAP.md`
- `FACTOR9_MUBASHER_FULL_PRICE_EXTRACTION_REPORT.md`
- `FACTOR9_FULL_PRICE_TIMESERIES_VALIDATION.md`
- `FACTOR9_PRICE_TIMESERIES_CLEANING_REPORT.md`
- `FACTOR9_MUBASHER_HISTORICAL_URL_TEST.md`
- ملفات `factor9_training_ready_enhanced` و`factor9_historical_event_library_master`

لا تدخل هذه الملفات الخاصة إلى Git. وجهتها المنطقية بعد القبول هي:

```text
AI Rebuild/04_Curated_Core/KU_BO/01_Factor9_Research
```

## الأرقام المتصالحة

- Company master: 140 شركة.
- Tickers لها Price history: 137.
- الصفوف الأصلية: 534,135.
- الصفوف النظيفة: 533,997.
- الصفوف المستبعدة الفريدة: 138.
- المصالحة الحسابية: `534135 - 533997 = 138`.
- Issue flags المبلغ عنها: 243، وهي Flags وليست عدد الصفوف المستبعدة.
- محاولة الاستخراج الكامل غطت 138 شركة مرتبطة، مع Failure واحد مسجل.

تقرير Validation ذكر 105 حالات `high < low`، و70 حالة `close > high`، و68 حالة
`close < low`. قد تتجمع أكثر من Flag في صف أو تختلف طريقة العد؛ لذلك لا يُستنتج
من مجموع 243 أن هناك 243 صفًا فريدًا مستبعدًا.

## ما يمكن الحفاظ عليه دون تكرار

- ملفات Raw السعرية.
- الملف النظيف.
- ملف الصفوف المستبعدة.
- Failure ledger.
- Company master.
- مخرجات Price factors وScore القديمة بوصفها Baseline بحثية.
- Event library وReview queue.

لا يعيد Codex Crawling أو Cleaning أو Score نفسه قبل بناء Manifest ببصمات الملفات
والتحقق من أن Artifact ناقص أو تالف فعلًا.

وجود الـManifest أو الملف في Drive ليس دليل سلامة. يلزم جذر Artifact محلي موثوق؛
يُعاد فتح كل ملف منه دون اتباع symlinks، ثم يعاد حساب الحجم وSHA-256 ومقارنتهما
بالـManifest. الملف المفقود أو المتغير وpath traversal تمنع القبول، وأدلة البوابات
المحلولة يجب أن تطابق hashes لملفات أعيد فتحها بالفعل.

## المخاطر المكتشفة

- الهوية الرسمية effective-dated غير مثبتة لكل صف.
- حقوق إعادة الاستخدام الآلي لمصدر السعر الثانوي لم تُثبت.
- اكتمال تعديلات Corporate Actions غير مثبت.
- بعض تواريخ وأسماء Event library ناتجة عن OCR أو Auto-normalization وتظهر فيها
  أخطاء هوية أو تاريخ.
- وقت إتاحة كل حدث Point-in-Time غير مثبت.
- Fundamental وMarket Cap وOutstanding Shares ليست طبقة نهائية.
- Score V1 سعري واستكشافي، وليس Probability أو Investment model.

## بوابات القبول الإلزامية

1. إنشاء Manifest خاص داخل Drive يربط كل ملف بالمسار المنطقي وSHA-256 والحجم
   والنسخة والمصدر.
2. مراجعة الحقوق وطريقة الوصول والغرض المسموح لكل Artifact.
3. ربط الشركات والأسعار بـOfficial Security Code وهوية effective-dated.
4. إعادة التحقق من معادلة Raw/Clean/Excluded دون إعادة بناء البيانات.
5. مصالحة Corporate Actions مع الإفصاحات والأسعار الرسمية.
6. مراجعة كل Event label بواسطة دليل رسمي أو مراجعة بشرية مسجلة.
7. إثبات `published_at` و`available_at` وقرار المعالجة لكل حدث.

أي بوابة تفشل تنقل الصف إلى Quarantine أو Review Queue. لا يُملأ الصف بالحدس،
ولا يتحول وجوده في Drive إلى حق استخدام أو حقيقة تدريبية.

## طريقة دمجه لاحقًا

بعد القبول، يدخل Factor 9 كطبقة Research Feature/Context داخل KU-BO، مع فصل:

- السعر الخام عن السعر المعدل؛
- العوامل السعرية عن Fundamental؛
- الأحداث المراجعة عن Auto-labels؛
- بيانات التطوير عن Locked test؛
- Score عن Probability وعن قرار الاستثمار.

أول استخدام صحيح له هو Baseline ومصدر candidates لمكتبة الأحداث، ثم مقارنة
Walk-forward. لا يملك وحده صلاحية إنتاج سعر دخول أو خروج أو توصية شراء.
