# الحالة الحالية لـData Foundation Pilot

تاريخ اللقطة: `2026-08-09`

سلسلة الفروع المتراكمة:

```text
build/data-foundation-v0.2
  └── build/official-identity-calendar-v0.2
        └── build/security-status-corporate-actions-v0.2
              └── build/ca-enrichment-status-history-v0.2
```

قاعدة المرحلة الحالية:

```text
build/security-status-corporate-actions-v0.2@e624c7f847b93192596fe31532efee7842d537d6
```

## طبقة Price History

- Pilot محدود إلى NBK وKFH وMABANEE وZAIN وHUMANSOFT.
- Vendor Mapping منفصلة عن Official Identity.
- Authorized User Export مرتبط بـCollection Manifest وSHA-256.
- `research_price_history.csv` منفصلة عن Official Complete `daily_eod`.
- لا Synthetic Prices ولاForward Fill ولاحقول سوقية مخترعة.

## Current Official Identity and Calendar

- مصالحة Security Code وISIN وTicker والاسم عبر مصدرين رسميين.
- Primary وSupporting Evidence Hashes لكل Security Master row.
- Current Identity موسومة بـ`CURRENT_SNAPSHOT_ONLY`.
- Trading Calendar لسنة 2026 مبني على Official Holidays وTrading Weekdays وSession Regime.
- Listing Date لا تُستخدم بدل Effective-Dated Identity History.

## Current Status and Corporate Action Schedule

- Current `TRADING` أو`SUSPENDED` row لكل سهم.
- Official Delisting Archive.
- Corporate Action Schedule dates مع Query/Pagination receipt.
- Pilot Action rows لا تقبل إلا بعد مطابقة Security Code وTicker وISIN.
- Action Type وAmount وAdjustment Factor بقيت Pending في المرحلة السابقة.

## ما أضيف في المرحلة الحالية

### Corporate Action Disclosure Enrichment

- Workspace مستقلة لكل Pending Action.
- ربط Schedule Row ببصمتها حتى لا يُثرى Action مختلف بالخطأ.
- Raw Official Disclosure وReviewed UTF-8 Text Export وEvidence Phrases.
- Official Previous Close Evidence عندما يحتاج الحساب سعرًا سابقًا.
- أربعة مفاهيم مستقلة داخل Factor Ledger:

```text
Reference Price Factor
Historical Continuity Factor
Position Quantity Multiplier
Return Price Multiplier
```

- Cash Dividend يستخدم Raw Price plus Cash Component في Return Engine.
- Bonus وSplit وReverse Split تستخدم Quantity Multiplier عند وضوح Fractional Entitlement policy.
- Rights Issue يحسب Mechanical TERP فقط، ويظل Return Engine محجوبًا حتى تثبيت Exercise/Sale/Lapse policy.
- Capital Reduction وMerger والإجراءات الغامضة تبقى `NO_AUTOMATIC_FORMULA` ما لم يوجد Official Factor أوOfficial Reference Price صالح.
- إنشاء `corporate_action_return_policy_queue.csv` لأي Action غير جاهزة للعائد.

### Historical Suspension and Resumption Notice Ledger

- Query Receipt مستقلة لكل سهم ولكل History Window.
- Official Opening State Evidence بدل نسخ Current Status إلى الماضي.
- Notice types محدودة إلى:

```text
SUSPEND
RESUME
DELIST
RELIST
```

- Raw Notice وReviewed Text Export وClassification Phrase مرتبطة ببصمات.
- Transition engine يمنع Resume أثناء TRADING أوSuspend أثناء SUSPENDED أوتعارض حدثين في اليوم نفسه.
- إنشاء Daily Inclusive Status Intervals داخل Window المعلنة.
- الحالة النهائية المعاد بناؤها يجب أن تطابق Current Snapshot عند نهاية النافذة.

## الحالات القصوى الممكنة

### Corporate Action

```text
CA_ENRICHMENT_READY
```

تعني أن كل Actions قبلت وأن Return treatment مكتملة.

```text
CA_REFERENCE_FACTORS_READY_RETURN_POLICY_PENDING
```

تعني أن Factors قابلة للتدقيق، لكن بعض Rights أوComplex Actions ما زالت تحتاج Return policy.

```text
CA_ENRICHMENT_ZERO_RESULT_READY
```

تعني أن Upstream Schedule لم تحتو Pending Actions داخل Pilot والنافذة.

### Status History

```text
HISTORICAL_STATUS_INTERVALS_READY
```

تعني اكتمال Status Intervals داخل `history_window_from` إلى `history_window_to` فقط.

## ما لا تزال الحالات السابقة لا تعنيه

- Mechanical Factor أصبح Official Factor.
- Reference-price adjustment أصبح Return multiplier.
- Reviewed Text Export أصبحت Original Disclosure.
- Rights TERP أصبح Execution Receipt.
- Status History خارج النافذة مكتملة.
- Historical Point-in-Time Universe كامل للسوق.
- Benchmark جاهز.
- Official Complete EOD جاهز.
- Data Foundation كاملة.
- Backtest أوForecast أوProbability أوRecommendation أوAccuracy مسموح.

## البيانات غير المرفوعة إلى GitHub

لا يحتوي الفرع على:

- Real Market CSV.
- Official disclosures أوnotices فعلية.
- Official rendered query captures فعلية.
- Browser sessions أوCookies.
- Credentials أوTokens.
- Drive identifiers.

جميع ملفات Runtime وRaw Evidence تبقى خارج Git.

## البوابات التالية

```text
RETURN_POLICY_FOR_RIGHTS_AND_COMPLEX_ACTIONS
BENCHMARK_HISTORY
OFFICIAL_COMPLETE_DAILY_EOD
FULL_DATA_FOUNDATION_RECONCILIATION
REAL_BASELINE_BACKTEST
```

## معيار القبول

المرجع الوحيد لقبول الكود هو GitHub Actions على أحدث Head للـPull Request، وتشمل:

```text
Compile
Full Unit and Adversarial Suite
Source Parser and Live-Probe Gates
Official Identity and Calendar Gates
Current Status and Corporate Action Schedule Gates
Corporate Action Formula and Enrichment Gates
Historical Status Notice and Interval Gates
Synthetic Smoke Check
Secret Guard
Wheel Build and Reinstallation
Installed CLI Checks
```
