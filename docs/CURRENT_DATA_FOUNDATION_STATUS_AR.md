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

الحالة المتحققة عند بدء `KU-BO-012`:

```text
main@92b2bdd2460a7508922297a12d85f13264d43acb
  └── PR #1 and PRs #4-#13 already integrated
        └── agent/kuwait-120d-next-session
              └── KU-BO-012 / IN_PROGRESS / DRAFT / MERGE_ALLOWED NO
```

قاعدة المرحلة الحالية:

```text
main
@92b2bdd2460a7508922297a12d85f13264d43acb
```

PR #1 وPRs #4 إلى #13 أسلاف لـ`main` ولا تحتاج دمجًا آخر. PR #2 وPR #3
قديمتان، متأخرتان 127 Commit، وغير قابلتين للدمج المباشر ومتجاوزتان بالعقود
الحالية؛ يمنع دمجهما أوCherry-pick شامل منهما. فرع المهمة الحالي هو
`agent/kuwait-120d-next-session`، ونُشر في Draft PR #14 عند رأس التنفيذ
`58a78042d5d509e599d2e273d793856b1dee14dd`، ونجح Exact-head CI Run
`31733924569` على Python 3.11 إلى 3.14. لم يحدث Merge. التفويض
`KU-BO-MERGE-004` شرطي، وتبقى الحالة `MERGE_ALLOWED: NO` أثناء التنفيذ.

## امتداد KU-BO-012 فوق Data Foundation

يضيف المنتج `KUWAIT_120D_NEXT_SESSION_RESEARCH` سياقًا تراكميًا 120 يومًا،
مع نوافذ 30 يومًا للأحداث النشطة و7 أيام للمجتمع و72 ساعة للمحفز الحديث.
يسجل المحاولات في موجات محدودة، ثم يطبّع Context Events وSecurity Exposure
وFactor Snapshots ويصدر صف مقام لكل ورقة متوقعة. Telegram وIndexSignal
للمزاج أوالتوجيه فقط.

يعيد Persisted Source Search validator حساب بصمات التقرير وسجل المحاولات
والـRaw artifacts قبل دمجها. ويضيف `kuwait_research_pipeline` مع
`parsed-research-inputs.schema.json` وأمر `build-kuwait-research-bundle` جسرًا
ذريًا إلى Context/Exposure/Factor artifacts. الجسر لا يدعي Parser عامًّا ولا
يستنتج قيمًا أودرجات من Raw bytes.

الكتالوج على الفرع يحتوي 68 تعريف مصدر و62 مجموعة استقلال و59 نطاقًا مرشحًا
بعد استبعاد البحث والتخزين. منها 53 نطاقًا معلنًا Enabled-public، و52 نطاق
Start URL تنفيذيًا مميزًا قبل الحجز. الخطة العادلة تختار 50 بمساهمات
`17/0/29/4`، وتحجز الموجة الأخيرة للأرشيف و`t.me` و`indexsignal.com`؛ Search
Router مسجل وغير منفذ. حالة القدرة: 66 `DEFINED_ONLY`، و2
`END_TO_END_TESTED` على Fixtures مولدة، و0 `LIVE_OPERATIONAL`.

المحاولات Fail-stop: Hard block لا يعاد، و429 يتوقف بعد ثلاث محاولات في
الاستراتيجية نفسها، ويحترم `Retry-After` ضمن ميزانية الوقت. تجاوز الميزانية
أوفشل Sleeper يوقف المسار. يحفظ Ledger القيود وDisposition وRetry-After، مع
Non-claims صريحة حول External Seal وPublication time وLow-level metering وParser
cutoff وZero-result proofs.

تربط `factor_snapshot_sha256` الصفوف والعوامل والأدلة والتصرفات والدرجات
كاملة، ويُشتق `snapshot_id` منها. تُفرض Freshness من Registry، بما فيها 24
ساعة لحالة التداول، ولا يدخل حدث `SUPERSEDED` في Factor-eligible exposure.
أما Replay فيعيد اشتقاق Rank من Score ويفرض Top-K وFill موثقًا لأن المنتج
Execution-grade. Primary label هو adjusted gross return قبل التكاليف؛ تستخدم
التكاليف في Actionable وNet-excess metrics الثانوية.

عقد الإعادة التاريخية يحتاج 40 قرارًا و41 جلسة رسمية متتالية مع Real
Point-in-Time Universe وEOD وBenchmark وStatus وCorporate Actions وFeatures
وOutcomes منفصلة. هذه الحزمة غير موجودة؛ لذلك نتيجة الأربعين الأخيرة هي:

