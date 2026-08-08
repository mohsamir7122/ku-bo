# سياسة تجميع ملفات الأسعار

هذه الوثيقة تحدد سياسة تجميع ملفات الأسعار قبل إدخالها في `USER_EXPORT` أو أي Backtest حقيقي. الهدف ليس فقط الحصول على CSV، بل بناء إطار فارغ قابل للتعبئة، يمنع خلط الأسهم، ويجعل كل ملف سعر قابلًا للمراجعة لاحقًا.

الاسم التشغيلي لهذه الطبقة:

`Price File Collection Framework`

## 1. المبدأ الأساسي

ملف الأسعار لا يدخل المشروع إلا إذا كان معه دليل مصدر واضح. أي ملف بلا مصدر، أو بلا تاريخ تنزيل، أو بلا ربط مؤكد مع `security_code` و`ISIN`، يعامل كبيانات غير صالحة للـBacktest.

الملف المقبول يجب أن يجيب عن خمسة أسئلة:

- ما السهم المقصود؟
- ما مصدر الأسعار؟
- متى تم تنزيل الملف أو تصديره؟
- هل الأسعار Raw أم Adjusted؟
- هل يمكن إعادة الوصول إلى المصدر أو إثباته لاحقًا؟

إذا لم نستطع الإجابة، يدخل الملف في `quarantine` ولا يدخل `normalized/eod_ohlcv.csv`.

## 2. أنواع المصادر المقبولة

### مصدر رسمي أو مرخص

هذا هو المصدر الأعلى ثقة، ويستخدم كمرجع عند التعارض:

- Boursa Kuwait official reports أو data products.
- Company disclosures المنشورة رسميًا.
- Licensed market data vendor مثل LSEG أو Bloomberg أو Refinitiv إذا توفر اشتراك مصرح.
- Broker statement أو platform export إذا كان مصرحًا ومحدد التاريخ.

هذه المصادر تصلح لبناء `daily_eod`, `Corporate Actions`, و`Trading Calendar` إذا كانت تغطي الحقول المطلوبة.

### مصدر ثانوي قابل للمراجعة

يستخدم كمصدر مساعد أو مؤقت، ولا يكفي وحده لفتح Backtest كامل إذا لم توجد Corporate Actions وCalendar:

- Investing.com manual export.
- TradingView export إذا كان متاحًا للمستخدم ومصرحًا.
- Yahoo/other finance portals فقط إذا كانت تغطي السهم الكويتي بدقة ويمكن توثيق الرابط.
- Screenshots أو HTML محفوظ من Browser مصرح، بشرط وجود Metadata ووقت حفظ.

هذا النوع يصلح لمرحلة `Live Pilot Data Import`، وليس وحده لإعلان Accuracy نهائية.

### مصدر غير مقبول للتسعير التاريخي

هذه المصادر قد تفيد في Sentiment أو News، لكنها لا تستخدم كملف سعر رسمي:

- Telegram messages.
- Forums أو social media posts.
- صور متداولة بلا رابط أصلي.
- ملفات Excel مجهولة المصدر.
- أرقام مكتوبة يدويًا بلا Raw evidence.

لو استخدمت هذه المصادر، تكون فقط كـFeature أو Signal، وليس كسعر Entry/Exit.

## 3. ترتيب أولوية المصادر عند التعارض

إذا اختلفت الأسعار بين مصدرين:

1. المصدر الرسمي أو المرخص مقدم.
2. المصدر الذي يثبت `security_code` و`ISIN` مقدم على المصدر الذي يستخدم Ticker فقط.
3. المصدر الذي يوضح هل السعر Adjusted أم Raw مقدم.
4. المصدر الأحدث تنزيلًا لا يتفوق تلقائيًا على المصدر الأدق.
5. إذا بقي التعارض، يوسم السهم في ذلك التاريخ `PRICE_CONFLICT` ويمنع من التقييم حتى تتم المراجعة.

