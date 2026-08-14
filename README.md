# KU-BO Research Engine 0.1.0 — أساس قابل للتدقيق للبحث متعدد المصادر في بورصة الكويت

`KU-BO` أساس برمجي `Auditable Research Foundation` لأعمال `Research Decision-Support`. يجمع Evidence Pack من مصادر متعددة، ويتحقق من التوقيت والهوية واستقلال الناشرين، ثم ينتج ترتيبًا بحثيًا أو `WATCH` أو `ABSTAIN` حسب الأدلة المتاحة. تعطل موقع منفرد لا يوقف البحث تلقائيًا، لكنه قد يحجبه إذا أزال دليل الهوية الرسمي الإلزامي ولم يبق بديل رسمي حديث.

هذه النسخة ليست منصة مكتملة للإنتاج، ولا خدمة جمع حية شاملة، ولا نظام توصيات أوتنفيذ تداول. نجاح العقود والاختبارات الاصطناعية يثبت سلوك الأساس البرمجي فقط، ولا يثبت توافر المصادر الخارجية أوالدقة التنبئية أوالجاهزية التشغيلية المستمرة.

النتيجة الافتراضية الآن هي **Research Rank موثّق للمجموعة التي جرى تغطيتها**. ليست احتمالًا، وليست توصية شراء، ولا تدّعي دقة تاريخية لم تُقَس. يظل المسار القديم الأكثر صرامة موجودًا بصورة منفصلة عندما تكون الحاجة إلى Forecast احتمالي أو Backtest موثوق.

## المبادئ غير القابلة للتجاوز

- الوضع الافتراضي أصبح `research_network`.
- لا يحتاج البحث الأولي إلى Historical Pack كامل أو Model Card.
- يحتاج كل تشغيل إلى حزمة أدلة حديثة من عدة مصادر مستقلة، لا إلى نجاح موقع واحد.
- تعطل بورصة الكويت لا يوقف البحث كله إذا اكتمل النصاب **وبقي إيصال هوية رسمي بديل وحديث**؛ وإلا يكون فشل الهوية Structural. كما يمنع التعطل اعتبار المحفز «مؤكدًا رسميًا» ويخفض السهم المتأثر إلى `WATCH`.
- المنتديات وتليغرام وTradingView Ideas تساهم في المزاج والمخاطر فقط، بحد أقصى 10% للأفق القصير، ولا تستطيع إنشاء حقيقة رسمية أو محفز.
- إعادة نشر الخبر عشر مرات تُحسب أصلًا واحدًا.
- صفحات السوق والتعليقات داخل المنصة نفسها تُحسب ناشرًا واحدًا؛ Investing لا يصبح مصدرين، وكذلك TradingView.
- تضارب إشارتين مستقلتين وقويتين يفرض `WATCH`.
- التأكيد الرسمي يجب أن يطابق `event_key` واتجاه المحفز نفسه؛ إفصاح رسمي مختلف لا يؤكد خبرًا آخر لمجرد تعلقهما بالسهم ذاته.
- لا يُستخدم وصف «الأفضل في السوق» إلا بعد مطابقة 100% من عضوية السوق وتغطيته لحظيًا.
- الافتتاح وIntraday والتنفيذ يظلون `EXECUTION_BLOCKED` من دون Feed مرخّص ومؤقت.

## شبكة المصادر

يسجل الكتالوج شبكة قابلة للتوسع من المصادر وعائلات الناشرين، موزعة على أدوار لا على قائمة ثقة عمياء:

الحالة الحالية على فرع `KU-BO-012` هي **68 تعريف مصدر** تُحتسب ضمن **62 مجموعة استقلال**؛ عدد الروابط أوالأسطح لا يساوي عدد الناشرين المستقلين. بعد استبعاد أسطح البحث والتخزين يوجد **59 نطاقًا مرشحًا**، منها **53 نطاقًا مصرحًا في الكتالوج كعام ومفعّل افتراضيًا**، وتتحول Start URLs المنفذة إلى **52 نطاقًا مميزًا** قبل الحجز العادل. الخطة الافتراضية تختار 50 نطاقًا بالضبط، بمساهمات جديدة حسب الموجات `17/0/29/4`، وتحجز الأربعة الأخيرة للأرشيف/المجتمع بما يضمن محاولة `t.me` و`indexsignal.com`. البقية تحتاج تفعيلًا أوحق استخدام؛ ولا يمثل أي رقم تأكيدات مستقلة.

حالة القدرة منفصلة عن التسجيل: **66** تعريفًا `DEFINED_ONLY`، و**2** فقط `END_TO_END_TESTED` على Fixtures مولدة، و**0** `LIVE_OPERATIONAL`. لا يُرقّى مصدر لأن اسمه موجود أولأن صفحته قابلة للفتح يدويًا.

- رسمي/جهة إصدار: بورصة الكويت، تقاريرها وإفصاحاتها، هيئة أسواق المال/iFSAH، ومواقع علاقات المستثمرين الموثقة.
- سوق وتاريخ سعري: Investing.com، TradingView، Argaam، MarketScreener، Mubasher، Yahoo Finance، وTradingEconomics.
- أخبار وأرشيف صحفي: KUNA، Reuters، Zawya، Asharq Business، الراي، الأنباء، الجريدة، والقبس.
- مجتمع ومنتديات: IndexSignal، قنوات تليغرام العامة، وTradingView Ideas.
- أرشيف ويب وتوجيه: Wayback Machine، Common Crawl، والبحث على الويب.
- بيانات مرخّصة: ICE أو Broker/Market Feed مصرح به عند وجود Entitlement حقيقي.

كل مصدر يملك عقدًا يحدد أدواره، نطاقاته، مجموعة استقلاله، أقصى درجة لتوقيت الدليل، وما إذا كان يستطيع إنشاء Finding أم لا.

