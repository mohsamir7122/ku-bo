# Official Identity and Trading Calendar Pilot v0.2

## الهدف

هذه المرحلة تلي `Data Foundation Pilot v0.2` ولا تستبدلها. هدفها إضافة طبقتين كانتا تمنعان ربط Price History بالسوق بصورة منضبطة:

- Current Official Identity للأسهم الخمسة.
- Official Trading Calendar لسنة 2026.

الأسهم المشمولة تظل:

```text
NBK
KFH
MABANEE
ZAIN
HUMANSOFT
```

لا تبني المرحلة Historical Point-in-Time Universe كاملًا، ولاSecurity Status History، ولاCorporate Actions، ولاBenchmark، ولاOfficial Complete Daily EOD. لذلك لا تسمح بـReal Backtest أوForecast أوRecommendation.

## لماذا نستخدم أكثر من مصدر رسمي للهوية؟

صفحة Short Sell الرسمية تستطيع توفير:

```text
Security Code
Company Name
ISIN
```

أما صفحة Listed Companies الرسمية فتضيف:

```text
Ticker
Sector
Market Segment
Date of Listing
```

لا يسمح النظام لأي صفحة منهما منفردة بإكمال Current Identity. يجب أن يتطابق `security_code`، وأن يطابق `ISIN` الـSeed المقيدة، وأن يطابق `Ticker` الاسم المستهدف، وأن تكون الأسماء الرسمية متوافقة.

يحفظ `security_master.csv` بصمتين:

```text
raw_sha256
supporting_raw_sha256s
```

وبذلك لا تضيع حقيقة أن الصف الموحّد نتج من مصالحة أكثر من Official Artifact.

## حدود Current Snapshot

يكتب النظام:

```text
identity_scope = CURRENT_SNAPSHOT_ONLY
valid_from = identity_snapshot_effective_date
```

هذا التاريخ هو تاريخ اللقطة الرسمية المتصالحة، وليس Listing Date ولادليلًا على أن نفس Ticker أوMarket Segment كان مستخدمًا في كل السنوات السابقة.

يُحفظ `listing_date` كحقل وصفي رسمي مستقل، ولا يُستخدم بدل Effective-Dated Identity History.

## Official Artifacts المطلوبة

ينشئ الأمر Workspace يحتوي خمسة عقود ثابتة:

```text
short_sell_identity
listed_companies
market_holidays
trading_extension
contact_hours
```

المصادر الرسمية المحددة في العقد هي:

```text
https://reports.boursakuwait.com.kw/en/shortsell
https://www.boursakuwait.com.kw/en/participants/participants/listed-companies/
https://www.boursakuwait.com.kw/en/securities/trading/market-holidays/
https://www.boursakuwait.com.kw/TS-Extension-EN/
https://www.boursakuwait.com.kw/en/contact/
```

صفحة Listed Companies قد تعتمد على Client Rendering؛ لذلك يجب حفظ الصفحة بعد ظهور الجدول كاملًا بواسطة Authorized Browser Export. صفحة HTML لا تحتوي الجدول الفعلي تُرفض باعتبارها Parser Drift، ولا تتحول إلى Zero Result.

## إنشاء Workspace

```bash
kubo-data-foundation --project-root . prepare-official-foundation \
  --output-root runtime/official_foundation/official-pilot-001 \
  --run-id official-pilot-001 \
  --calendar-year 2026 \
  --prepared-by "authorized-user"
```

ينشئ الأمر:

```text
runtime/official_foundation/official-pilot-001/
  raw_exports/boursa/
  manifests/official_foundation_manifest.json
  normalized/
  reports/
  quarantine/
```

وجود Workspace أوPlaceholder لا يثبت أي شيء. يجب استبدال كل Placeholder بالبايتات الرسمية الكاملة، وتسجيل:

```text
file_sha256
observed_at
captured_by
review_status = ACCEPTED
```

## شرط التوقيت

يجب جمع Artifact الهوية من Short Sell وArtifact Listed Companies في نفس اليوم المدني وفق `Asia/Kuwait`.

كما يجب أن يساوي:

```text
identity_snapshot_effective_date
```

تاريخ هذا الجمع. يمنع ذلك تكوين Current Identity واحدة من صفحتين التقطتا في تاريخين مختلفين بينما ربما تغير الإدراج أوالرمز بينهما.

## الاستيراد والمصالحة

```bash
kubo-data-foundation --project-root . import-official-foundation \
  --workspace runtime/official_foundation/official-pilot-001 \
  --output-root runtime/data_foundation/official-pilot-001
```

المخرجات الأساسية:

```text
raw/
normalized/security_master.csv
normalized/trading_calendar.csv
reports/official_identity_report.json
reports/trading_calendar_report.json
reports/official_foundation_import_report.json
manifest.json
official_foundation_manifest.json
```

## بناء Trading Calendar

يبني النظام صفًا لكل يوم مدني داخل سنة واحدة.

يستنتج نوع اليوم فقط من Official Evidence:

- `HOLIDAY`: التاريخ موجود في صفحة Market Holidays الرسمية.
- `WEEKEND`: اليوم خارج Sunday–Thursday وفق صفحة Contact الرسمية.
- `NORMAL`: يوم ضمن Sunday–Thursday وليس ضمن Holiday List.

بالنسبة إلى الأيام العادية لسنة 2026، يُربط النظام بـSession Regime الساري من 12 أكتوبر 2025:

```text
Continuous Trading: 09:00:00–13:00:00
Closing Auction: 13:00:00–13:10:00
Trade at Last: 13:10:00–13:15:00
```

عقد `trading_calendar.csv` الحالي يحتفظ بـ:

```text
continuous_start
continuous_end
trade_at_last_end
session_regime_id
raw_sha256
supporting_raw_sha256s
```

ولا يدّعي أن Holiday Snapshot غير قابلة للتغيير؛ فقد تصدر قرارات رسمية لاحقة تعدّل بعض التواريخ.

## حالات التشغيل

```text
CURRENT_IDENTITY_AND_CALENDAR_READY
```

تعني أن Current Identity للأسهم الخمسة وتقويم السنة اجتازا العقود. لا تعني Historical Universe جاهزة.

```text
PARTIAL
```

تعني نجاح إحدى الطبقتين وفشل الأخرى.

```text
BLOCKED
```

تعني عدم وجود ناتج صالح.

## أسباب الرفض الأساسية

- Artifact ناقصة أوغير موجودة.
- Hash لا يطابق البايتات.
- Manifest غير مكتملة أوغير مقبولة.
- Identity pages في يومين مختلفين بتوقيت الكويت.
- Short Sell ISIN لا يطابق Pilot Seed.
- Listed Companies Ticker لا يطابق السهم.
- Official Names متعارضة.
- Listed Companies table غير Rendered.
- Holiday Year لا يطابق Calendar Window.
- Session ranges غير متصلة.
- Calendar لا يحتوي كل يوم مدني في الفترة.
- Supporting Evidence Hash غير محلولة.

## ما لا تزال المرحلة لا تثبته

- Historical ticker changes.
- Historical market segment changes.
- Delistings وإعادة الإدراج.
- Suspensions وHalts التاريخية.
- Corporate Actions.
- Benchmark prices.
- Official value traded وtrade count وreference price.
- Full-market denominator عبر السنوات.
- Forecast skill أوAccuracy.

## المرحلة التالية

بعد نجاح Current Identity وTrading Calendar، تكون الخطوة المنطقية التالية:

```text
Security Status History + Corporate Action Ledger
```

ولا يبدأ Model Training قبل اكتمال هذه الطبقات وربطها بـPrice History وBenchmark.