لا نحل التعارض بمتوسط الأسعار، لأن ذلك يصنع رقمًا جديدًا لا ينتمي لأي مصدر.

## 4. الحقول المطلوبة لكل ملف سعر

لكل ملف CSV يجب تسجيل Metadata خارج الملف أو في Manifest مرافق:

- `ticker`
- `security_code`
- `isin`
- `name_en`
- `sector`
- `source_name`
- `source_type`
- `source_url_or_location`
- `downloaded_at`
- `downloaded_by`
- `file_name`
- `file_sha256`
- `date_range_start`
- `date_range_end`
- `row_count`
- `price_basis`: `RAW`, `ADJUSTED`, أو `UNKNOWN`
- `currency`
- `unit`: مثل `fils` أو `KWD`
- `allowed_use`: مثل `USER_EXPORT`, `SECONDARY_CHECK`, أو `OFFICIAL_EOD`
- `review_status`: `PENDING`, `ACCEPTED`, `QUARANTINED`, أو `REJECTED`. لا يستورد المسار إلا `ACCEPTED`.
- `review_notes`

أي ملف ناقص `ticker`, `security_code`, `isin`, `source_name`, `downloaded_at`, أو `file_sha256` لا يدخل المسار الحقيقي.

## 5. أسماء الملفات القياسية

داخل مجلد التجميع، استخدم أسماء ثابتة:

```text
prices/raw_exports/{source_name}/{YYYY-MM-DD}/{ticker}.csv
```

مثال:

```text
prices/raw_exports/investing/2026-08-08/KFH.csv
prices/raw_exports/investing/2026-08-08/NBK.csv
```

ولا تغير أسماء الأسهم حسب الاسم العربي أو اسم الشركة الكامل. الربط الحقيقي يكون من `config/symbol_mapping.json`.

## 6. سياسة ملفات Investing USER_EXPORT

ملفات Investing تقبل فقط كـ`SECONDARY_RAW_PRICE_EXPORT` إلا إذا تم توثيق أنها Adjusted.

الأعمدة المطلوبة:

```text
Date,Price,Open,High,Low,Vol.,Change %
```

القواعد:

- ملف واحد لكل سهم.
- اسم الملف يجب أن يطابق `ticker.csv`.
- التواريخ تكون newest-first كما يصدرها الموقع.
- تاريخ مثل `Aug 06, 2026` يجب أن يكون بين علامات اقتباس بسبب الفاصلة.
- لا يتم تعديل القيم يدويًا داخل CSV.
- إذا حدث تعديل لإصلاح Encoding أو Header، يحفظ الملف الأصلي كما هو، ويحفظ الملف المعدل باسم منفصل مع شرح.

## 7. سياسة السعر Raw وAdjusted

لا يجوز خلط Raw وAdjusted في نفس الاختبار.

إذا كان السعر Raw:

- يجب وجود `Corporate Action Ledger`.
- يجب حساب أثر Cash dividends وBonus/Splits في Outcome.
- يجب توثيق أن العائد المستخدم Total return أو Price return.

إذا كان السعر Adjusted:

- يجب توثيق منهج التعديل إن أمكن.
- لا يجوز إضافة تعديلات Corporate Actions مرة ثانية حتى لا يحدث Double adjustment.

إذا كان النوع Unknown:

- يسمح فقط بـDry run أو Data quality check.
- يمنع Backtest الحقيقي.

## 8. سياسة الحفظ والبصمة

كل ملف سعر خام يجب أن يحفظ كما هو دون تعديل، ثم تحسب له بصمة:

```text
SHA-256
```

الملفات الناتجة من المعالجة مثل `normalized/eod_ohlcv.csv` لا تحل محل الملفات الخام. الملف الخام هو الدليل، والملف normalized هو نسخة تشغيلية.

## 9. سياسة المراجعة قبل الإدخال

قبل إدخال أي ملف في `USER_EXPORT` يجب فحص:

