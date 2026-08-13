# الحالة الحالية لـData Foundation Pilot

تاريخ اللقطة: `2026-08-13`

السلسلة التاريخية التي أصبحت مدمجة في `main`:

```text
build/data-foundation-v0.2
  └── build/official-identity-calendar-v0.2
        └── build/security-status-corporate-actions-v0.2
              └── build/ca-enrichment-status-history-v0.2
                    └── ops/codex-control-center-v0.1
                          └── build/benchmark-official-eod-v0.2
                                └── build/tri-security-pilot-v0.3
                                      └── build/tri-security-run-receipt-v0.1
```

الحالة الحية بعد دمج PR #12 كحزمة اختبارات فقط:

```text
main@c621fcf88034c4571aa08aee2e54e2e026a4f651
  └── PR #12 merged / TEST_SPEC_ONLY
        └── Post-merge CI 31684299396 PASS
              └── build/tri-security-receipt-enforcement-v0.2
                    @5e5b4ad9237ccaff04974576a3c77b2058a79b8f
```

قاعدة المرحلة الحالية:

```text
main
@c621fcf88034c4571aa08aee2e54e2e026a4f651
```

فرع تنفيذ `KU-BO-011` المحلي هو
`build/tri-security-receipt-enforcement-v0.2`. يتضمن `main` بعد دمج PR #12،
وImplementation Code Head قبل Commit سجلات التحكم الحالية هو
`5e5b4ad9237ccaff04974576a3c77b2058a79b8f`. حالته `IN_PROGRESS`؛ نجحت
بواباته المحلية، لكن لا يوجد Implementation Draft PR منشور أوExact-head CI
خاص به بعد.

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
- عقد KU-BO-010 يعيد حساب Batch Plan وScoped Config Manifest وWorkspace
  Report، ثم يربط Run/Batch/Cohort/Window في Run Receipt خارجي مصادق عليه.
- Stage Binding بمفتاح مستقل يربط Manifest والجرد المعلن وشجرة ملفات المرحلة
  كاملة، ويكشف الإضافة أوالحذف أوالتغيير أوخلط تشغيل آخر.
- إعداد Benchmark الموروث غير متوافق مع قطاعي Industrials وUtilities في
  الدفعة الثلاثية، لذلك يبقى Qualification محجوبًا صراحة ولا يجوز إعادة
  استخدام مقام Pilot الخماسي.
- بقي Stage Binding v1 عقد سلامة بايتات فقط ولم يتغير ادعاؤه
  `binding_proves_stage_matches_run_scope=false`. أضاف فرع KU-BO-011 عقد
  Semantic Admission v2 منفصلًا بمفتاح ثالث مستقل، وفرضه في Direct API وCLI
  لكل Importer وفي Final Reconciliation. نجح إثبات Adapter الاصطناعي محليًا
  في 1,280/1,280 حالة من Source Tree و1,280/1,280 من Clean Installed Wheel،
  لكن Exact-head CI لم يكتمل بعد؛ لذلك المرحلة ليست Qualification end-to-end.
- كل دفعة تحمل البوابات النهائية الاثنتي عشرة بالحالة
  `PENDING_EXTERNAL_EVIDENCE`.

## حزمة قبول KU-BO-011

PR #12 مدمجة الآن في `main` كحزمة **Test Specification اصطناعية فقط**:

```text
8 importer/reconciliation boundaries
x 40 mutation families
x 4 attack channels/timings
= 1,280 deterministic case specifications
```

بصمة Corpus هي
`53c95afbdf4174a5c3e74c2bfb798beddc650841f1301d4b8d99bc4a54af2b03`.
نجح Exact-head CI على Python 3.11 إلى 3.14 وشغّل 1,841 Test مع فحوص
التوليد الحتمي وSchema والبصمات الدلالية وWheel وInstalled CLI وSmoke
وControl وSecret Guard. ثم دُمجت PR #12 في `c621fcf` ونجح Post-merge CI
`31684299396`.

هذا النجاح يثبت سلامة **مواصفات الاختبار وبنيتها** فقط، ولا يثبت أن أي
Importer تفرض Run Receipt أوStage Binding. من دون Implementation Adapter
يعيد الوضع الصارم `TARGET_ADAPTER_UNAVAILABLE`. وحتى بعد إضافة Adapter يجب
أن تستدعي Production APIs وCLIs الحقيقية، ولا يجوز أن تنجح بمجرد إعادة
القيم المتوقعة من Test Case. لذلك يبقى ادعاء PR #12:

