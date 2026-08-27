# حالة بناء الأساس البرمجي KU-BO 0.1.0

هذا الملف يصف ما نُفذ واختُبر داخل المستودع. لا يعلن اكتمال منصة Production، أوتوافر المصادر الخارجية، أوصلاحية النظام للتوصية أوالتنفيذ المالي.

## منفذ في الأساس البرمجي

العناصر الموروثة متحققة بحسب CI التاريخي الخاص بها. عناصر `KU-BO-012`
مضافة على فرع المهمة واجتازت بوابات القبول المحلية، ونُشرت في Draft PR #14
واجتاز رأس التنفيذ Exact-head CI. لم يحدث الدمج؛ لا تُقرأ القائمة كإعلان
Production أوMerge.

- كتالوج يحوي 69 تعريف مصدر موزعة على 63 مجموعة استقلال و60 نطاقًا مرشحًا بعد استبعاد البحث والتخزين؛ 54 منها معلنة Enabled-public في الكتالوج، و53 نطاق Start URL تنفيذيًا مميزًا قبل الحجز. هذه تعريفات سياسة وليست موصلات حية.
- خمس سياسات تغطي 14 منتجًا بحثيًا وزمنيًا، منها `KUWAIT_120D_NEXT_SESSION_RESEARCH`.
- عقد Workflow يثبت نوافذ 120 يومًا للسياق و30 يومًا للأحداث النشطة و7 أيام للمجتمع و72 ساعة للمحفزات الحديثة، مع Corpus تراكمي وWatermark.
- بحث متعدد الموجات بخطة افتراضية عادلة من 50 نطاقًا ومساهمات جديدة `17/0/29/4`. تحجز الموجة الأخيرة للأرشيف والمجتمع، فتشمل `t.me` و`indexsignal.com`، بينما يبقى Search Router مسجلًا وغير منفذ. توجد ثلاث محاولات للأخطاء العابرة لكل استراتيجية وأربع استراتيجيات مختلفة للرد الصحيح الفارغ.
- Retry fail-stop: لا إعادة للمنع الصريح، و429 يتوقف بعد ثلاث محاولات في الاستراتيجية نفسها؛ يُحترم `Retry-After` ضمن Wall budget فقط، ويتوقف المسار إذا تجاوزها أوفشل Sleeper. يحفظ Ledger الـDisposition وRetry-After وLimitations، ولا يدعي External Seal أوPublication time أوقياس كل Low-level HTTP request.
- مدقق تشغيل محفوظ يعيد بصمة تقرير Source Search وسجل المحاولات والـRaw artifacts. وجسر `build-kuwait-research-bundle` يربط هذه البايتات بمدخلات `parsed-research-inputs` الصارمة ثم يصدر Context/Exposure/Factor artifacts Atomically، من دون ادعاء Parser عام أوتوليد قيم من Raw bytes.
- عقود Context Event وSecurity Exposure وFactor Snapshot ومقام كامل؛ كل سهم متوقع يأخذ Disposition صريحة، والعامل المفقود لا يتحول إلى صفر. `factor_snapshot_sha256` تربط الصفوف والعوامل والأدلة والتصرفات والدرجات، وتُفرض نوافذ Freshness من سجل العوامل، ومنها 24 ساعة لحالة التداول، ولا يدخل حدث `SUPERSEDED` في Factor-eligible exposure.
- عقد Replay Execution-grade صارم لـ40 قرارًا و41 جلسة رسمية. يعيد اشتقاق Rank من Score ويفرض Top-K وFill موثقًا لكل Selected؛ يبقي Non-trading rows في المقام لكنه يعيد `STOP_BACKTEST` ما دام `KU-BO-008-D01` مفتوحًا. الـPrimary adjusted-gross label قبل تكاليف التنفيذ، بينما تطبق التكاليف على Actionable وNet-excess metrics الثانوية. لا يعلن Runtime حالة `STOP_INFERENCE` غير قابلة للوصول.
- Capture layer آمنة للملفات وPublic HTTPS مع Domain Allowlist وRobots وTimeout وMax bytes ومنع Auth/CAPTCHA/Paywall bypass. ترفض Capture Plan قبل Connector أوI/O إذا تجاوزت 32 مهمة، أو128 MiB مجموع بايتات، أو300 ثانية مجموع مهلات.
- حزمة تشغيل Per-run مع Hash وتوقيت ونطاق وميزانية ومصالحة `raw_bytes`.
- Quorum لكل ورقة مالية، لا على مستوى السوق فقط.
- ربط Raw Hash بالمصدر نفسه، ورفض Late Capture وStale Finding وAccess Receipt وSearch Snippet كدليل.
- Effective-dated identity binding في جميع النطاقات ومنع Ticker mismatch.
- تحقق Packet-level من بنية Runtime authority لمواقع الشركات والحسابات الديناميكية، ومن Activation للمصادر المعطلة، ومن Entitlement للمصادر المرخصة؛ هذه الحقول شروط اتساق وليست Root of Trust ذاتية.
- سجل ثقة خارجي `1.0` يفشل مغلقًا للمصادر الحساسة، مع مصادقة `HMAC-SHA256` بمفتاح وKey ID من Runtime وربط فريد للمصدر والحساب/Subject والنطاق وSecurity codes وActivation/Entitlement وفترة الصلاحية. يسجل ناتج التحقق Registry ID وبصمة المحتوى وKey ID ولا يسجل المفتاح.
- Dedup لإعادة النشر وNear-duplicate النصي المحافظ، ورصد تضارب المصادر المستقلة.
- Research Rank بلا Probability أوRecommendation، ورفض طلب Entry/Exit في `research_network`.
- Output Contracts بصيغتي JSON وMarkdown، بالعربية والإنجليزية، وبمستويات Brief وStandard وDeep.
- تحليل وصفي شفاف للسعر والنشاط والسيولة والأساسيات وSentiment، مع فصل Tone عنTruth.
- قياس Illiquidity ومحاكاة `NO_FILL` و`PARTIAL_FILL` وLimit Queue وSuspension.
- Purge/Embargo primitives للتحقق الزمني.
- Research Decision Ledger وOutcome stream منفصلان، Hash chain، File locking، وHMAC seal اختياري يرفض Downgrade. Outcome يتطلب Evidence packet فعليًا داخل Ledger ويعيد التحقق من Manifest والبايتات عند الإضافة والتحقق والختم، ولا يقبل Hash من المتصل.
- CLI للجمع، التحقق، التخطيط، التقارير، Ledger verification/sealing، وإضافة Outcome.
- محلل هوية خاص ببورصة الكويت ومحلل جدول تاريخ سعر خاص بـInvesting، مع مصالحة Security Code/Ticker/ISIN وفشل مغلق عند Parser Drift. اجتاز المسار اختبارًا من البايتات إلى Finding ثم Network Validation على Fixtures مولدة غير سوقية.
- مصفوفة قدرات آلية تفصل تعريف المصدر وCapture وParser وFixture evidence عن `LIVE_OPERATIONAL`؛ لا تسجل أي مصدر حيًا تشغيليًا في هذه النسخة.
- JSON Schemas وMethodology Registry ووثائق تشغيل وSecurity policy.
- GitHub Actions على Python 3.11 و3.12 و3.13 و3.14 مع Compile وFull Suite وSmoke وSecret Guard وبناء Wheel واختباره بعقد `--project-root`.
- أضيفت إلى CI مرحلة KU-BO-012 المركزة، وأضيف إلى Installed Wheel التحقق من `validate-research-workflow` ومن ظهور `run-source-search` و`build-kuwait-research-bundle` و`evaluate-forty-session-replay`. نجح Exact-head Run `31733924569` لرأس التنفيذ `58a78042d5d509e599d2e273d793856b1dee14dd` على Python 3.11 إلى 3.14.

