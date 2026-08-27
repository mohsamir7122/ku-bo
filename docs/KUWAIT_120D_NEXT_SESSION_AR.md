# بحث سياق الكويت 120 يومًا وتقييم الجلسة التالية

حالة الوثيقة: `DRAFT / KU-BO-012 IN_PROGRESS`

هذا المسار يترجم سؤال «ما الأسهم التي قد ترتفع في الجلسة التالية؟» إلى عملية بحث قابلة للتدقيق. هو لا يَعِد بارتفاع سهم، ولا يحول الدرجة إلى احتمال أوتوصية. الكود والعقود موجودة على فرع `agent/kuwait-120d-next-session` المبني على `main@92b2bdd2460a7508922297a12d85f13264d43acb`، لكن لا توجد بعد حزمة سوق حقيقية Point-in-Time تسمح بحساب دقة الأربعين جلسة.

## عقد المنتج

```text
product_id: KUWAIT_120D_NEXT_SESSION_RESEARCH
timezone: Asia/Kuwait
context_window: 120 calendar days
active_event_window: 30 calendar days
community_window: 7 calendar days
fresh_catalyst_window: 72 hours
outcome_horizon: next completed official trading session
primary_target: GROSS_ADJUSTED_RETURN_GT_0
secondary_targets: MARKET_NET_EXCESS_GT_0, SECTOR_NET_EXCESS_GT_0
```

السياق الأكبر يجيب: ما الذي تغير في الكويت والقطاعات والشركات خلال الأشهر الأخيرة؟ نافذة 30 يومًا تحصر الأحداث التي ما زالت نشطة، وسبعة أيام تمنع منشورًا اجتماعيًا قديمًا من تلويث المزاج الحالي، و72 ساعة تميز المحفز الأقرب للجلسة التالية.

## معنى «البحث في 50 موقعًا»

المقصود محاولة ما يصل إلى 50 **نطاقًا قابلًا للتسجيل ومميزًا**، لا جمع 50 رابطًا من ناشر واحد، ولا اشتراط 50 نتيجة، ولا اعتبارها 50 تأكيدًا مستقلًا. الكتالوج يحتوي الآن:

```text
source_definitions: 69
independence_groups: 63
candidate_research_domains: 60
declared_enabled_public_catalog_domains: 54
distinct_executable_start_url_domains: 53
default_fair_plan_domains: 50
DEFINED_ONLY: 67
END_TO_END_TESTED: 2 generated fixtures
LIVE_OPERATIONAL: 0
```

استُبعدت أسطح البحث والتخزين من رقم 60. الفارق إلى 54 هو ستة نطاقات معطلة أوLicensed (`facebook.com` و`ice.com` و`instagram.com` و`tiktok.com` و`twitter.com` و`x.com`). والفرق من 54 إلى 53 ينتج من تحويل التعريفات العامة إلى Start URLs تنفيذية مميزة. تبقى أسطح البحث والتخزين مفيدة للتوجيه أوالحفظ، لكنها لا تنشئ Finding. تكرار خبر Reuters في عدة صحف يحسب أصلًا واحدًا بعد Dedup، وكل أسطح المنصة ذات الملكية الواحدة تُعامل كمجموعة ناشر واحدة.

## ترتيب البحث

يجري البحث في أربع موجات:

1. بورصة الكويت والجهات الرسمية والرقابية؛
2. الشركات والجهات الحكومية والاقتصادية؛
3. البيانات السوقية المنظمة والصحف ووكالات الأخبار؛
4. المجتمع والأرشيف؛ أما Search Router فمسجل للتوجيه فقط ولا ينفذه المشغل الحالي.

كل تشغيل له حدود قصوى للنطاقات والطلبات والوقت. الخطة الافتراضية العادلة تختار 50 نطاقًا من 53 Start URL domain، بمساهمات جديدة `17/0/29/4`. تحجز الموجة الرابعة الأربعة الأخيرة لـ`archive.org` و`commoncrawl.org` و`indexsignal.com` و`t.me`، وبذلك لا تستهلك الموجات المبكرة الميزانية قبل Telegram وIndexSignal. أسطح مجتمع Investing/TradingView موجودة، لكنها لا تضيف نطاقين جديدين بعد احتساب ملكيتيهما في الموجة الثالثة. Corpus الـ120 يومًا تراكمي وله Watermark؛ لذلك لا يعيد التشغيل المعتاد تنزيل أربعة أشهر كاملة من كل مصدر.