```text
TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM
```

هذه هي الحالة التاريخية لـPR #12 ولا تتغير بأثر رجعي. أما فرع التنفيذ الحالي
فرفع Corpus إلى v3 بعقد Materialization تنفيذي مستقل، ونجح Generator/Audit
محليًا ببصمة:

```text
e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288
```

التمييز الملزم هو: PR #12 تظل `TEST_SPEC_ONLY`، بينما Head التنفيذ يثبت
`CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT` **محليًا فقط**.

## نطاق تنفيذ KU-BO-011 الحالي

الحالة `IN_PROGRESS`. أضاف الفرع الحالي:

- Semantic Stage Admission v2 بعقد وإصدار مستقلين ومفتاح HMAC ثالث لا يساوي
  مفتاح Run أومفتاح Stage؛
- إبقاء `Stage Binding v1.0` Byte-integrity contract فقط من دون تغيير
  `binding_proves_stage_matches_run_scope=false`؛
- فرض المصادقة والربط الدلالي في Direct API وCLI للـImporters السبعة
  وFinal Reconciliation؛
- ربط Run/Batch/Cohort/Window/Stage والـPredecessor graph الفعلية وأدوار
  المدخلات الدقيقة؛
- رفض أي Input مفقودة أومزورة أومنتهية أومخلوطة أوغير متوافقة قبل إنشاء
  Output؛
- Atomic staging بلا overwrite مع إعادة التحقق قبل Commit لمقاومة TOCTOU؛
- أمر CLI لإصدار Semantic Admission وبناء `BoundaryAdmissionRequest` من
  مفاتيح Runtime-only وأدلة Predecessor؛
- Schema صارمة JSON Schema 2020-12 في
  `schemas/tri-security-semantic-admission.schema.json` تمنع الحقول الزائدة
  وتثبت أزواج Boundary/Stage وأدوار المدخلات ومجموعات Predecessor المرتبة؛
- Adapter لا يستورد `expected` أوMutators الاختبارات، ويملك عقدًا مستقلًا
  لـArtifact/Field/Action/Timing/Resign Policy/Value، ويستدعي Public Boundary
  الحقيقي لكل حالة؛
- نجح Strict Source Adapter وClean Installed Wheel Adapter في 1,280/1,280
  لكل منهما مع عدم إنشاء Protected Output عند الرفض؛
- نجح Installed Authenticated DAG للحدود الثمانية، وأنشأ وتحقق من ثمانية
  Semantic Admissions وثمانية Lineage Artifacts؛
- نجح Full Local Suite بعدد 1,916 Test؛ ونجحت فحوص Compile وCorpus
  Generator/Audit v3 وCodex Control وSynthetic Smoke وSecret Guard وDiff.

هذه النتائج تثبت كودًا وسلوكًا خصوميًا اصطناعيًا فقط. لا تثبت Market Data أو
Provider/Capture Authority أوRights أوReal Backtest أوForecast أوProbability
أوAccuracy أوRecommendation أوProduction Readiness.

المتبقي قبل الإغلاق هو تسجيل ونشر Implementation Draft PR ثم نجاح GitHub
Actions على Exact Head نفسه. لذلك Handoff الحالية `PARTIAL`، والمهمة تظل
`IN_PROGRESS`.

تفويض الدمج المرتب مسجل في `KU-BO-MERGE-003`. اكتمل جزؤه الأول بدمج PR #12
أولًا ونجاح Post-merge CI. يبقى جزء Implementation فقط، وMetadata المهمة تظل
محافظة أثناء التنفيذ: `EXPECTED_PR_MODE: DRAFT` و`MERGE_ALLOWED: NO`. لا تدمج
Implementation PR إلا بعد اكتمال Adapter والبوابات المحلية وFresh exact-head
CI.

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
- Run أوStage أوSemantic HMAC keys؛ المفاتيح Runtime-only وخارج Git.

جميع ملفات Runtime وRaw Evidence تبقى خارج Git.

## البوابات التالية

```text
PUBLISH_KU_BO_011_IMPLEMENTATION_AS_DRAFT_PR
PASS_KU_BO_011_EXACT_HEAD_GITHUB_ACTIONS
RECHECK_KU_BO_MERGE_003_AT_ORDERED_MERGE_BOUNDARY
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
