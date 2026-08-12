# الحالة الحالية لـData Foundation Pilot

تاريخ اللقطة: `2026-08-12`

السلسلة التاريخية التي أصبحت مدمجة في `main`:

```text
build/data-foundation-v0.2
  └── build/official-identity-calendar-v0.2
        └── build/security-status-corporate-actions-v0.2
              └── build/ca-enrichment-status-history-v0.2
                    └── ops/codex-control-center-v0.1
                          └── build/benchmark-official-eod-v0.2
```

الفرع النشط غير المدمج:

```text
main@be5fe3883016dedf07fa680905f7199f3906b4d8
  └── build/tri-security-pilot-v0.3
```

قاعدة المرحلة الحالية:

```text
main@be5fe3883016dedf07fa680905f7199f3906b4d8
```

## طبقة Price History

- Pilot محدود إلى NBK وKFH وMABANEE وZAIN وHUMANSOFT.
- Vendor Mapping منفصلة عن Official Identity.
- Authorized User Export مرتبط بـCollection Manifest وSHA-256.
- `research_price_history.csv` منفصلة عن Official Complete `daily_eod`.
- لا Synthetic Prices ولاForward Fill ولاحقول سوقية مخترعة.

## طبقة الدفعات الثلاثية

- سجل صارم لثلاث دفعات، كل واحدة ثلاثة أسهم بالضبط.
- نقطة البدء: `KFH` و`SHIP` و`AZNOULA`.
- الدفعتان اللاحقتان توسعان فئات المصدر من دون تغيير المقام الثلاثي.
- كل الهويات في السجل `UNVERIFIED_SEED` ولا تصبح رسمية من دون بايتات
  رسمية مؤرخة ومربوطة بـSHA-256.
- إنشاء Workspace لا يجمع بيانات، ولا يجيز الانتقال إلى الدفعة التالية، ولا
  يثبت Backtest readiness.
- CLI تعيد حساب Manifest Hashes عند استخدام `--pilot-config-dir`، لكن Window
  وBatch-plan receipt لم تُربطا بعد بكل مخرج Downstream؛ المرحلة Preparation
  وليست Qualification end-to-end.
- كل دفعة تحمل البوابات النهائية الاثنتي عشرة بالحالة
  `PENDING_EXTERNAL_EVIDENCE`.

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

### Benchmark History

- Registry يميز `BROAD_MARKET` عن `SECTOR` و`PRICE_INDEX` عن `TOTAL_RETURN_INDEX`.
- Workspace وmanifest منفصلان لكل سلسلة مع SHA-256 وWindow وPagination وRights.
- التطبيع يطابق الجلسات الرسمية ولا يستخدم Forward Fill أوBenchmark بديل.
- أكواد Registry الحالية داخلية و`UNVERIFIED_SEED`؛ لذلك لا تثبت وحدها Provider History حقيقية.

### Official Complete Daily EOD

- Pipeline مستقلة عن `research_price_history`.
- Denominator هو كل `security_code × official trading session` داخل النافذة.
- كل زوج له صف واحد وحالة صريحة، بما فيها `NO_TRADE` و`SUSPENDED` و`HALTED`.
- Provider conflicts تدخل Quarantine، وغياب حقل رسمي لا يُعوّض باشتقاق ثانوي.
- Licensed imports تحتاج Runtime Trust Registry خارج Evidence Packet لإثبات authority/entitlement، لكنه شرط لازم غير كافٍ: لا تصبح البايتات Real Evidence من دون إيصال التقاط خارجي مصادق عليه يربط SHA-256 والنافذة والاستعلام والمصدر.

### Final Data Foundation Reconciliation

- أمر واحد يعيد قراءة البايتات واحتساب Hashes ولا يثق في Status محفوظ وحده.
- التقرير يخرج البوابات الاثنتي عشرة المطلوبة بترتيب ثابت.
- Upstream manifests القديمة لا تحتوي Evidence Classification وRights hash-bound؛ لا يجوز استنتاج Real Evidence من `source_id` أو`review_status`.
- `KU-BO-008-D01` ما زال مفتوحًا، ولذلك `outcome_session_policy` متعمد أن يبقى `UNFROZEN`.
- بوابة `PRICE_CORPORATE_ACTION_QA` تربط factor/policy بالهوية الفعالة والتقويم والحالة وEOD داخل النافذة، وتفصل معاملة السهم عن Basis الـBenchmark؛ أي Security Code مجهول أوتعارض فعلي يحجب البوابة.
- Schema v1 يمنع `FROZEN` بالكامل؛ commit لخيار 1 العالمي لا يحسم القرار،
  والمسار المستقبلي يحتاج عقدًا product-specific وإيصال قرار موافقًا عليه.
- لذلك يرفض `ForecastLedger` تسجيل due date ذاتي حتى لو كان بعد `decision_at`،
  ويرفض التقييم الحقيقي legacy gates أوcaller hash sets وحدها. لا توجد Metrics
  حقيقية قبل Policy product-specific موافق عليها، وحل جلسات رسمي مربوط بالحالة، وFinal Authority Receipt مستقل.
- الاختبارات التركيبية فقط تستطيع استخدام `SYNTHETIC_CONTRACT_ONLY` صراحة؛
  نتيجتها non-claim و`metrics=null` دائمًا، وسجلها لا يمر `PASS` ولا يقبل seal.
- لا توجد بيانات Benchmark أوEOD حقيقية داخل Git؛ العقود والـfixtures لا ترفع الحالة إلى Backtest Ready.
- لا يوجد بعد Final Authority Receipt مستقل مصادق عليه؛ لذلك يرفض runtime والـschemas أي READY محفوظ أوذاتي الهاش حتى يُنفّذ هذا الجذر الخارجي ويُتحقق منه.

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
- Benchmark real-evidence جاهز؛ الموجود Contract وWorkspace فقط.
- Official Complete EOD real-evidence جاهز؛ الموجود Contract وWorkspace فقط.
- Data Foundation مكتملة أوBaseline Backtest مسموح.
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
FREEZE_OUTCOME_AND_RIGHTS_RETURN_POLICY
VERIFY_OFFICIAL_BENCHMARK_DEFINITIONS_AND_RIGHTS
IMPORT_REAL_RIGHTS_COMPATIBLE_BENCHMARK_HISTORY
IMPORT_REAL_COMPLETE_OFFICIAL_OR_LICENSED_DAILY_EOD
UPGRADE_LEGACY_UPSTREAM_EVIDENCE_CLASSIFICATION_AND_RIGHTS
PASS_FINAL_REAL_DATA_FOUNDATION_RECONCILIATION
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
Benchmark Registry, History, Basis, and Calendar Gates
Official Daily EOD Denominator, Status, Evidence, and Totals Gates
Final Twelve-Gate Data Foundation Reconciliation
Synthetic Smoke Check
Secret Guard
Wheel Build and Reinstallation
Installed CLI Checks
```