## مسار سياق الكويت وتقييم الجلسة التالية

يضيف `KU-BO-012` المنتج `KUWAIT_120D_NEXT_SESSION_RESEARCH` كمسار بحثي محافظ على مستوى الكون المؤهل كاملًا. يحتفظ بأربع نوافذ مستقلة:

```text
سياق الكويت:             120 يومًا تقويميًا
الأحداث النشطة:           30 يومًا تقويميًا
مزاج المجتمع:              7 أيام تقويمية
المحفزات الأحدث:           72 ساعة
أفق النتيجة:               الجلسة الرسمية المكتملة التالية
```

التجميع تراكمي وله Watermark؛ التشغيل العادي لا يعيد تنزيل أربعة أشهر كاملة في كل سؤال. تسير المحاولات في موجات: رسمي/رقابي، ثم جهات الإصدار والحكومة، ثم البيانات المنظمة والأخبار، ثم المجتمع والأرشيف. `web_search_router` مسجل للتوجيه فقط ولا ينفذه المشغل الحالي. يحاول المشغل 50 نطاقًا بحثيًا مميزًا ضمن ميزانية ثابتة، ويعيد الخطأ العابر بحد أقصى ثلاث محاولات لكل استراتيجية. أما الرد الصحيح الفارغ فيسمح بأربع استراتيجيات استعلام مختلفة جوهريًا، لا أربع إعادات للرابط نفسه. المنع الصريح وLogin وCAPTCHA وPaywall وRobots لا يُتجاوز أي منها؛ تُحفظ المحاولة وسببها.

إعادة المحاولة Fail-stop: المنع الصريح لا يعاد، وHTTP 429 يبقى في الاستراتيجية نفسها ثم يوقف المصدر بعد المحاولة الثالثة بدل الدوران على استعلام آخر. يحترم `Retry-After` ما دام داخل ميزانية الوقت المتبقية؛ وإذا تجاوزها أوفشل Sleeper يتوقف المسار. يسجل Attempt Ledger كل قرار مع `retry_after_seconds` وDisposition والقيود، ويصرح بأن Hash chain ليست External Seal، وأن Capture time ليست Publication time، وأن Low-level HTTP غير محسوبة كلٌ على حدة، وأن Parser يجب أن يفرض Point-in-Time cutoff، وأن Zero Result يحتاج Material query-route proofs فريدة.

يمكن إعادة فتح تشغيل Source Search المحفوظ والتحقق منه قبل الدمج؛ يعيد المدقق حساب بصمة التقرير وسجل المحاولات والبايتات الخام المشار إليها. ثم يقبل `build-kuwait-research-bundle` ملفًا صارمًا من Parsed Inputs، ويرفض أي Evidence hash لا يحل إلى تلك البايتات، ويصدر Context/Exposure/Factor artifacts وحزمة تكامل Atomically. هذا جسر تكامل قابل للتدقيق، وليس Parser عامًا: لا يستنتج من البايتات أحداثًا أوتعرضات أوعوامل أوDispositions أوScores من تلقاء نفسه.

تُطبّع الأحداث إلى `KUWAIT_MACRO` أو`SECTOR` أو`SECURITY`، ثم ترتبط بالأسهم بأدلة Exposure صريحة. ينتج Factor Snapshot لكل عضو متوقع وصف مقام كامل يوضح `SELECTED` أو`REJECTED` أو`ABSTAINED` أو`UNRESOLVED`. تربط `factor_snapshot_sha256` المحتوى القانوني الكامل للصفوف والعوامل والأدلة والتصرفات والدرجات، ويُشتق منها `snapshot_id`. كما تُفرض Freshness كل عامل من سجل النوافذ؛ حالة التداول الحالية نافذتها 24 ساعة، والحدث `SUPERSEDED` لا يصبح Factor-eligible. القيمة المفقودة تظل `MISSING` أو`NOT_APPLICABLE` ولا تتحول إلى صفر محايد. Telegram وIndexSignal للمزاج أوتوجيه البحث فقط، ولا يثبتان حقيقة رسمية أوالسعر أوالإجراء أوالمحفز منفردين.

عقد الإعادة التاريخية الصارم يحتاج **41 جلسة رسمية متتالية** لتقييم **40 قرارًا**، مع Universe وFeatures وOutcomes وCorporate Actions وحالة تداول وبصمات Point-in-Time لكل قرار. المنتج Execution-grade: الترتيب يُعاد اشتقاقه من Score تنازليًا مع Security Code كفاصل حتمي، والاختيار يساوي Top-K، وكل صف مختار يحتاج `FILLED` موثقًا. يبقى العضو غير المتداول في المقام، لكنه يوقف الإعادة ما دام قرار `KU-BO-008-D01` مفتوحًا؛ لا يُحذف ولا يُمنح Close اصطناعيًا.

الـPrimary label هو `GROSS_ADJUSTED_RETURN_GT_0`: عائد الجلسة التالية الإجمالي المعدل قبل تكاليف التنفيذ. الرسوم وSpread وSlippage تدخل في Actionable net ومقاييس Market/Sector net-excess الثانوية، لا في الـPrimary gross label. لا يحتوي المستودع حاليًا على Packet سوقي حقيقي يحقق العقد؛ لذلك نتيجة CLI لاختبار الأربعين الأخيرة هي `STOP_BACKTEST` مع **0 من 40 جلسة قابلة للقياس** و`metrics=null`. ويصدر العقد `agreement_rate=null` مع `agreement_rate_status=NOT_APPLICABLE`، و`authority_verified=false`، و`accuracy_claim_allowed=false`؛ أي إن نسبة التوافق المعروضة بشريًا **`N/A` وليست `0%`**. لا يعرض Runtime حالة `STOP_INFERENCE` لأنها غير قابلة للوصول في هذا العقد الصارم. التفاصيل في `docs/KUWAIT_120D_NEXT_SESSION_AR.md`.