## إعادة المحاولة والنتيجة الفارغة

- الأخطاء العابرة مثل Timeout وDNS وTLS وHTTP 429 وHTTP 5xx: ثلاث محاولات إجمالية لكل استراتيجية.
- Hard block لا يعاد. يظل HTTP 429 في الاستراتيجية نفسها ثم يوقف المصدر بعد المحاولة الثالثة؛ لا يغير الاستراتيجية للتحايل على Rate limit.
- يحترم `Retry-After` كما أرسله الخادم إذا وقع داخل Wall budget؛ تجاوزه للوقت المتبقي أوفشل Sleeper يوقف المسار من دون Retry إضافية.
- الاستجابة الصحيحة الفارغة: حتى أربع استراتيجيات مختلفة جوهريًا، مثل تغيير مصطلحات البحث أواللغة أوالفترة أونوع صفحة المصدر. تكرار الطلب نفسه لا يُحسب.
- Login أوCAPTCHA أوPaywall أوRobots أوExplicit denial: لا تجاوز ولا تحايل؛ تُسجل الحالة النهائية وإجراء الاسترداد الممكن.
- فشل موقع واحد: يخفض التغطية أوالثقة للسهم المتأثر، ولا يوقف الكون كله إذا ظلت الشروط الإلزامية لبقية الأسهم سليمة.

يسجل Attempt Ledger المصدر والاستراتيجية ووقت البدء والانتهاء والحالة والرابط النهائي وفئة الخطأ و`retry_after_seconds` وHash الاستجابة وMaterial query-route proof والـDisposition والـLimitations. وجود سجل للمحاولة لا يعني أن محتواها أصبح Evidence. وتصرح Limitations بأن Hash chain ليست External Seal، وCapture time ليست Publication time، وأن Low-level HTTP ليس Metered طلبًا بطلب، وأن Parser cutoff وUnique zero-result proofs يظلان مطلوبين.

بعد الحفظ يعيد Persisted-run validator فتح `source_search_run.json` وسجل المحاولات والـRaw artifacts ويعيد حساب بصماتها؛ أي تعديل لاحق في التقرير أوالسجل أوالبايتات يفشل. ثم يوفّر أمر `build-kuwait-research-bundle` جسرًا صريحًا إلى `parsed-research-inputs.schema.json`: لا يقبل Evidence hash خارج التشغيل المتحقق، ويكتب Context/Exposure/Factor artifacts والحزمة النهائية Atomically. الجسر لا يُعد Parser عامًا ولا يستنتج أحداثًا أوعوامل أوScores من Raw bytes؛ المدخلات الدلالية تظل مسؤولية Parser/QA صالح ومعلن.

## Telegram وIndexSignal

كلاهما `COMMUNITY_SENTIMENT` أو`ROUTING` فقط. قد يشيران إلى موضوع يحتاج الرجوع إلى مصدره الأصلي، وقد يدعمان قياس المزاج ضمن سقفه، لكنهما لا يثبتان منفردين:

- هوية الورقة المالية؛
- السعر أوالحجم؛
- إفصاحًا أوإجراء شركة؛
- محفزًا رسميًا أوحقيقة مالية.

تعذر الوصول إلى قناة أوصفحة، أوعودتها فارغة، يسجل في المحاولات ولا يتحول إلى «لا يوجد خبر» أوإشارة هبوط.

## من الخبر إلى صف السهم

تُطبّع الأحداث إلى `KUWAIT_MACRO` أو`SECTOR` أو`SECURITY`. وكل صلة بسهم تحمل نوع Exposure واحدًا:

```text
DIRECT_NAMED
CONTRACT_COUNTERPARTY
SECTOR_EXPOSURE
INFERRED_EXPOSURE
UNRESOLVED
```