## حالة قدرات المصادر

```text
DEFINED_ONLY:          67
END_TO_END_TESTED:      2  (generated fixtures only)
LIVE_OPERATIONAL:       0
```

إضافة المصدر أوالنطاق إلى الكتالوج لا تثبت Capture أوParser أوحق وصول. Telegram وIndexSignal يظلان Community sentiment/routing فقط، ولا يثبتان Official fact أوPrice أوCorporate Action أوCatalyst.

## نتيجة اختبار الأربعين الأخيرة

تم تفعيل عقد التقييم Fail-closed، لكن لا توجد داخل المستودع حزمة سوق حقيقية Point-in-Time تشمل 40 قرارًا و41 جلسة رسمية مع الكون الكامل والأسعار والإجراءات والحالة والنتائج. النتيجة الصحيحة حاليًا:

```text
run_status: STOP_BACKTEST
process_valid_scoreable_sessions: 0
expected_decision_sessions: 40
metrics: null
agreement_rate: null
agreement_rate_status: NOT_APPLICABLE
authority_receipt_sha256: null
authority_verified: false
accuracy_claim_allowed: false
```

`agreement_rate=null/NOT_APPLICABLE` تُعرض بشريًا `N/A` ولا تعني `0%`: لا يوجد مقام صالح لحساب النسبة. لا يجوز فتح النتائج أوحساب دقة من Fixtures مولدة.

