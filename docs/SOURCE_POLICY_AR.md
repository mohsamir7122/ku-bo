# سياسة مصادر V3

## المبدأ

لا توجد قائمة «مصادر موثوقة دائمًا». توجد أدوار وحدود. كل تشغيل يختبر الوصول والجودة والتوقيت من جديد، ويحفظ الدليل الخام. المصدر المتاح اليوم قد يصبح محجوبًا أو تالف الـParser غدًا.

## ترتيب الاستخدام

ابدأ بالمصادر التي تحقق الأدوار المطلوبة بأقل تكلفة وبأعلى استقلال. استخدم الرسمي/جهة الإصدار لتأكيد الحقائق الرسمية، والمصادر المنظمة للمقارنة السوقية، والأخبار للسياق، والمجتمع للمزاج فقط، والأرشيف للبحث عن السياق والروابط القديمة.

لا يشترط نجاح بورصة الكويت كي يبدأ Research Rank **إذا بقي إيصال هوية رسمي بديل وحديث** لكل Security مغطى. إذا تعذرت، سجل الفشل واستكمل النصاب من مصادر مستقلة، لكن لا تجعل Quorum الخبري يعوض فشل الهوية. لا تنقل صفة «رسمي» إلى مصدر تحريري؛ استخدم فقط مصدر هوية Official/Licensed مسجلًا، واجعل `official_confirmation_available = false` وخفّض المحفز الاتجاهي غير المؤكد إلى `WATCH`.

لا تُعامل أقسام المنصة الواحدة كناشرين مستقلين، ولا تعتبر إفصاحًا رسميًا مختلفًا تأكيدًا لخبر آخر عن السهم نفسه. يلزم تطابق الحدث والاتجاه، مع Raw Evidence مربوط بالمصدر الذي يُنسب إليه.

## مصادر البدء المسجلة

- بورصة الكويت: الصفحات الحالية، أرشيف التقارير، وأرشيف الإفصاحات.
- CMA/iFSAH وIssuer IR.
- Investing.com، TradingView، Argaam، MarketScreener، Mubasher، Yahoo Finance، وTradingEconomics.
- KUNA، Reuters، Zawya، Asharq Business، الراي، الأنباء، الجريدة، والقبس.
- بنك الكويت المركزي، الإدارة المركزية للإحصاء، مؤسسة البترول وشبكة شركاتها، ووزارات المالية والنفط والتجارة والجهات الاستثمارية والتنموية الكويتية المسجلة.
- Kuwait Times وArab Times وCNBC Arabia وArab News وThe National وGulf News وGulf Business وMEED وBloomberg وFinancial Times وAP، بحدود المصدر وحقوق الوصول الخاصة بكل منها.
- OPEC وIMF وWorld Bank وEIA وGCC-Stat للسياق الكلي أوالقطاعي المنسوب إلى أصله.
- IndexSignal، Telegram public previews، وTradingView Ideas.
- Wayback Machine، Common Crawl، والبحث على الويب.
- ICE وAuthorized Broker Feed عند وجود Entitlement.

القائمة الكاملة وعقود النطاق في `config/source_network.json`.

وجود المصدر في الكتالوج لا يعني وجود Connector أوParser. المرجع الآلي لذلك هو `config/source_capabilities.json`: الحالة الافتراضية `DEFINED_ONLY`، والمحللان الحاليان لبورصة الكويت وInvesting مصنفان `END_TO_END_TESTED` على Fixtures مولدة مع `live_operational = false`. لا تُرفع الحالة إلى `LIVE_OPERATIONAL` من دون Capture حي مصرح به واختبار قبول ومراقبة Drift.

الكتالوج الحالي يحتوي 68 تعريف مصدر تتجمع في 62 مجموعة استقلال؛ لا تستخدم الرقمين بالتبادل. بعد استبعاد أسطح البحث والتخزين توجد 59 نطاقًا مرشحًا، منها 53 نطاقًا معلنًا Enabled-public في الكتالوج، و52 نطاق Start URL مميزًا يمكن للمشغل تنفيذه قبل تطبيق الحجز العادل. الخطة الافتراضية تحاول 50 نطاقًا، لكن المحاولة لا تصبح Finding، والنطاق لا يساوي ناشرًا مستقلًا، وإعادة النشر لا تصبح تأكيدًا جديدًا.