## نصاب المصادر حسب الأفق

للأفق من جلسة إلى خمس جلسات، يلزم على الأقل مصدران مستقلان لاكتشاف السوق، ومصدر تاريخ سعري، ومصدران إخباريان، وأربع مجموعات مستقلة إجمالًا.

للأفق من 10 إلى 63 جلسة، يلزم مصدران لاكتشاف السوق، ومصدران تاريخيان، ومصدران إخباريان، ومصدر أساسيات، وخمس مجموعات مستقلة.

للأفق 126 أو 252 جلسة، يلزم مصدران تاريخيان، ومصدران إخباريان، ومصدران للأساسيات، وخمس مجموعات مستقلة. مساهمة المجتمع في هذا الأفق تساوي صفرًا.

للافتتاح أو Intraday، يلزم `EXECUTION_TAPE` مرخّص. المواقع العامة لا تعوضه.

## حزمة كل تشغيل

```text
research_run/
  research_run.json
  universe.json              # required effective-dated identity in every scope
  manifest.json
  source_observations.json
  findings.jsonl
  raw/
    ... exact captured bytes ...
```

`research_run.json` يثبت المنتج، `decision_at`، النطاق، تغطية الكون، والميزانية. `universe.json` إلزامي لكل نطاق، ويربط كل `security_code` وTicker بفعالية زمنية ومصدر هوية Official/Licensed وأثر خام. يفسر `membership_as_of` بتوقيت `Asia/Kuwait`، ويجب أن يقع في تاريخ القرار المحلي نفسه وألا يتجاوزه؛ الأعداد وحدها لا تكفي، ووصف السوق كاملًا يتطلب كذلك تغطية 100% وFinding جوهريًا لكل عضو متوقع. يربط `manifest.json` كل أثر خام بعنوانه وتوقيته وحجمه وSHA-256. يسجل `source_observations.json` نجاح أو فشل كل مصدر وسبب قبوله أو رفضه. ويحتوي `findings.jsonl` فقط على الاستنتاجات المرتبطة بأثر خام من المصدر نفسه، مع `evidence_roles` و`fact_type` صالحين؛ ويجب أن يطابق `source_url` عنوان الـArtifact المشار إليه حرفيًا. كما يرتبط التقرير والسجل بـ`evidence_packet_hash` واحد يغطي الملفات القانونية والأدلة المشار إليها في Manifest.

## حالات التشغيل

- `SOURCE_NETWORK_REQUIRED`: لم تُقدم حزمة تشغيل حديثة.
- `SOURCE_NETWORK_BLOCKED`: عقد أو توقيت أو Hash أو هوية غير صالح.
- `RESEARCH_PARTIAL`: الحزمة سليمة لكن نصاب الأدوار غير مكتمل.
- `RESEARCH_READY`: نصاب الشبكة مكتمل ويمكن إخراج Research Rank.
- `EXECUTION_BLOCKED`: المنتج يحتاج Feed تنفيذ مرخّصًا غير موجود.

أما `validated_forecast` فيحتفظ ببوابات Historical Pack وModel Card والتحقق المستقبلي. وجوده لا يجعل الوضع البحثي Probability بصورة غير مباشرة.

## البدء

يتطلب Python 3.11 أو أحدث. تعتمد النواة على حزمة `tzdata` المثبتة تلقائيًا مع المشروع لضمان توفر قاعدة مناطق IANA و`Asia/Kuwait` حتى على Windows أوContainer مصغرة بلا System tzdb.

```bash
python3 -m pip install -e .
kubo validate-source-network
kubo validate-live-probe --probe /absolute/path/to/fresh_access_probe.json
```

واجهة `kubo` تعتمد على ملفات العقود داخل Checkout المشروع. عند تثبيت Wheel وتشغيل الأمر من خارجه، مرر جذر المستودع قبل اسم الأمر:

```bash
kubo --project-root /absolute/path/to/ku-bo validate-source-network
```

إذا لم يكن الجذر صالحًا، يفشل الأمر برسالة واضحة بدل Traceback أو افتراض وجود إعدادات داخل الـWheel.

يمكن أيضًا التشغيل من دون تثبيت:

```bash
PYTHONPATH=src python -m kubo validate-source-network
```

## طبقة المعرفة التاريخية الكويتية

يضيف `KU-BO-013` عقد تخطيط مستقلًا يغطي ست طبقات سنوية: تاريخ الكويت من 1500،
الأزمات التجارية من 1927، دورة حياة الشركات من 1970، الأرشيف الإعلامي للشركات
من 1980، القضايا خلال آخر عشرين سنة تقويمية، والأحداث الاقتصادية خلال آخر خمس
سنوات تقويمية. سجل المصادر يحتوي 28 تعريفًا مصنفًا حسب السلطة والدور ووسيلة
الوصول والحقوق، وجميعها `DEFINED_ONLY` إلى أن يثبت جمع فعلي قابل لإعادة التحقق.

```bash
kubo --project-root . validate-historical-knowledge
kubo --project-root . plan-historical-research \
  --as-of 2026-08-14 \
  --output /absolute/path/to/historical-plan.json
```

الخطة لا تجمع المحتوى ولا تدّعي اكتمال سنة أو شركة. كل صف يبدأ
`NOT_COLLECTED`، والشركات تحتاج أولًا تعدادًا رسميًا من السجل التجاري. الصحافة
للتعضيد، والسوشيال والمنتديات وWikipedia للتوجيه أو المزاج فقط. الإحالة أو
الاتهام لا يعني الإدانة، لذلك يفرض العقد حالة إجرائية صريحة. هذه المعرفة
`CONTEXT_ONLY` ولا تولّد شراءً أو Forecast أو Score مباشرة. التفاصيل في
`docs/KUWAIT_HISTORICAL_KNOWLEDGE_AR.md`.

