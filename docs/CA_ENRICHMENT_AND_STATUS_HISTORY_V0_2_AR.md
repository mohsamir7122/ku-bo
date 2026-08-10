# Corporate Action Enrichment and Historical Status v0.2

## موقع هذه المرحلة

هذه المرحلة مبنية فوق السلسلة التالية:

```text
Research Price History
Current Official Identity
2026 Trading Calendar
Current Security Status Snapshot
Official Corporate Action Schedule
```

وتضيف مسارين مستقلين:

```text
Corporate Action Disclosure Enrichment
Historical Suspension and Resumption Notice Ledger
```

الفصل بينهما مقصود. Corporate Action يغيّر المقارنة السعرية أوعدد الأسهم أوالتوزيع النقدي، بينما Suspension يغيّر قابلية تنفيذ القرار وتاريخ النتيجة. دمجهما في ملف واحد كان سيجعل أي Failure في أحدهما غامضًا.

## المسار الأول: Corporate Action Disclosure Enrichment

### المشكلة التي يعالجها

صفحة Corporate Actions الرسمية تثبت مواعيد مثل Cum Date وEx Date وRecord Date وPayment Date، لكنها لا تكفي وحدها لإثبات:

```text
Action Type
Cash Amount per Share
Bonus Ratio
Split Ratio
Rights Subscription Price
Capital Reduction Terms
Adjustment Factor
```

لذلك تبقى صفوف المرحلة السابقة:

```text
action_type = UNCLASSIFIED_ENTITLEMENT
factor_status = pending
```

ولا تتغير إلا بعد ربطها بإفصاح رسمي من Boursa Kuwait أوiFSAH أوCMA، وبـOfficial Previous Close evidence إذا كان الحساب يحتاجه.

### إنشاء Workspace

```bash
kubo-data-foundation --project-root . prepare-ca-enrichment \
  --status-corporate-root runtime/data_foundation/status-ca-001 \
  --output-root runtime/ca_enrichment/ca-enrichment-001 \
  --run-id ca-enrichment-001 \
  --prepared-by "authorized-user"
```

يقرأ الأمر Upstream Schedule وEnrichment Queue، ويثبت بصمتيهما، ثم ينشئ لكل Action:

```text
Raw official disclosure placeholder
Reviewed UTF-8 text export placeholder
Official previous-close evidence placeholder
Terms object
Schedule-row SHA-256
```

وجود Workspace أوText Export لا يثبت المعلومة. يجب أن يكون Raw Disclosure رسميًا، وأن يكون Text Export مشتقًا منه ومراجعًا، وأن تظهر Evidence Phrases المحددة حرفيًا داخل النص.

### الاستيراد

```bash
kubo-data-foundation --project-root . import-ca-enrichment \
  --status-corporate-root runtime/data_foundation/status-ca-001 \
  --workspace runtime/ca_enrichment/ca-enrichment-001 \
  --output-root runtime/data_foundation/ca-enrichment-001
```

المخرجات:

```text
normalized/corporate_action_factor_ledger.csv
normalized/corporate_action_return_policy_queue.csv
reports/ca_enrichment_import_report.json
manifest.json
ca_enrichment_manifest.json
```

## أربعة مفاهيم مختلفة لا يجوز جمعها في رقم واحد

### Reference Price Factor

هو نسبة السعر النظري أوالسعر المرجعي بعد الإجراء إلى Previous Close. يفيد في تفسير الانقطاع السعري، وقد يستخدم في بعض عمليات Price Continuity.

### Historical Continuity Factor

هو معامل ربط السلسلة قبل الإجراء وبعده عند بناء سلسلة مقارنة مستمرة. قد يساوي Reference Price Factor في بعض الإجراءات الميكانيكية، لكنه لا يتحول تلقائيًا إلى Total Return treatment.

### Position Quantity Multiplier

هو التغير في عدد الأسهم التي يمتلكها المستثمر نتيجة Bonus أوSplit أوReverse Split.

### Return Price Multiplier

هو المعامل الذي يطبق على سعر الخروج عند قياس قيمة المركز. في Cash Dividend يظل معامل السعر واحدًا، ويضاف Cash Distribution بصورة مستقلة. لذلك لا يجوز استعمال Dividend Reference Factor باعتباره Return Multiplier.