- هل عدد الصفوف منطقي؟
- هل التاريخ يغطي الفترة المطلوبة؟
- هل يوجد أيام مكررة؟
- هل توجد أسعار صفرية أو سالبة؟
- هل `High` أقل من `Low`؟
- هل `Open/Close` خارج نطاق `High/Low`؟
- هل حجم التداول مفهوم، خصوصًا `K`, `M`, أو فراغ؟
- هل العملة والوحدة واضحة؟
- هل السهم موقوف في بعض الأيام؟

أي مشكلة لا تعني رفضًا تلقائيًا، لكنها تمنع التقييم حتى تفسر في `review_notes`.

## 10. سياسة quarantine

ينقل الملف إلى `quarantine` إذا:

- لا يوجد مصدر واضح.
- لا يوجد `ISIN` أو `security_code`.
- يوجد تعارض سعري غير محلول.
- السعر يبدو Adjusted لكن غير موثق.
- الملف معدل يدويًا ولا يوجد أصل خام.
- التاريخ أو الـticker لا يطابقان الخريطة.

الملف في `quarantine` يمكن استخدامه للتشخيص فقط، ولا يدخل `Backtest`.

## 11. سياسة الحد الأدنى للخمسة أسهم

لـ`KFH`, `NBK`, `ZAIN`, `HUMANSOFT`, و`MABANEE`، الحد الأدنى قبل `Point-in-Time Real Backtest`:

- CSV سعر حقيقي لكل سهم.
- Manifest مرافق لكل CSV.
- `security_code` و`ISIN` مطابقان لـ`symbol_mapping`.
- تحديد `RAW` أو `ADJUSTED`.
- تغطية نفس الفترة الزمنية لكل الأسهم أو تفسير الفجوة.
- لا توجد `missing_exports`.
- لا توجد `rejected_exports`.

إذا اكتملت الأسعار فقط دون Calendar وCorporate Actions وBenchmark، الحالة تكون:

```text
PRICE_IMPORT_READY_ONLY
```

وليست:

```text
READY_TO_BACKTEST
```

## 12. قالب قرار الملف

كل ملف يأخذ واحدًا من القرارات التالية:

- `ACCEPT_FOR_IMPORT`: صالح للدخول في `USER_EXPORT`.
- `ACCEPT_FOR_SECONDARY_CHECK`: يصلح للمقارنة فقط.
- `QUARANTINE_PENDING_REVIEW`: يحتاج مراجعة.
- `REJECT`: لا يستخدم.

القرار يجب أن يكون مكتوبًا، وليس مفهومًا ضمنيًا.

## 13. مخرجات التجميع المطلوبة

بعد جمع الملفات، يجب أن ينتج مجلد التجميع:

```text
price_collection_manifest.csv
raw_exports/
quarantine/
normalized/
collection_report.json
```

ثم فقط يتم تشغيل:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . import-investing-user-exports ...
```

## 14. قواعد ممنوعة

الممنوعات الصريحة:

- ممنوع إدخال سعر من ذاكرة أو دردشة.
- ممنوع إعادة تسمية سهم لتجاوز خطأ في الخريطة.
- ممنوع ملء يوم ناقص بسعر اليوم السابق إلا إذا كان هذا جزءًا موثقًا من سياسة Calendar.
- ممنوع حذف أيام سيئة لتحسين النتيجة.
- ممنوع اختيار مصدر السعر بعد رؤية Outcome.
- ممنوع تسمية النتيجة Accuracy إذا كانت ملفات الأسعار أو Corporate Actions ناقصة.

## 15. الخلاصة التشغيلية

السياسة المختصرة:

اجمع ملفات الأسعار من مصادر مصرح بها، احفظ الخام، احسب `SHA-256`, املأ Manifest، راجع الهوية والجودة، اعزل المشكوك فيه، ثم أدخل المقبول فقط إلى `USER_EXPORT`.

هذه الطبقة هي الجسر بين جمع الملفات يدويًا وبين `Point-in-Time Real Backtest`. بدونها سنمتلك أرقامًا، لكن لن نمتلك Evidence.