## أرشيف بدء التشغيل المعزول

يبني `KU-BO-014` فوق الخطة التاريخية ولا يستبدلها. الهدف هو إنشاء
`Bootstrap Archive Scaffold` ذري وغير قابل للاستبدال يحتوي على الخطة نفسها،
بصمات مدخلات الإعداد، أوصاف المراحل، وManifest للتحكم فقط. يبدأ الأرشيف بصفر
Evidence وصفر أحداث وصفر شركات؛ نجاح تهيئته لا يعني أن الجمع بدأ أوأن التاريخ
اكتمل.

ترتيب التطوير المحجوز هو: الأرشيف التاريخي، ثم `Company Intelligence`، ثم
موجات المصادر، ثم المصالحة الرسمية النهائية مع بورصة الكويت. وتظل المرحلة
الثانية محجوبة حتى يصل تعداد رسمي Effective-dated للشركات المدرجة. تُستخدم
بورصة الكويت مبكرًا كمرساة هوية محدودة لهذا التعداد، ثم تعود في المرحلة
الأخيرة للمصالحة الشاملة؛ فلا تُبنى ملفات الشركات من قائمة غير رسمية.

يربط Crosswalk معلن مصادر KU-BO-013 بمعرّفات Source Network عندما توجد علاقة
دلالية، لكنه لا يحول التعريف إلى Connector أوParser أوحق جمع. جميع الروابط
تبدأ `collection_allowed=false`، وتبقى المصادر الاجتماعية للتوجيه أوالمزاج
فقط. التفاصيل وحدود مساحة العمل في `docs/BOOTSTRAP_ARCHIVE_AR.md`.

تهيئة الـScaffold والتحقق منه لا يجريان أي اتصال شبكي. يمكن وضعه داخل Checkout
تحت `runtime/` غير المتتبع في Git، أومسار Runtime خارجي؛ ويجب أن يكون الهدف
جديدًا وأبوه موجودًا:

```bash
mkdir -p runtime
kubo --project-root . validate-bootstrap-archive-config
kubo --project-root . prepare-bootstrap-archive \
  --as-of 2026-08-14 \
  --output-root runtime/bootstrap-2026-08-14
kubo validate-bootstrap-archive \
  --archive-root runtime/bootstrap-2026-08-14
```

جسر Source Search إلى Context/Exposure/Factor يعمل على تشغيل محفوظ ومدخلات Parsed صريحة:

```bash
kubo --project-root /absolute/path/to/ku-bo build-kuwait-research-bundle \
  --source-search-root /absolute/path/to/source-search-run \
  --parsed-inputs /absolute/path/to/parsed-research-inputs.json \
  --output-root /absolute/path/to/integrated-research-bundle
```

يعيد الأمر التحقق من التقرير والسجل والبايتات، ولا يحول Raw capture إلى Finding تلقائيًا.

إنشاء خطة بحث من حزمة تشغيل:

```bash
kubo plan \
  --mode research_network \
  --product next_session_rank \
  --network-run /absolute/path/to/research_run
```

إنشاء تقرير مرن من عقد طلب:

```bash
kubo run-request \
  --request examples/analysis_request.json \
  --network-run examples/synthetic_source_network_run \
  --output runtime/report.md
```

`examples/analysis_request.json` اصطناعي. يمكن اختيار `json` أو`markdown` وتحديد Scope والأسهم وعمق التقرير، لكن الوضع `research_network` يرفض صراحة طلب Probability أوBuy Recommendation أوEntry/Exit Price.

## Data Foundation Pilot

توفّر واجهة `kubo-data-foundation` مسارات منفصلة للهوية والتقويم والحالة والإجراءات، و`Benchmark History`، و`Official Complete Daily EOD`، ثم مصالحة نهائية من اثنتي عشرة بوابة. يمكن التحقق من سجل المؤشرات المثبت في المشروع عبر:

```bash
kubo-data-foundation --project-root . validate-benchmark-registry
```

قوالب الجمع والـfixtures تثبت العقود فقط. لا يحتوي المستودع على بيانات Benchmark أوEOD حقيقية، ولا يثبت Runtime Trust Registry بايتات الالتقاط وحده؛ يلزم إيصال خارجي مصادق عليه يربط الـartifact نفسه بالمصدر. كما تبقى READY النهائية ممنوعة حتى يوجد إيصال نهائي مستقل يربط التقرير والحزمة والمكونات والسياسة وفحص المستودع. ولا يُسمح بحالة `DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST` إلا عند نجاح كل البوابات على Evidence حقيقية وحقوق متوافقة وسياسة outcome product-specific بقرار مصادق عليه؛ عقد v1 الحالي لا يسمح بـ`FROZEN`. دليل التشغيل والعقود موجود في `docs/BENCHMARK_OFFICIAL_EOD_V0_2_AR.md`، والحالة الحالية في `docs/CURRENT_DATA_FOUNDATION_STATUS_AR.md`.

## الجمع والموصلات

طبقة الجمع تحفظ البايتات الخام أولًا، ثم Manifest يحتوي URL ووقت الالتقاط والحجم وSHA-256 وحالة المصدر. يوجد Connector للملفات والـFixtures للاختبارات، وPublic HTTP Connector محدود بالـAllowlist والحجم والوقت. الموصل لا يتجاوز Login أوCAPTCHA أوPaywall أوRate Limit أوRobots controls.