## طرق الحساب المسموح بها

### OFFICIAL_FACTOR

يستخدم فقط عندما ينص الدليل الرسمي صراحةً على Factor، ويُحفظ ذلك الدليل وبصمته. وجود Official Factor لا يكفي وحده لتجهيز Return Engine إذا كانت سياسة الحقوق أوالاندماج أوالتخفيض غير مكتملة.

### OFFICIAL_REFERENCE_PRICE

يستخدم عندما ينص الدليل الرسمي على Reference Price. يحسب النظام نسبة هذا السعر إلى Previous Close، لكنه يبقي Return treatment مستقلة.

### REPRODUCIBLE_MECHANICAL

يُسمح به فقط للإجراءات ذات المدخلات الرسمية الكاملة والصيغة الميكانيكية المحددة:

- Cash Dividend: السعر النظري بعد التوزيع هو Previous Close مطروحًا منه Cash per Share. Return Engine يستخدم Raw Price plus Cash Component.
- Bonus Shares: عدد الأسهم بعد الإجراء هو عدد الأسهم السابق مضافًا إليه Bonus Ratio؛ والسعر النظري ينخفض بما يقابل زيادة العدد.
- Stock Split وReverse Split: السعر النظري يتغير عكسيًا مع Quantity Multiplier.
- Rights Issue: يحسب النظام Theoretical Ex-Rights Price من Previous Close ونسبة الحقوق وسعر الاكتتاب، لكنه لا يسمح بتحويل ذلك إلى عائد منفذ قبل تحديد هل الحقوق مارست أوبيعت أوانقضت.

### NO_AUTOMATIC_FORMULA

يظل إلزاميًا عند:

```text
Capital Reduction
Merger
Ambiguous Rights Terms
Mixed Cash and Share Consideration
Par Value Change with incomplete mechanics
Any incomplete official disclosure
```

لا يُسمح للنظام بتخمين Factor لهذه الحالات.

## تمييز Cash Dividend العادي والخاص

يحفظ النظام نوعين منفصلين:

```text
CASH_DIVIDEND_NORMAL
CASH_DIVIDEND_SPECIAL
```

في النوعين يمكن حساب Dividend-adjusted theoretical price عند توافر Previous Close وCash Amount. لكن الاستخدام السوقي للسعر المعدل ليس واحدًا: Cash Dividend العادي يُعامل في Return Engine كـRaw Price plus Cash، بينما Special Cash قد يرتبط أيضًا بـTrading Reference وفق القاعدة الرسمية السارية.

## Fractional Entitlements

Bonus وSplit وReverse Split لا تصبح Return-engine ready إلا إذا كانت سياسة الكسور واضحة، مثل:

```text
NOT_APPLICABLE
EXACT_FRACTIONAL_ENTITLEMENT
```

أما:

```text
ROUND_DOWN
CASH_IN_LIEU
UNKNOWN
```

فتحتاج Evidence أوPolicy إضافية قبل قياس العائد النهائي.

## حالات Corporate Action Enrichment

```text
CA_ENRICHMENT_ZERO_RESULT_READY
```

تعني أن Upstream Schedule لم تحتو Actions داخل Pilot والنافذة المحددة.

```text
CA_ENRICHMENT_READY
```

تعني أن كل Actions قبلت وأن Return treatment لكل منها مكتملة.

```text
CA_REFERENCE_FACTORS_READY_RETURN_POLICY_PENDING
```

تعني أن Reference/Continuity factors أصبحت قابلة للتدقيق، لكن بعض الإجراءات مثل Rights ما زالت تحتاج سياسة عائد منفصلة.

```text
PARTIAL
```

تعني وجود إفصاحات غير مراجعة أوFactors غير مكتملة.

```text
BLOCKED
```

تعني وجود تعارض أوHash mismatch أوEvidence Phrase غير موجودة أوUpstream receipt قديمة.

## المسار الثاني: Historical Suspension and Resumption Notice Ledger

### لماذا Current Snapshot لا تكفي؟