حالة القدرات الحالية هي 66 `DEFINED_ONLY` و2 `END_TO_END_TESTED` على Fixtures مولدة و0 `LIVE_OPERATIONAL`. هذه الأرقام تفصل التسجيل عن القدرة التشغيلية، ولا يجوز وصف الـ52 التنفيذية أوالـ53 المعلنة أوالـ59 المرشحة بأنها مصادر حية.

## سياسة البحث المطول لـKU-BO-012

يبحث `KUWAIT_120D_NEXT_SESSION_RESEARCH` في موجات ثابتة:

1. الرسمي والرقابي؛
2. جهة الإصدار والحكومة؛
3. البيانات المنظمة والتحريرية؛
4. المجتمع والأرشيف وتوجيه البحث.

الهدف Attempt Coverage هو 50 نطاقًا مميزًا، وليس شرطًا اصطناعيًا لإيجاد نتيجة. يختار Fair planner مساهمات نطاق جديدة `17/0/29/4` بالترتيب، ويحجز الأربعة الأخيرة للأرشيف/المجتمع: `archive.org` و`commoncrawl.org` و`indexsignal.com` و`t.me`. لا تضيف أسطح Investing وTradingView المجتمعية نطاقين جديدين لأن ملكيتيهما احتُسبتا في الموجة الثالثة. أما `web_search_router` فهو `SEARCH_ROUTER_CATALOG_ONLY_NOT_EXECUTED` ولا ينشئ Finding.

لكل استراتيجية ثلاث محاولات إجمالية عند Timeout أوDNS أوTLS أوHTTP 429 أوHTTP 5xx. Hard block لا يعاد. يظل 429 في الاستراتيجية نفسها ثم يتوقف المصدر بعد المحاولة الثالثة، ولا يدور حول Rate limit باستراتيجية أخرى. يُحترم `Retry-After` من دون اختصاره إذا سمحت Wall budget؛ وإذا تجاوز الوقت المتبقي أوفشل Sleeper يتوقف المسار Fail-stop. إذا استجاب الموقع استجابة صحيحة لكنها فارغة، تُجرب حتى أربع صيغ مختلفة جوهريًا في المصطلح أواللغة أونوع الصفحة أوالفترة؛ إعادة عنوان URL نفسه لا تُحسب استراتيجية جديدة.

Login وCAPTCHA وPaywall وRobots وHTTP denial الصريح حالات Terminal لذلك المسار. يسجل النظام وقت المحاولة والاستراتيجية والحالة والرابط النهائي وفئة الخطأ وHash الاستجابة وإجراء الاسترداد، ولا يتجاوز الحماية. فشل مصدر لا يوقف أسهمًا غير مرتبطة؛ يخفض التغطية أوالثقة أوينتج `ABSTAIN` عند الحاجة.

يحفظ Attempt Ledger كذلك `retry_after_seconds` وMaterial query-route proof والـDisposition والـLimitations. وتعلن نتيجة التشغيل صراحة أن Ledger hash chain ليست External Seal، وأن Capture timestamp ليست Evidence publication timestamp، وأن Low-level HTTP requests لا تُقاس كل واحدة على حدة، وأن Parser يجب أن يفرض cutoff، وأن Zero Result لا يقبل بلا Unique material-route proofs.

بعد الحفظ، يجب إعادة فتح Source Search run بمدققه المخصص. يعيد المدقق Hash التقرير وLedger والـRaw artifacts المشار إليها ويتحقق من Schema والمسارات والتوقيت قبل التكامل. لا يكفي نجاح العملية داخل الذاكرة أووجود ملف باسم متوقع.