تحفظ الصلة الدليل ووقت القطع والثقة والتعارض. الحدث `SUPERSEDED` لا يستطيع إنشاء Exposure صالح للعوامل، بينما يظل الحدث التصحيحي `CORRECTED` فعالًا بوصفه التصحيح الجاري. ثم يبني Factor Snapshot بإصداره الثابت عوامل السعر والسيولة والتذبذب والإفصاحات والإجراءات والحالة ونظام السوق/القطاع والتعرض للأحداث والمزاج المحدود. حالة العامل واحدة من:

```text
OBSERVED
MISSING
NOT_APPLICABLE
REJECTED
```

لا تُستبدل المعلومة المفقودة بصفر. يفرض Registry لكل عامل `window_days` أو`window_hours` مقابل `available_at` و`decision_at`؛ حالة التداول الحالية لا يزيد عمرها على 24 ساعة. وتربط `factor_snapshot_sha256` كامل المحتوى القانوني للصفوف والعوامل والأدلة والتصرفات والدرجات، ويُشتق `snapshot_id` من البصمة نفسها، لذلك يكشف المدقق العبث بأي قيمة أوEvidence أوDisposition أوScore. ويصدر صف مقام لكل عضو متوقع وحالة نهائية `SELECTED` أو`REJECTED` أو`ABSTAINED` أو`UNRESOLVED` مع أول مرحلة فاشلة وسببها. بذلك لا تختفي الأسهم التي تعذر تحليلها من مقام القياس.

## عقد الإعادة التاريخية

لتقييم أحدث 40 قرارًا يلزم 41 جلسة رسمية متتالية: جلسة قرار لكل صف، ثم الجلسة التالية لقياس النتيجة. قبل فتح Outcomes يجب تجميد السياسة والكود والكون وFeature Snapshot لكل Cutoff. كما يلزم:

- عضوية سوق Point-in-Time كاملة ومتصالحة؛
- تقويم رسمي وحالة تداول لكل ورقة؛
- أسعار تنفيذ/إغلاق مقبولة ومعدلة بالإجراءات؛
- Corporate Actions وSuspension/Resumption تاريخية؛
- Benchmark سوق وقطاع Point-in-Time؛
- 40 صف قرار مختومًا ومقامًا كاملًا؛
- Outcome packets منفصلة وحقوق استخدام قابلة للتدقيق؛
- Final Authority Receipt مستقل.

المنتج `execution_grade_required=true`. يعيد المدقق اشتقاق Rank من Score تنازليًا ثم Security Code تصاعديًا عند التعادل، ويشترط أن Selected rows تساوي Top-K. كل Selected row يحتاج تنفيذًا `FILLED` مع Evidence وتوقيت/سعر دخول وخروج عند إغلاق الجلسة؛ Non-fill يحجب الإعادة.

الهدف الأساسي `GROSS_ADJUSTED_RETURN_GT_0` هو العائد الإجمالي المعدل من إغلاق القرار إلى إغلاق النتيجة **قبل** رسوم التنفيذ وSpread وSlippage. تُستخدم تكاليف التنفيذ في `actionable_net_up` وفي Market/Sector net-excess metrics الثانوية. لذلك لا يجوز وصف Primary agreement بأنه «بعد التكاليف».

كل سهم في الكون يظل في المقام حتى إذا كانت نتيجة جلسته `SUSPENDED` أو`HALTED` أو`NO_TRADE` أو`TRADED_THEN_SUSPENDED`. لكن `KU-BO-008-D01` ما زال مفتوحًا، ولذلك تؤدي أي حالة كهذه إلى `STOP_BACKTEST` بدل حذف الصف أوتقديم Close اصطناعي أواختيار سياسة تمديد ضمنية.

الحالات المسموحة:

```text
PASS_BACKTEST     # كل البوابات نجحت ويمكن حساب المقاييس المعلنة مسبقًا
STOP_BACKTEST     # خلل بنيوي أوأدلة/مقام/سلامة مفقودة؛ metrics=null
```