خطة الجمع محدودة بثوابت Fail-closed: **32 مهمة كحد أقصى، و128 MiB لمجموع `max_bytes`، و300 ثانية لمجموع `timeout_seconds`**. تُرفض الخطة المتجاوزة قبل إنشاء أي Connector أوبدء الالتقاط أوكتابة مجلد الناتج.

تشغيل Capture Plan اصطناعي:

```bash
kubo capture \
  --plan examples/capture_plan.json \
  --fixture-root examples/synthetic_source_network_run \
  --output-root runtime/capture
```

النتيجة Raw capture فقط، وتبقى `RAW_CAPTURE_PENDING_PARSER_VALIDATION`. لا تدخل في Rank قبل Parsing وIdentity وTiming وEvidence validation.

تتضمن النسخة `0.1.0` محللين محدودين ومحددين بالمصدر: `boursa_identity_html_v1` لهوية الورقة الرسمية، و`investing_history_html_v1` لجدول السعر التاريخي المنسوب إلى المزود. يفرض `materialize-parser-run` مصالحة Security Code/Ticker/ISIN، وربط كل مهمة ببايتات Manifest، ثم يعيد تشغيل مدقق الشبكة. اختبارات النهاية إلى النهاية تستخدم Fixtures مولدة لا تحتوي بيانات سوق حقيقية؛ لذلك تسجل `config/source_capabilities.json` المحللين كـ`END_TO_END_TESTED` فقط و`live_operational = false`.

```bash
kubo materialize-parser-run \
  --capture-root /absolute/path/to/capture \
  --parser-plan /absolute/path/to/parser-plan.json
```

لا يغطي هذا المسار الأخبار أوالإفصاحات أوالمحفزات، ولا يجعل Investing مصدر تنفيذ أوFeed حيًا. أي تغيير في رؤوس الجدول أوالهوية أوOHLC أوتسلسل التاريخ أوتطابق نسبة التغير يفشل مغلقًا. بقية المصادر المسجلة بلا Parsers عاملة حتى يثبت العكس في مصفوفة القدرات.

الموصلات التي تحتاج حسابًا، مثل Investing.com أوTelegram أوFacebook أوInstagram أوTikTok أوX، لا تصبح متاحة بمجرد تسجيل الدخول إلى Codex أوGitHub. كل Connector يحتاج تفويضه المستقل، والحسابات الاجتماعية غير الموثقة لا تُثبت حقائق شركة.

### حد الثقة للمصادر المحمية

يفشل `0.1.0` مغلقًا عند مساهمة مصدر معطل افتراضيًا أو ديناميكي النطاق أو مرخّص ما لم يُقدَّم سجل ثقة خارجي منفصل عن Packet، صالح وقت القرار، ومصادق عليه بـ`HMAC-SHA256` ومفتاح و`key_id` من بيئة التشغيل. يربط السجل `source_id` بالحساب/Subject والنطاق و`security_code` وActivation/Entitlement وفترة الصلاحية، ويجب أن يحل كل استخدام إلى قيد واحد مطابق. تبقى حقول `runtime_authority` وActivation وEntitlement داخل Packet مطلوبة لاتساق الأدلة، لكنها **ليست Root of Trust** ولا تكفي وحدها للتفويض. ويعرض ناتج التحقق وجوب السجل وقائمة المصادر الحساسة ومعرّف السجل وبصمة محتواه ومعرّف المفتاح المستخدم، من دون كشف المفتاح.

تمرر الأوامر `validate-network-run` و`plan` و`run-request` السجل بالخيار `--runtime-trust-registry`، ويجب أن يبقى مساره خارج مجلد حزمة الأدلة. يقرأ CLI المفتاح فقط من `KUBO_RUNTIME_TRUST_HMAC_KEY` بصيغة `hex:` أو`base64:`، ومعرّفه من `KUBO_RUNTIME_TRUST_HMAC_KEY_ID`؛ ولا يقبل مفتاحًا أقصر من 32 بايت.

## منهج التحليل

- `source_network` يفرض Point-in-Time cutoff ويربط كل Finding بأثر خام من المصدر نفسه.
- `research_rank` يزيل إعادة النشر على مستوى Origin/Publisher Family ويكشف التعارضات.
- `liquidity` يفصل جودة الإشارة عن قابلية التنفيذ، ويمثل `NO_FILL` و`PARTIAL_FILL` والحدود السعرية والتعليق.
- `methodology_registry.json` يربط كل منهج بمرجعه العلمي وحالته واختباراته المطلوبة.
- أي Model أوProbability يبقى محجوبًا حتى Prospective Validation وTemporal Calibration وModel Card مختوم.

## Degraded Mode

- فشل بورصة الكويت: يستمر البحث فقط إذا بقي إيصال هوية Official/Licensed بديل وحديث؛ وتُخفض Official Confirmation للأسهم المتأثرة.
- فشل Social Media: يستمر التحليل من دون طبقة Sentiment.
- فشل مصدر سعري أوخبري: يستمر ما دام Quorum المستقل مكتملًا.
- نقص أدلة سهم واحد: يتحول السهم إلى `WATCH` أو`ABSTAIN`، ولا يتوقف السوق كله.
- `SOURCE_NETWORK_BLOCKED` ينتج من تلف العقود أوالهوية أوالأدلة. حجب موقع منفرد لا يكفي وحده، لكن غياب بديل يفي بعقد الهوية الإلزامي يكفي للحجب.

## Research Ledger

يمكن تجميد التقرير الصادر في Decision stream مستقل عن Outcome stream:

```bash
kubo run-request \
  --request examples/analysis_request.json \
  --network-run examples/synthetic_source_network_run \
  --research-ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1

kubo verify-research-ledger \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1
```

السجل Append-only مع Hash chain ولا توجد API لتعديل قرار قديم. يربط كل قرار بصمة حزمة الأدلة، وبصمة سياسات المشروع، وبصمة حزمة `kubo` المستوردة والمنفذة فعليًا؛ لذلك لا يستطيع `--project-root` مغاير انتحال بصمة كود Wheel مثبت.