الانتقال من Raw capture إلى البحث لا يحدث ضمنيًا. يقبل `build-kuwait-research-bundle` فقط `parsed-research-inputs` صريحة ترتبط Hashes فيها ببايتات التشغيل المتحقق، ثم يعيد التحقق من Context Events وSecurity Exposures وFactor Snapshot ويكتب الحزمة Atomically. الجسر لا يقرأ الخبر دلاليًا ولا يخترع Exposure أوFactor أوDisposition أوScore؛ غياب Parser مناسب يبقى نقصًا معلنًا.

Corpus السياق تراكمي وله Watermark. يحتفظ بـ120 يومًا للسياق العام، و30 يومًا للأحداث النشطة، و7 أيام فقط للمجتمع، و72 ساعة للمحفز الحديث. لا يعاد تنزيل الأشهر الأربعة كلها في كل سؤال عادي.

## قواعد المجتمع والمنتديات

- لا Price/Volume/Official Event/Catalyst/Fundamental من المنتدى.
- لا اعتماد على Screenshot أو Forward أو Search Snippet.
- لا مضاعفة للدرجة بسبب تكرار المنشور.
- لا نسبة أكثر من سقف المزاج المحدد للأفق.
- لا مساهمة مجتمع في الأفق الطويل أو منتجات التنفيذ.
- Telegram وIndexSignal مصدران للمزاج أوتوجيه رابط الأصل فقط. تعذر الوصول أوالقناة الفارغة يُسجل كما هو، ولا يصبح Blocker للسوق كله ولا حقيقة سلبية عن الشركة.

## قواعد الجودة

ارفض المصدر من المساهمة في التشغيل عند وجود Placeholder، نسبة مستحيلة، Timestamp متناقض، وحدة غير محلولة، Parser Drift، Rate-limit محتواه ناقص، أو Raw Hash غير محلول. احتفظ بمحاولة المصدر وسبب رفضها.

ارفض كذلك `QUALIFIED` عندما يساوي عدد العناصر المؤهلة صفرًا، وأي Hash مأخوذ من Artifact لمصدر آخر، وأي Artifact جُمع بعد `decision_at`. صفحة الوصول أو Search Snippet لا تصبح Market Evidence.

كل Finding يحتاج `fact_type` مسموحًا في `fact_eligibility` للمصدر، ويجب أن يطابق `source_url` عنوان الـArtifact المشار إليه حرفيًا، لا أن يكتفي بمشاركة النطاق.

## تفويض المصادر المحمية

حقول `runtime_authority` وActivation وEntitlement داخل Packet ليست تفويضًا ذاتي الإثبات. يفرض `0.1.0` للمصادر المعطلة أوالديناميكية أوالمرخصة سجل ثقة خارجيًا منفصلًا عن Packet ومصادقًا بـ`HMAC-SHA256` ومفتاح Runtime، يربط `source_id` بالـSubject/Account والنطاق وSecurity codes وActivation/Entitlement وفترة الصلاحية وKey ID. يفشل المصدر مغلقًا عند غياب السجل أوالمفتاح، أوفشل المصادقة أوعدم وجود قيد فريد مطابق، حتى لو كان إيصال Packet منظمًا.

لا تخلط KWD وFils، Board مختلفة، Last متأخرًا مع Close مكتمل، أو أسعارًا قبل/بعد Corporate Action. لا تجمع القيم المتعارضة بالمتوسط.

## الأرشيفات

يمكن لـWayback/Common Crawl إثبات أن Capture متاح بسياقه، لا أن الأرشيف كامل أو أن Capture Time هو First-public time. استخدمهما لاسترجاع صفحة أو رابط، ثم حاول الوصول إلى الأصل.

## التنفيذ

أي Price عامة متأخرة أو Last-only لا تثبت Entry أو Fill. المنتج `KUWAIT_120D_NEXT_SESSION_RESEARCH` معلن Execution-grade، ولذلك كل Selected row في Replay يحتاج `FILLED` ودليل تنفيذ، ويُطبق Spread/Slippage/Fees على المقاييس الصافية. الافتتاح، Intraday، L1/L2، Queue، وSlippage تحتاج مصدرًا مرخّصًا أو Broker Export مصرحًا به مع Entitlement وتوقيت؛ غيابها يحجب القياس ولا يخفض معيار المنتج.