حتى `PASS_BACKTEST` على 40 جلسة يبقى Pilot وصفيًا، وليس Prospective Validation أوProbability أومنظومة توصية.
في التنفيذ الحالي يظل غياب Final Authority verifier خللًا بنيويًا سابقًا لأي
فحص قوة، ولذلك يعيد المسار الحقيقي `STOP_BACKTEST`. أزيلت حالة
`STOP_INFERENCE` من هذا العقد لأنها لم تكن قابلة للوصول من Evaluator.

## النتيجة الحالية لاختبار الأربعين الأخيرة

```text
status: STOP_BACKTEST
expected_decision_sessions: 40
required_official_sessions: 41
process_valid_scoreable_sessions: 0
metrics: null
agreement_rate: null
agreement_rate_status: NOT_APPLICABLE
authority_receipt_sha256: null
authority_verified: false
accuracy_claim_allowed: false
```

السبب: المستودع لا يحتوي Real Point-in-Time packet للكون الكامل أوEOD وBenchmark والإجراءات والحالة وFeature snapshots وOutcomes اللازمة، ولا Final Authority verifier مستقلًا. لذلك لا يوجد مقام صالح؛ `agreement_rate=null/NOT_APPLICABLE` تُعرض بشريًا `N/A`، وكتابة `0%` ستكون معلومة خاطئة لأن الصفر هنا عدد الجلسات المؤهلة للقياس لا نسبة فشل التوقعات. كما لا يُعلن نطاق تقويمي على أنه «مختبَر» قبل مصالحة الجلسات الرسمية الفعلية داخل Packet.

## حالة الاختبارات عند نقطة الاستقرار

```text
workflow/source/ingestion/context/integration/replay/CLI/schema targeted: 183/183 PASS
final full suite on current tree:                        2067/2067 PASS (164.347s)
compileall / JSON / diff / smoke / secret:               PASS
corpus generation and audit:                             1280/1280 PASS
Codex control:                                           PASS (15/10; 0 errors/0 warnings)
final wheel:                                             PASS (444351 bytes)
isolated install/imports/CLI/workflow validation:        PASS
installed_data_foundation_check:                         PASS (8 admissions; 8 lineages)
KU-BO-012 implementation-head GitHub Actions:            PASS (Run 31733924569; Python 3.11-3.14)
```

بصمة Wheel النهائية SHA-256 هي `ee089ec3a7e100e81e1ef4a0378824c2b3e817db7d4c23d2d197b728b400c3a3`. أضيفت مرحلة KU-BO-012 المركزة إلى CI، وأضيفت Installed-Wheel checks لأوامر Workflow/Search/Integration/Replay، ومنها ظهور `build-kuwait-research-bundle`. نُشر التنفيذ في Draft PR #14 عند `58a78042d5d509e599d2e273d793856b1dee14dd`، ونجح Run `31733924569`. لم يحدث Merge، وتحديث سجل التحكم هذا يحتاج Exact-head CI جديدًا قبل حد الدمج.

## حالة الفروع والدمج

- PR #1 وPRs #4–#13 أسلاف لـ`main@92b2bdd`، ولذلك لا تحتاج دمجًا جديدًا.
- PR #2 وPR #3 قديمان، غير قابلين للدمج مباشرة، ومتجاوزان بالعقود الحالية؛ يُمنع دمجهما أوCherry-pick شامل منهما.
- KU-BO-012 ما زالت `IN_PROGRESS` في Draft PR #14. `MERGE_ALLOWED` يبقى `NO` حتى نجاح Exact-head CI لرأس سجل التحكم اللاحق وإعادة فحص قرار الدمج الشرطي `KU-BO-MERGE-004`.
- قرار سياسة Outcome عبر التعليق/التوقف `KU-BO-008-D01` ما زال `OPEN`.

## حدود الادعاء

المسموح حاليًا هو القول إن عقود البحث والسجل والأحداث والتعرض والعوامل والمقام والإعادة Fail-closed موجودة وقابلة للاختبار على مدخلات تعاقدية. غير المسموح هو ادعاء أن 50 موقعًا تعمل حيًا، أوأن السوق كله مغطى فعليًا، أوأن هناك نسبة توافق، أوأن الدرجة احتمال، أوأن السهم موصى بشرائه.