Current Suspended Companies page تثبت حالة وقت الجمع فقط. لا تثبت أن السهم كان قابلًا للتداول في تاريخ سابق، ولا تكشف كل فترات الإيقاف والاستئناف.

لذلك تبني هذه المرحلة Status History داخل Window معلنة، اعتمادًا على:

```text
Official Opening State Evidence
Complete Historical Disclosure Query Receipt لكل سهم
Official SUSPEND Notices
Official RESUME Notices
Official DELIST Notices
Official RELIST Notices
Current Snapshot reconciliation
```

### إنشاء Workspace

```bash
kubo-data-foundation --project-root . prepare-status-history \
  --status-corporate-root runtime/data_foundation/status-ca-001 \
  --output-root runtime/status_history/status-history-001 \
  --run-id status-history-001 \
  --history-window-from 2021-01-01 \
  --history-window-to 2026-08-09 \
  --prepared-by "authorized-user"
```

يجب أن يساوي `history-window-to` تاريخ Current Status Snapshot القادم من Upstream.

ينشئ الأمر لكل سهم:

```text
Historical disclosure query placeholder
Opening state evidence placeholder
Query contract
```

وينشئ Notice Template لإضافة Events.

### الاستيراد

```bash
kubo-data-foundation --project-root . import-status-history \
  --status-corporate-root runtime/data_foundation/status-ca-001 \
  --workspace runtime/status_history/status-history-001 \
  --output-root runtime/data_foundation/status-history-001
```

المخرجات:

```text
normalized/opening_status_evidence.csv
normalized/status_notice_ledger.csv
normalized/status_intervals.csv
manifests/status_query_ledger.csv
reports/status_history_validation_report.json
reports/status_history_import_report.json
manifest.json
```

## Query Completeness

لكل سهم يجب تسجيل:

```text
Pages Declared
Pages Received
Result Count Declared
Rows Normalized
Zero Result
Raw SHA-256
```

Zero Result لا يقبل إلا عند وجود Rendered Query Receipt كاملة، وتطابق الصفحات والأعداد، وعدم وجود Notice rows لذلك Query.

Query Receipt هي Operator Attestation مربوطة بالبايتات، وليست Market Fact مستقلة.

## Opening State

لا يسمح النظام بنسخ Current Status إلى بداية النافذة. يجب وجود Official Evidence مستقلة تثبت حالة السهم في `history_window_from`.

الحالات الافتتاحية الممكنة:

```text
TRADING
SUSPENDED
DELISTED
```

## التحولات المسموح بها

```text
TRADING ثم SUSPEND ثم SUSPENDED
SUSPENDED ثم RESUME ثم TRADING
TRADING أوSUSPENDED ثم DELIST ثم DELISTED
DELISTED ثم RELIST ثم TRADING
```

أي Resume أثناء TRADING، أوSuspend أثناء SUSPENDED، أوتعارض انتقالين في اليوم نفسه، يُحجب.

## بناء الفترات

يبني النظام فترات Daily Inclusive متصلة. كل فترة تحمل:

```text
Security Code
Ticker
Status
Effective From
Effective To
Opening Evidence SHA-256
Start Notice ID
End Notice ID
All Evidence Hashes
```

بعد تطبيق كل Notices، يجب أن تساوي الحالة النهائية Current Snapshot عند نهاية النافذة. عدم التطابق يعني أن Query ناقصة أوافتتاح الحالة خطأ أوNotice لم تُلتقط.

## حالة Status History

```text
HISTORICAL_STATUS_INTERVALS_READY
```

تعني أن الفترات اكتملت داخل النافذة المعلنة فقط.

ولا تعني أن:

```text
التاريخ قبل النافذة مكتمل
كل Intraday Halt ممثل
كل أسباب الإيقاف مصنفة
Backtest أصبح جاهزًا
```

## البوابات التي تبقى بعد هذه المرحلة

حتى بعد نجاح المسارين، تبقى:

```text
Return Policy for Rights and Complex Actions
Benchmark History
Official Complete Daily EOD
Full Data Foundation Reconciliation
Real Baseline Backtest
```

ولا ينتج هذا الفرع Forecast أوProbability أوRecommendation أوAccuracy.