```text
status=STOP_BACKTEST
process_valid_scoreable_sessions=0
expected_decision_sessions=40
metrics=null
agreement_rate=null
agreement_rate_status=NOT_APPLICABLE
authority_receipt_sha256=null
authority_verified=false
accuracy_claim_allowed=false
```

تُعرض `agreement_rate=null/NOT_APPLICABLE` بشريًا `N/A` ولا تعني `0%`؛ لا
يوجد مقام مؤهل للحساب. يبقى `KU-BO-008-D01` `OPEN`، ولا توجد سياسة
Product-specific مجمدة لعبور التعليق أوالتوقف. لذلك يبقى Non-trading member في
المقام لكنه يوقف Replay بدل حذفه أوتوليد Close اصطناعي. لا يعلن Runtime حالة
`STOP_INFERENCE` غير قابلة للوصول.

التحقق المركز المسجل على رأس KU-BO-012 نجح `183/183` لاختبارات Workflow/Source
Orchestrator/Context/Integration/Replay/CLI، ونجح Full Suite الخاص بذلك الرأس
`2,067/2,067` في `164.347s`. كما نجح `compileall` وJSON وDiff وSmoke
وSecret Guard، وتوليد وتدقيق Corpus من `1,280` حالة، وCodex control
على 15 ملف تحكم و10 ملفات مطلوبة بلا Errors أوWarnings. نجحت Wheel
النهائية بحجم `444351` بايت وSHA-256
`ee089ec3a7e100e81e1ef4a0378824c2b3e817db7d4c23d2d197b728b400c3a3`، ونجح
التثبيت المعزول وImports وCLI help و`validate-research-workflow`، ونجح
`installed_data_foundation_check` مع 8 Semantic admissions و8 Lineages. أضيفت
Gates المركزة إلى CI، ونُشرت في Draft PR #14؛ نجح Run `31733924569` للرأس
`58a78042d5d509e599d2e273d793856b1dee14dd`. لم يحدث Merge، وتغيير سجل التحكم
اللاحق احتاج Exact-head CI جديدًا قبل مراجعة حد الدمج. نتائج الشجرة الأحدث
الخاصة بـKU-BO-014 موثقة في `docs/BUILD_STATUS_AR.md` ولا تغيّر بوابات Data
Foundation الخارجية الواردة هنا.

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
  ونجح Exact-head CI المنشور؛ ومع ذلك المرحلة ليست Qualification end-to-end
  لأن الإثبات اصطناعي ولا يحتوي Market Evidence.
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

هذه هي الحالة التاريخية لـPR #12 ولا تتغير بأثر رجعي. أما فرع التنفيذ آنذاك
فرفع Corpus إلى v3 بعقد Materialization تنفيذي مستقل، ونجح Generator/Audit
محليًا ببصمة:

```text
e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288
```

التمييز الملزم هو: PR #12 تظل `TEST_SPEC_ONLY`، بينما PR #13 تثبت
`CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT / SYNTHETIC_ONLY` على Head منشور
وناجح في CI، من دون أي ترقية لادعاءات السوق.

## النطاق التاريخي لتنفيذ KU-BO-011 المدمج

هذه فقرة تاريخية تصف ما أضافه فرع KU-BO-011 قبل دخوله في
`main@92b2bdd2460a7508922297a12d85f13264d43acb`:

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

هذه النتائج المنشورة تثبت كودًا وسلوكًا خصوميًا اصطناعيًا فقط. لا تثبت
Market Data أوProvider/Capture Authority أوRights أوReal Backtest أوForecast
أوProbability أوAccuracy أوRecommendation أوProduction Readiness.

كان دليل التنفيذ قد نُشر على Draft PR #13 عند
`6dc821f8342bf2041ac3bed983c6805ff0a2c3fc` ونجح Exact-head CI Run
`31695010037` على Python 3.11 إلى 3.14، ثم أصبح هذا التاريخ ضمن `main` الحالي.
لا يُعاد استخدام ذلك CI كإثبات لـKU-BO-012، ولا يثبت Market Evidence أوReal
Backtest أوForecast أوProbability أوAccuracy أوRecommendation أوProduction
Readiness.

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
COMPLETE_KU_BO_012_LOCAL_ACCEPTANCE_SUITE
PUBLISH_KU_BO_012_DRAFT_PR
PASS_KU_BO_012_EXACT_HEAD_GITHUB_ACTIONS
RECHECK_KU_BO_MERGE_004_AT_MERGE_BOUNDARY
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
KU-BO-012 Workflow, Source Search, Context, Integration, Factor, Replay, and CLI Gates
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
Installed KU-BO-012 Workflow/Search/Replay Command Checks
```