## حالة التحقق

- اختبارات Workflow/Source Orchestrator/Ingestion/Context/Integration/Replay/CLI/Schemas المركزة: `183/183 PASS`.
- Full Suite النهائية على الشجرة الحالية: `2,067/2,067 PASS` في `164.347s`.
- `compileall` وJSON checks و`git diff --check` وSmoke وSecret Guard: `PASS`.
- توليد Corpus من `1,280` حالة وتدقيقه: `PASS`.
- Codex control check: `PASS` على 15 ملف تحكم و10 ملفات مطلوبة، مع 0 Errors و0 Warnings.
- Wheel النهائية: `PASS`؛ الحجم `444351` بايت، وSHA-256 هو `ee089ec3a7e100e81e1ef4a0378824c2b3e817db7d4c23d2d197b728b400c3a3`.
- Isolated install/imports/CLI help/`validate-research-workflow`: `PASS`؛ و`installed_data_foundation_check`: `PASS` مع 8 Semantic admissions و8 Lineages.
- GitHub Actions الخاصة بـKU-BO-012: `PASS` لرأس التنفيذ المنشور في Draft PR #14؛ Run `31733924569`، SHA `58a78042d5d509e599d2e273d793856b1dee14dd`، وكل Jobs Python 3.11/3.12/3.13/3.14 نجحت. تحديث سجل التحكم اللاحق يحتاج CI جديدًا قبل مراجعة الدمج.

## غير مكتمل عمدًا ولا يجوز الادعاء بعكسه

- لا توجد Credentials أوSessions لمنصات Investing.com أوTelegram أوMeta أوTikTok أوX.
- لا يوجد Licensed Broker/Market Feed مهيأ؛ Intraday/Opening/Execution-grade outputs محجوبة.
- Social policy definitions لا تعني أن API platform connector مفوض أوعامل.
- لا توجد Forecasts حية أوProbability معايرة أوAccuracy مثبتة.
- Near-duplicate detection محافظ قائم على النص، وليس Semantic embedding model معتمدًا.
- Entitlement receipt وسجل الثقة يتحققان محليًا ولا يستعلمان حيًا من Vendor licensing service؛ لا يوجد Entitlement تشغيلي أوFeed مرخص مهيأ داخل المستودع.
- لا يحتوي المستودع على سجل ثقة تشغيلي أومفتاح Runtime. الآلية منفذة، لكن تشغيل مصدر محمي يبقى محجوبًا حتى يقدمهما المشغل خارج Packet مع التفويض القانوني اللازم.
- Full historical backtest يظل محجوبًا حتى Point-in-Time Universe وCorporate Actions وExecution data وSealed prospective denominator.
- `KU-BO-008-D01` ما زال `OPEN`؛ سياسة تقدم جلسة النتيجة عبر التعليق/التوقف غير مجمدة Product-specific.
- لا توجد خدمة Production منشورة، أوScheduler تشغيلي، أومراقبة توافر مستمرة، أوضمان لاستقرار أي مصدر خارجي.
- لا توجد Captures حية مسجلة ومصرح بها تثبت قبول المحللين على الصفحات الخارجية الحالية. المحللان المنفذان مختبران على Fixtures تعاقدية مولدة فقط، وبقية المصادر بلا Parsers عاملة. التشغيل الحقيقي يحتاج تفويض الوصول وFixtures مصرح بها وQA ومراقبة Drift.
- CI الحالي Linux فقط. حزمة `tzdata` أصبحت Runtime dependency مثبتة تلقائيًا كي يعمل `Asia/Kuwait` على Windows أوContainer مصغر بلا System IANA tzdb؛ ولا يزال دعم منصة إضافية خارج اختبارات الـwheel المعزولة غير مُدّعى بلا CI خاص بها.

## معيار التسليم

النسخة `0.1.0` أساس هندسي قابل للتدقيق للعقود والجمع العام المحدود والتحليل البحثي المحافظ. ليست Production-complete وليست منصة توصيات حية. الانتقال إلى Forecast أوExecution أوتشغيل Production يتطلب Capabilities خارجية موثقة، وعمليات نشر ومراقبة، ثم Prospective Validation جديدة؛ ولا يجيزه مجرد نجاح الاختبارات الاصطناعية.