تُضاف النتيجة لاحقًا من Payload قياس صارم وحزمة Evidence حقيقية داخل مجلد السجل، لا من Hash يرسله المتصل:

```text
runtime/ledger/outcome_evidence/outcome-101-next/
├── manifest.json
└── raw/
    └── official-close.json
```

```bash
kubo append-research-outcome \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1 \
  --outcome-id outcome-101-next \
  --decision-id synthetic-demo-request \
  --observed-at 2026-08-08T14:00:00+03:00 \
  --payload runtime/outcome-101-next.json \
  --evidence-pack outcome_evidence/outcome-101-next
```

يُحل المسار النسبي لـ`--evidence-pack` من داخل `--ledger-dir`. يتحقق الأمر من تطابق القرار والسهم والتوقيت، ومن قائمة `raw/` وحجم كل ملف وSHA-256 الفعلي، ثم يعيد `verify` و`seal` الفحص من البايتات نفسها. Payload القياس يحدد `metric_id` وقيمة رقمية منتهية و`unit` وفترة القياس و`method_id`؛ وجود البايتات لا يثبت صحة المنهج أوParser من دون مراجعة مستقلة.

يمكن إنشاء HMAC Seal باستخدام `KUBO_LEDGER_HMAC_KEY` وقت التشغيل فقط بصيغة `hex:` أو`base64:` ومع `--key-id`. يتطلب التحقق بالمفتاح `--expected-key-id` ويرفض خفض الخوارزمية إلى Seal غير موقّع:

```bash
kubo seal-research-ledger \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1 \
  --seal runtime/ledger/research-ledger.seal.json \
  --key-id operations-2026

kubo verify-research-ledger \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1 \
  --seal runtime/ledger/research-ledger.seal.json \
  --expected-key-id operations-2026
```

لا تحفظ قيمة المفتاح في `.env.example` أوGitHub، ولا تمررها كـCLI argument.

تشغيل المثال الاصطناعي للتحقق من العقود فقط:

```bash
PYTHONPATH=src python3 scripts/smoke_check.py
```

المثال الاصطناعي ليس بيانات بورصة ولا توقعًا. وفي مسار
`validated_forecast` قد ينجح في فحص العقد، لكنه يبقى
`SYNTHETIC_CONTRACT_ONLY` ولا يتحول إلى `DATA_READY_MODEL_UNBOUND` أوأي
حالة جاهزية حقيقية. وحتى إن أُعيدت تسمية قيود Packet محليًا، يبقى نجاح العقد
`EVIDENCE_CONTRACT_VALIDATED_MODEL_UNBOUND` إلى أن ينجح تقرير المصالحة النهائي
على Evidence حقيقية؛ فـPack ذاتي الادعاء ليست جذر ثقة. وحتى بطاقة Model
مصنفة `PROSPECTIVE_VALIDATED` لا تتجاوز `EVIDENCE_AND_MODEL_CONTRACT_VALIDATED`
من دون تلك البوابة النهائية.

ولمنتجات `horizon_sessions` لا تكفي مقارنة `outcome_due_at > decision_at`:
السجل الحقيقي يرفض Civil Days أوتواريخ يحددها المستدعي، والتقييم الافتراضي
يعيد `STOP_BACKTEST` بلا Metrics إلى أن توجد Policy product-specific بقرار
موافق عليه (Schema v1 يرفض FROZEN وخيار 1 العالمي)، وجلسات
وحالات رسمية مربوطة بالبايتات، وFinal Data-Foundation Authority Receipt مستقل.
وضع `SYNTHETIC_CONTRACT_ONLY` اختياري وصريح لتمرين العقد فقط؛ يعيد
`metrics=null` ولا يكشف IC أوReturn أوBrier، ولا ينتج PASS أوclaim أداء أو
Ledger Seal صالحًا.

## التحقق

يحتفظ CI بالـGate المركز لـKU-BO-012، ويضيف KU-BO-014 Gate مستقلًا للتاريخ
والـCrosswalk والـScaffold والـSchemas والـCLI وضبط Codex. كما يختبر الـWheel
المثبتة في `validate-bootstrap-archive-config` ثم ينشئ Archive تحت `runtime/`
ويعيد التحقق منه. PR #15 وPR #16 مدمجان في `main`؛ أما KU-BO-014 فمنشور في
Draft PR #17 بلا سلطة Merge. نجح رأس التنفيذ `c8b41b2` في Exact-head CI Run
`31840391449`، ويظل رأس سجل التحكم اللاحق محتاجًا إلى CI مطابق قبل الإغلاق.

نجحت محليًا اختبارات KU-BO-014 وحدها `34/34`، والاختبارات المستهدفة مع طبقة
التاريخ وضبط Codex `57/57`، ثم نجحت Full Suite النهائية على الشجرة الحالية
`2,120/2,120` في `158.371s`. نجحت كذلك `compileall`، وفحوص JSON، و
`git diff --check`، وSmoke، وSecret Guard، وتوليد وتدقيق Corpus من `1,280`
حالة. ونجح Codex control check على 18 ملف تحكم و10 ملفات مطلوبة مع 0 Errors
و0 Warnings.

نجح بناء Wheel KU-BO-014 والتثبيت المعزول وCLI help والتحقق من الإعداد وإنشاء
الـScaffold وإعادة فتحه من خارج Checkout. نُشر Draft PR #17، ونجح رأس التنفيذ
الدقيق في CI على Python 3.11–3.14. لا يجيز ذلك أي Merge أوجمع حي.

```bash
PYTHONPATH=src python3 -m compileall -q src tests scripts
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 scripts/smoke_check.py
PYTHONPATH=src python3 scripts/secret_guard.py
```

