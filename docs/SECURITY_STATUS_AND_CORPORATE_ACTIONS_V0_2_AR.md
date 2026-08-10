# Security Status and Corporate Actions Pilot v0.2

## الهدف

هذه المرحلة مبنية فوق:

```text
Data Foundation Price History
Current Official Identity
2026 Trading Calendar
```

وهدفها إضافة:

- Current Security Status Snapshot للأسهم الخمسة.
- Official Delisting Archive capture.
- Official Corporate Action Schedule للفترة المحددة.

لا تدّعي المرحلة أنها بنت Security Status History كاملة، ولاأنها عرفت نوع كل Corporate Action أوالمبلغ أوAdjustment Factor.

## المصادر الرسمية

تستخدم Workspace العقود التالية:

```text
https://www.boursakuwait.com.kw/en/securities/company-information/suspended-companies/
https://www.boursakuwait.com.kw/en/securities/company-information/delisted-companies/
https://www.boursakuwait.com.kw/en/securities/company-information/corporate-actions/
```

يجب حفظ الصفحات بعد ظهور الجداول Client-rendered. صفحة لا تحتوي الجدول الفعلي تُرفض باعتبارها Parser Drift، ولا تتحول إلى Zero Result.

## إنشاء Workspace

```bash
kubo-data-foundation --project-root . prepare-status-corporate \
  --output-root runtime/status_corporate/status-ca-001 \
  --run-id status-ca-001 \
  --action-window-from 2021-01-01 \
  --action-window-to 2026-08-09 \
  --prepared-by "authorized-user"
```

المخرجات:

```text
runtime/status_corporate/status-ca-001/
  raw_exports/boursa/
  manifests/status_corporate_manifest.json
  normalized/
  reports/
  quarantine/
```

## إكمال Manifest

يجب تحديد:

```text
status_snapshot_effective_date
corporate_action_query.filter_applied = true
pages_declared
pages_received
result_count_declared
corporate_action_query.review_status = ACCEPTED
```

ويجب لكل Artifact تسجيل:

```text
file_sha256
observed_at
captured_by
review_status = ACCEPTED
```

يجب أن يكون تاريخ جمع الصفحات الثلاث هو نفسه `status_snapshot_effective_date` وفق `Asia/Kuwait`.

## الاستيراد

يتطلب الأمر Output صحيحًا من مرحلة Current Official Identity and Calendar:

```bash
kubo-data-foundation --project-root . import-status-corporate \
  --workspace runtime/status_corporate/status-ca-001 \
  --official-foundation-root runtime/data_foundation/official-pilot-001 \
  --output-root runtime/data_foundation/status-ca-001
```

يتحقق الأمر من Upstream Evidence Manifest ومن Raw Hashes ومن `security_master.csv` قبل استخدام الهوية.

## Current Security Status Snapshot

ينتج النظام:

```text
normalized/security_status_evidence.csv
```

لكل سهم Current Identity صف واحد فقط:

```text
TRADING
SUSPENDED
```

إذا كان السهم موجودًا في Official Suspended Companies table يصبح:

```text
SUSPENDED
reason_code = PRESENT_IN_CURRENT_SUSPENDED_TABLE
```

وإذا كان غائبًا عن جدول كامل ومقبول يصبح:

```text
TRADING
reason_code = ABSENT_FROM_COMPLETE_SUSPENDED_TABLE
```

لكن جميع الصفوف تحمل:

```text
temporal_scope = CURRENT_SNAPSHOT_ONLY
```

غياب السهم اليوم عن Suspended Companies لا يثبت أنه لم يُوقف في الماضي. لذلك:

```text
security_status_history_ready = false
```

## Delisting Archive

ينتج النظام:

```text
normalized/delisting_archive.csv
```

ويحتفظ بتاريخ إلغاء الإدراج المنشور رسميًا. إذا ظهر سهم من Current Pilot Identity باعتباره Delisted قبل Snapshot Date، تُحجب Status layer بسبب تعارض رسمي.

Delisting Archive لا تعوض Suspension and Resumption Notices، ولا تثبت جميع الفترات التي كان السهم خلالها موقوفًا.

## Corporate Action Schedule

ينتج النظام ملفين:

```text
normalized/corporate_action_market_rows.csv
normalized/corporate_action_schedule.csv
```

الأول يحفظ كل صفوف Market Result التي استخرجت من الصفحة. والثاني يحتفظ فقط بالأسهم الخمسة بعد مطابقة:

```text
security_code
Ticker
ISIN
```

الحقول الرسمية المتاحة من صفحة Schedule هي:

```text
Cum Date
Ex Date
Record Date
Payment Date
```

لذلك يكتب النظام:

```text
action_type = UNCLASSIFIED_ENTITLEMENT
factor_status = pending
adjustment_factor = empty
coverage_scope = OFFICIAL_SCHEDULE_DATES_ONLY
```

لا يجوز استنتاج أن الصف Cash Dividend أوBonus Shares من التواريخ وحدها، كما لا يجوز حساب Adjustment Factor بلا Official Disclosure يحدد النوع والمبلغ أوالنسبة.

## Enrichment Queue

لكل صف Corporate Action في Pilot ينشأ:

```text
normalized/corporate_action_enrichment_queue.csv
```

ويظل مطلوبًا إضافة Official Issuer/IFSah disclosure يثبت:

```text
Action Type
Cash Amount per Share
Bonus Ratio
Split or Reverse Split Ratio
Rights Terms
Capital Reduction Terms
Official Adjustment Factor or reproducible official calculation inputs
```

## Query Ledger

ينتج:

```text
manifests/query_ledger.csv
```

ويحفظ:

```text
Query Window
Pages Declared
Pages Received
Result Count Declared
Rows Normalized
Zero Result
Raw SHA-256
```

هذا Query Receipt هو Operator Attestation مرتبط بالصفحة الملتقطة، وليس Market Fact مستقلًا. إذا لم يطابق Result Count عدد الصفوف الفعلية، تُحجب Corporate Action layer.

## حالات التشغيل

```text
CURRENT_STATUS_AND_CA_SCHEDULE_READY
```

تعني أن Current Status Snapshot اجتازت العقود وأن Official Schedule Rows جُمعت، لكن Action Type وFactors ما زالت Pending.

```text
CURRENT_STATUS_AND_CA_ZERO_RESULT_READY
```

تعني أن Corporate Actions query المراجعة أعطت Zero Result للأسهم الخمسة خلال النافذة، مع نجاح Current Status Snapshot. لا تعني أن خارج النافذة خالٍ من الإجراءات.

```text
PARTIAL
```

تعني نجاح إحدى الطبقتين وفشل الأخرى.

```text
BLOCKED
```

تعني عدم وجود مخرج صالح.

## ما لا تزال المرحلة لا تثبته

- Historical suspension intervals.
- Resumption dates.
- Historical ticker or market-segment changes.
- Corporate Action Type and Amount.
- Adjustment Factors.
- Rights issue subscription economics.
- Capital reduction conversion factors.
- Benchmark history.
- Official Complete Daily EOD.
- Real Backtest أوForecast أوProbability أوRecommendation أوAccuracy.

## المرحلة التالية

بعد قبول هذه المرحلة، تكون الخطوة المنطقية التالية:

```text
Corporate Action Disclosure Enrichment + Adjustment Factors
```

وبالتوازي:

```text
Historical Suspension and Resumption Notices
```

ثم يأتي Benchmark History وOfficial Complete Daily EOD قبل السماح بأي Backtest حقيقي.