## تأهيل البيانات على دفعات من ثلاثة أسهم

يحتوي الإصدار الحالي على مسار مستقل يجهز الاختبار تدريجيًا بثلاثة أسهم في
كل دفعة، بدءًا بـ`KFH` و`SHIP` و`AZNOULA`. يتحقق المسار من الهوية المرشحة
والترتيب والحجم والفرادة، ثم ينشئ Workspace مقفلة الادعاء بلا جمع بيانات أو
Backtest:

```bash
kubo-data-foundation validate-tri-security-pilot
kubo-data-foundation prepare-tri-security-batch \
  --batch-id tri-001-kfh-ship-aznoula \
  --run-id tri-001-qualification \
  --window-from 2026-01-01 \
  --window-to 2026-08-12 \
  --output-root /safe/runtime/tri-001
```

نجاح الأمرين يعني صحة الإعداد وتجهيز مساحة العمل فقط؛ تظل الهوية
`UNVERIFIED_SEED` وجميع بوابات الأدلة الخارجية معلقة. راجع
`docs/TRI_SECURITY_PILOT_V0_3_AR.md` للتسلسل وحدود الادعاء.

تحتوي Workspace على `scoped_config/` لتمرير مقام الأسهم الثلاثة نفسه إلى
الأوامر القائمة بواسطة `--pilot-config-dir /safe/runtime/tri-001/scoped_config`.
مرر كذلك البصمة الصادرة في `scoped_config_manifest_sha256` باستخدام
`--expected-pilot-config-manifest-sha256` لربط التشغيل بالنسخة المقصودة.

يضيف `KU-BO-010` عقدًا مستقلًا لإصدار Run Receipt خارجي مصادق عليه يربط
خطة الدفعة وScoped Config وWorkspace Report والمقام الثلاثي والنافذة نفسها.
ويربط Stage Binding مستقل المفتاح شجرة مخرجات المرحلة كاملة، بما فيها الملفات
غير المعلنة في Manifest. مفاتيح HMAC ومعرّفاتها Runtime-only، ويُرفض تطابق
مفتاح التشغيل مع مفتاح المرحلة. إعداد Benchmark الخماسي الحالي غير متوافق مع
قطاعي Industrials وUtilities في الدفعة الثلاثية؛ لذلك يظل
`benchmark_qualification_allowed=false` ويفشل أي إخفاء لعدم التوافق مغلقًا.

هذه الطبقة تثبت المصادقة وسلامة الربط فقط. أضاف `KU-BO-011` فرض Semantic
Admission على الحدود الثمانية واختبارات خصومية اصطناعية، لكنه لم يحوّل
العقود إلى Market Evidence أوQualification أوتفويض للدفعة التالية أوBacktest
أوForecast. دليل الإيصالات في `docs/TRI_SECURITY_RUN_RECEIPT_V0_1_AR.md`،
والحالة المتراكمة في `docs/CURRENT_DATA_FOUNDATION_STATUS_AR.md`.

تشغّل GitHub Actions هذه البوابات على Python `3.11` و`3.12` و`3.13` و`3.14`. لا تثبت الوثائق عدد اختبارات ثابتًا؛ نتيجة CI الخاصة بالـCommit هي المرجع.

تغطي الاختبارات حالات غياب بورصة الكويت، فتح قناة رسمية بلا Finding، المجتمع وحده، Finding مستقبلي، Hash تابع لمصدر آخر، Artifact جُمع بعد القرار، Access Receipt أوSearch Snippet كدليل، تضارب مستقل، إعادة النشر، Counts بلا Universe Receipt، Probability غير مدعومة، السيولة الصفرية، التعليق، Limit Queue، وPartial Fill.

## خريطة الملفات

- `config/source_network.json`: سجل المصادر والأدوار والاستقلال وحدود الحقيقة.
- `config/source_capabilities.json`: حالة Capture/Parser/Fixture/Live لكل مصدر من دون استنتاج القدرة من مجرد وجوده في الكتالوج.
- `config/research_policies.json`: نصاب كل أفق وأوزان Research Rank.
- `config/research_workflows.json`: نوافذ وميزانيات وموجات `KUWAIT_120D_NEXT_SESSION_RESEARCH` وعقد الأربعين قرارًا.
- `config/source_query_strategies.json`: استراتيجيات الاستعلام المميزة وسياسة المحاولة المحدودة.
- `config/bootstrap_archive.json`: أقسام أرشيف بدء التشغيل وترتيب المراحل وسياسة التخزين المغلقة.
- `config/historical_source_network_crosswalk.json`: ربط دلالي معلن فقط بين كتالوج التاريخ وشبكة المصادر، بلا تفويض جمع.
- `src/kubo/bootstrap_archive/`: عقد الأرشيف، Crosswalk، التهيئة الذرية، وإعادة التحقق من Scaffold الخالي من الأدلة.
- `src/kubo/source_network.py`: مدقق كتالوج الشبكة وحزمة التشغيل والـLive Probe.
- `src/kubo/source_orchestrator.py`: موجات المحاولة وRetry/empty-result handling وسجل المحاولات المترابط.
- `src/kubo/context_research.py`: Context Events وSecurity Exposure وFactor Snapshot وصفوف المقام.
- `src/kubo/kuwait_research_pipeline.py`: التحقق من Source Search المحفوظ وربطه بمدخلات Parser الصارمة وإخراج حزمة Context/Exposure/Factor ذرية.
- `src/kubo/forty_session_replay.py`: تقييم 40 قرارًا/41 جلسة مع Stop gates قبل المقاييس.
- `src/kubo/research_workflow.py`: تحميل عقد المنتج ودمج تقارير جاهزية طبقات البحث.
- `src/kubo/source_parsers.py`: المحللان المحدودان لبورصة الكويت وInvesting مع فشل Parser Drift مغلقًا.
- `src/kubo/parser_materialization.py`: مصالحة الهوية وتحويل البايتات الملتقطة إلى حزمة قابلة للتحقق.
- `src/kubo/runtime_trust.py`: مصادقة سجل الثقة الخارجي وربط التفويض الحساس Fail-closed.
- `src/kubo/benchmark_*`: سجل ومساحة عمل وعقد واستيراد Benchmark History مع فصل Price/Total Return وBroad/Sector.
- `src/kubo/official_eod_*`: مساحة عمل واستيراد وتحقق مستقل لـOfficial Complete Daily EOD ومقام الجلسات.
- `src/kubo/data_foundation_reconciliation.py`: إعادة فحص المكونات وإصدار تقرير البوابات الاثنتي عشرة.
- `src/kubo/tri_security_pilot.py`: سجل الدفعات الثلاثية وتجهيز Workspace لتأهيل البيانات بلا Forecast.
- `src/kubo/tri_security_receipts.py`: إيصال تشغيل وربط مرحلة خارجيان، بمفتاحين مستقلين وحدود ادعاء مغلقة.
- `src/kubo/research_rank.py`: ترتيب الأدلة مع Dedup وتعارض المصادر.
- `src/kubo/request_contracts.py`: عقد الطلب المرن وحدود الحقول.
- `src/kubo/reporting.py`: مخرجات JSON وMarkdown حسب الطلب.
- `src/kubo/liquidity.py`: قياسات السيولة ومحاكاة تنفيذ محافظة.
- `src/kubo/pipeline.py`: المسار الافتراضي الجديد والمسار التاريخي المنفصل.
- `src/kubo/cli_v3.py`: واجهة الأوامر.
- `schemas/parsed-research-inputs.schema.json`: عقد الانتقال الصريح من البايتات المتحققة إلى الأحداث والتعرضات ومدخلات العوامل والتصرفات.
- `schemas/`: عقود JSON Schema القابلة للقراءة الآلية.
- `research/methodology_registry.json`: الأبحاث والقواعد والاختبارات المنهجية.
- `.github/workflows/ci.yml`: Compile وUnit/Adversarial Tests وSmoke Check وSecret Guard.
- `tests/test_source_network.py`: اختبارات الشبكة الخصمية.
- `research/manual_access_notes_2026-08-07.json`: ملاحظات تاريخية غير قابلة للاستخدام كـLive Probe أودليل إصدار.
- `docs/SOURCE_NETWORK_REPLACEMENT_AR.md`: تقرير تاريخي لمرحلة استبدال الشبكة قبل إصدار `0.1.0` الحالي.
- `docs/V3_1_HARDENING_AR.md`: لقطة تاريخية لتدقيق V3.1؛ الأرقام النهائية الحالية موثقة في `docs/BUILD_STATUS_AR.md`.
- `docs/OPERATIONS_AR.md`: طريقة بناء تشغيل حقيقي.
- `docs/BENCHMARK_OFFICIAL_EOD_V0_2_AR.md`: تشغيل Benchmark وOfficial EOD والمصالحة النهائية وحدود الأدلة.
- `docs/TRI_SECURITY_RUN_RECEIPT_V0_1_AR.md`: عقد المصادقة وربط الخطة والمقام والنافذة وشجرة المرحلة.
- `docs/CURRENT_DATA_FOUNDATION_STATUS_AR.md`: الحالة المتراكمة الحالية والبوابات الخارجية المتبقية.
- `docs/KUWAIT_120D_NEXT_SESSION_AR.md`: عقد البحث المطول، معنى 50 نطاقًا، وحدود اختبار الأربعين الأخيرة.
- `docs/BOOTSTRAP_ARCHIVE_AR.md`: معمارية KU-BO-014، شكل مساحة العمل، بوابات المراحل، وحدود عدم الجمع.
- `docs/legacy_v2/`: وثائق V2 التاريخية للرجوع، وليست مسار التشغيل الافتراضي.

## الحد الفاصل المهم

نجاح الشبكة يعني أن الأدلة الحالية كافية لترتيب بحثي محدود النطاق. لا يعني أن السهم سيرتفع، ولا أن هناك نسبة نجاح، ولا أن الشراء ممكن بالسعر الظاهر. تحويل النتيجة إلى احتمال أو ادعاء دقة يحتاج Forecasts مستقبلية مختومة، Outcomes منفصلة، Denominator كامل، تكاليف، واختبارًا زمنيًا لم تُغيّر سياسته بعد رؤية النتائج.

## حدود النسخة 0.1.0

النواة العامة والاختبارات وCLI تعمل بلا Credentials. أما مساهمة المصادر المحمية وExecution-grade data فتتوقف عمدًا على التفويض وEntitlement القانوني، وعلى سجل الثقة الخارجي المصادق عليه الموضح أعلاه مع مفتاح Runtime؛ غياب أي منها يحجب المصدر. لا يحتوي المستودع على Cookies أوTokens أوسجل ثقة تشغيلي، ولا يدّعي أن Connector غير مفوض يعمل. كما لا يصف Synthetic Smoke Check بأنه Backtest أوأداء حقيقي. وعند تشغيل Wheel من خارج Checkout، يجب تمرير `--project-root` إلى نسخة من المستودع تحتوي ملفات `config/`؛ فالـWheel ليس حزمة إعداد مستقلة.

## الترخيص

المشروع Proprietary وجميع الحقوق محفوظة باسم Mohamed Samir Rashed Shaheen. الاطلاع على المستودع لا يمنح حق الاستخدام أوالنسخ أوالتعديل أوالتوزيع؛ راجع `LICENSE`.
