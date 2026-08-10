# Benchmark History وOfficial Complete Daily EOD v0.2

## الهدف وحدود الادعاء

تضيف هذه المرحلة عقود جمع واستيراد وتحقق لبيانات `Benchmark History` و`Official Complete Daily EOD`، ثم تعيد فحص كل مكونات حزمة الـData Foundation في تقرير واحد. لا تحتوي الشجرة على بيانات سوق حقيقية، ولا تمنح القوالب أو الـfixtures حالة `DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST`.

الحالة الصحيحة دون exports رسمية أو مرخّصة ومراجَعة هي `PARTIAL` أو `BLOCKED`. لا يجوز تغييرها يدويًا إلى Ready، ولا يكفي `source_id` أو `review_status` لإثبات أن البيانات حقيقية أو مسموح استخدامها.

## 1. Benchmark Registry

السجل `config/pilot/benchmark_registry.json` يحدد لكل سلسلة:

- `benchmark_code` داخلي في namespace اسمه `KU_BO_INTERNAL`؛
- الاسم والمصدر والعملة والوحدة؛
- `BROAD_MARKET` أو `SECTOR`؛
- `PRICE_INDEX` أو `TOTAL_RETURN_INDEX`؛
- تاريخ الفاعلية وحالة تعريف السلسلة؛
- طريقة الوصول ومتطلب حقوق الاستخدام.

الأكواد الحالية متطلبات داخلية غير موثقة كأكواد مزود أو كتواريخ إطلاق تاريخية. لذلك يبقى `registry_state=UNVERIFIED_SEED`، ولا يجوز استخدام هذا السجل وحده كدليل رسمي.

التفريق التالي إلزامي:

```text
PRICE_INDEX != TOTAL_RETURN_INDEX
BROAD_MARKET != SECTOR
DAILY_CLOSE != INTRADAY
```

لا يسمح المستورد باستبدال سلسلة غائبة بسلسلة أخرى، ولا يعمل `forward fill`، ولا ينشئ صفوفًا غير موجودة في الـraw export.

## 2. Benchmark workspace والاستيراد

إنشاء مساحة عمل غير قابلة للكتابة فوق محتوى سابق:

```bash
kubo-data-foundation --project-root . prepare-benchmark-history \
  --official-foundation-root <official-foundation-root> \
  --output-root <empty-benchmark-workspace> \
  --run-id <run-id> \
  --window-from YYYY-MM-DD \
  --window-to YYYY-MM-DD
```

يجب ملء كل export مصرح به تحت مساحة العمل. عقد CSV الخام لكل سلسلة هو:

```text
trade_date,benchmark_value
```

ويحفظ الـmanifest لكل export: `SHA-256`، وURL المصدر، ووقت الرصد، والنافذة، وعدد الصفوف والصفحات، وحالة المراجعة، وحقوق الاستخدام، وتصنيف الأدلة. الحالات `ZERO_RESULT` و`UNAVAILABLE` حالات صريحة وليستا تصريحًا باستخدام مؤشر بديل.

الاستيراد:

```bash
kubo-data-foundation --project-root . import-benchmark-history \
  --official-foundation-root <official-foundation-root> \
  --workspace <completed-benchmark-workspace> \
  --output-root <empty-benchmark-output> \
  --imported-at <ISO-8601-aware-timestamp>
```

الناتج الطبيعي هو `normalized/benchmark_history.csv` مع ربط كل صف بـ`raw_sha256`، ومراجعة التواريخ مقابل جلسات التداول الرسمية، وفحص الازدواج والفجوات والترتيب والقيم غير الممكنة والعملة والوحدة والنوع. يجب أن يكون `observed_at` بعد إغلاق الجلسة وألا يتجاوز `imported_at` أو ساعة التشغيل. يعرض التقرير مصفوفة المقارنات الممكنة لكل Product ولا يساوي بين Price وTotal Return. ولا يحول وصف `PUBLIC_OFFICIAL_EXPORT` داخل manifest البايتات إلى دليل حقيقي؛ تبقى `LIVE_DEPENDENT` إلى أن يوجد إيصال التقاط خارجي مصادق عليه يربط الـSHA-256 نفسه بالمصدر وحدث الالتقاط.

## 3. Official Complete Daily EOD

هذا العقد مستقل عن `research_price_history`. الأخير بيانات بحثية ثانوية ولا يتحول إلى Official EOD بسبب اكتمال OHLC.

المقام هو حاصل ضرب أكواد الأسهم المعلنة في كل جلسات التداول الرسمية داخل النافذة. يجب وجود صف واحد فقط لكل `(trade_date, security_code)` وبإحدى الحالات:

```text
TRADED
NO_TRADE
SUSPENDED
HALTED
TRADED_THEN_SUSPENDED
NOT_LISTED_OR_NOT_ELIGIBLE
```

القواعد الأساسية:

- الربط يكون بـ`security_code` وهوية effective-dated؛ ولا يكفي Ticker.
- لا تُرجع Current Snapshot إلى الماضي.
- صف غير متداول لا يحتوي OHLC مصطنعًا أو نشاطًا موجبًا.
- الحقول الرسمية غير المتاحة لا تُشتق من مصدر ثانوي ثم تُسمى Official.
- `currency=KWD` ووحدة السعر وبنية `RAW_UNADJUSTED` أو `OFFICIALLY_ADJUSTED` معلنة.
- اختلاف مزودين يدخل `quarantine/provider_disagreements.csv` ولا يُحسم باختيار القيمة الملائمة.
- غياب حقول أو مزود أو Market Totals يبقى `PARTIAL` ولا يسمح بادعاء Complete EOD.

يجب التصريح بطريقة الالتقاط في كل Provider وMarket Totals، ولا تُستنتج من اسم المصدر:

```text
PUBLIC_OFFICIAL_DOWNLOAD
USER_PROVIDED_OFFICIAL_EXPORT
LICENSED_VENDOR_EXPORT
RECORDED_AUTHORIZED_FIXTURE
SYNTHETIC_GENERATED
```

تُرفض التركيبات المتناقضة بين `capture_mode` وتصنيف الدليل والحقوق وفئة المصدر. ولا يُمنح `RAW_DOWNLOAD` إلا لـ`PUBLIC_OFFICIAL_DOWNLOAD`؛ أما export رسمي يقدمه المستخدم فيبقى `USER_EXPORT` حتى لو كان نطاق المصدر رسميًا.

إنشاء مساحة العمل:

```bash
kubo-data-foundation --project-root . prepare-official-eod \
  --official-foundation-root <official-foundation-root> \
  --status-history-root <status-history-root> \
  --output-root <empty-eod-workspace> \
  --run-id <run-id> \
  --window-from YYYY-MM-DD \
  --window-to YYYY-MM-DD
```

عقد export الأساسي:

```text
trade_date,security_code,ticker,trading_state,open_fils,high_fils,low_fils,close_fils,volume,value_traded_kwd,trade_count,reference_price_fils
```

وعقد الإجماليات الاختياري:

```text
trade_date,board,scope,traded_security_count,total_volume,total_value_kwd,total_trade_count
```

الاستيراد والتحقق المستقل:

```bash
kubo-data-foundation --project-root . import-official-eod \
  --workspace <completed-eod-workspace> \
  --official-foundation-root <official-foundation-root> \
  --status-history-root <status-history-root> \
  --output-root <empty-eod-output> \
  --run-id <run-id> \
  --imported-at <ISO-8601-aware-time>

kubo-data-foundation --project-root . validate-official-eod \
  --official-eod-root <eod-output> \
  --official-foundation-root <official-foundation-root> \
  --status-history-root <status-history-root>
```

`validate-official-eod` يعيد قراءة البايتات وحساب hashes وفحص المقام والهوية والحالة والإجماليات؛ ولا يكرر Status محفوظًا في تقرير الاستيراد دون تحقق.

### مصدر رسمي حقيقي أوLicensed provider

تصنيف ملف رسمي بأنه `PROVEN_REAL_EVIDENCE` داخل manifest ليس جذر ثقة مستقلًا. وكذلك `RuntimeTrustRegistry` المصادق عليه يثبت هوية المصدر أوالنطاق أوالـentitlement، لكنه لا يثبت أن البايتات ذات الـSHA-256 المحدد خرجت فعلًا من المزود. لذلك يبقى المصدر الرسمي الحالي `LIVE_DEPENDENT`، ويبقى المصدر المرخص `LICENSED_FEED_DEPENDENT`، حتى عند نجاح سجل الثقة.

الترقية المستقبلية إلى `PROVEN_REAL_EVIDENCE` تحتاج إيصال التقاط خارجيًا مصادقًا عليه يربط المصدر والمزود وSHA-256 الخام ووقت الالتقاط والنافذة والاستعلام والأعداد وأكواد الـPilot والحقوق. لم يُقدَّم مثل هذا الإيصال في هذه المهمة.

إذا كان المصدر مرخّصًا، يظل تمرير `--runtime-trust-registry` من مسار خارج workspace وoutput شرطًا لازمًا لإثبات authority/entitlement، لكنه غير كافٍ لإثبات بايتات الالتقاط. يتحقق CLI من HMAC باستخدام:

```text
KUBO_RUNTIME_TRUST_HMAC_KEY
KUBO_RUNTIME_TRUST_HMAC_KEY_ID
```

لا تُحفظ قيمة المفتاح أوTag المصادقة داخل النتائج. وجود اسم ترخيص في الـmanifest وحده ليس إثبات entitlement، ونجاح entitlement وحده ليس إثبات capture.

عند إعادة التحقق من licensed output يجب إعادة تمرير `--runtime-trust-registry` نفسه إلى `validate-official-eod`. غيابه يجعل التحقق يفشل مغلقًا؛ ووجوده لا يرفع التصنيف عن dependency من دون إيصال الالتقاط المرتبط بالـartifact.

## 4. Corporate Actions وStatus

المصالحة تفصل بين:

```text
reference_price_factor
historical_continuity_factor
position_quantity_multiplier
return_price_multiplier
cash_component
```

Normal Cash Dividend يستخدم Raw Price مع Cash Component مستقل. وتبقى Rights Issue أو Complex Action ذات policy أو factor غير مكتمل عائقًا للنتائج المتأثرة. كما لا تُعامل جلسات `SUSPENDED` أو`HALTED` كقيمة سعر مفقودة عادية.

في المصالحة النهائية، كل صف كامل من factor/policy يُربط بـ`action_id` و`security_code` و`ticker` و`ISIN` و`ex_date` مع الهوية الفعالة والتقويم الرسمي وStatus interval واحد. إذا كان تاريخ الإجراء داخل نافذة EOD فيلزم صف EOD واحد متوافق؛ وإذا كان خارجها لا يُخترع صف. كما تُراجع تغطية Benchmark ونوع `PRICE_INDEX`/`TOTAL_RETURN_INDEX` من دون تطبيق معامل Corporate Action على سلسلة Benchmark نفسها. الصف القديم الذي يفتقد تاريخًا يبقى `PARTIAL`، أما الهوية المجهولة أوالتعارض أوالتاريخ غير الصالح فيصبح `BLOCKED`.

## 5. Outcome-session policy

الملف `config/pilot/outcome_session_policy.json` متعمد أن يكون `UNFROZEN`. قرار المرور عبر جلسات التعليق أو الإيقاف يغير زمن النتيجة والعائد، لذلك سُجل `KU-BO-008-D01` في `docs/codex/USER_DECISIONS.md` بدل اختلاق سياسة مالية.
وعقد v1 يرفض كل قيمة `FROZEN`: مجرد commit لخيار المرور العالمي (Option 1)
لا يُعد موافقة. فتح المسار لاحقًا يحتاج قرارًا مسجلًا وعقدًا product-specific
يحدد maximum extension وterminal treatment؛ والحساب الحالي لخيار 1 في الاختبار
مجرد structural exercise غير authoritative.

ما دام القرار مفتوحًا، يصدر التقرير:

```text
OUTCOME_SESSION_POLICY_NOT_FROZEN
```

ولا يسمح بجاهزية Backtest حقيقي.

هذا الحظر مطبق أيضًا عند نقطة التسجيل والتقييم، وليس نصًا في التقرير فقط:

- `ForecastLedger` يرفض أي `CREATE` أو`AMEND` حقيقي ذي `horizon_sessions` إذا
  لم يكن `outcome_due_at` مشتقًا من Policy product-specific مع قرار مصادق عليه ومن
  تقويم جلسات وحالة ورقة point-in-time مربوطين بالـhashes. الحساب بعدد الأيام
  المدنية ممنوع، كما لا تُحسب جلسة `SUSPENDED` أو`HALTED` ضمن الأفق.
- المدخلات الهيكلية و`manifest_hashes` التي يقدمها المستدعي لا تثبت أن بايتات
  التقويم والحالة رسمية. لذلك يبقى التسجيل الحقيقي محجوبًا أيضًا بواسطة
  `OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED` حتى يوجد إيصال
  التقاط خارجي مصادق عليه يربط البايتات نفسها.
- لا يقبل المسار duck-typed أوsubclass authority، ولا يتيح الـvalidator العام
  flag لتعطيل السلطة. كما أن أحداث `IMPORTED/WITHDRAW/EXPIRE` تقبل payload
  مطابقًا تمامًا لـ`{"reason": "..."}`؛ تهريب حقول Forecast خلالها يحظر append
  وverify وseal حتى لو أعيد حساب كل hashes.
- `evaluate_forecasts` الافتراضي يعيد `STOP_BACKTEST` و`metrics=null` من دون
  Final Data-Foundation Authority Receipt مستقل. تمرين العقد التركيبي يحتاج
  اختيار `SYNTHETIC_CONTRACT_ONLY` صراحة، لكنه يعيد أيضًا `metrics=null` ولا
  يكشف IC أوReturn أوBrier؛ ويظل non-claim ولا يمكن ختم سجله كـPASS.

## 6. Final reconciliation

ينشئ الأمر حزمة جديدة فقط، ويعيد حساب hashes لكل المدخلات:

```bash
kubo-data-foundation --project-root . build-data-foundation-packet \
  --official-foundation-root <official-foundation-root> \
  --status-history-root <status-history-root> \
  --ca-enrichment-root <ca-enrichment-root> \
  --research-price-history-root <research-price-root> \
  --benchmark-root <benchmark-output> \
  --official-eod-root <eod-output> \
  --output-root <empty-final-output>
```

ويعرض التقرير:

```bash
kubo-data-foundation --project-root . print-data-foundation-gate-report \
  --path <final-output>/reports/data_foundation_gate_report.json
```

ترتيب البوابات ثابت:

```text
POINT_IN_TIME_IDENTITY
TRADING_CALENDAR
SECURITY_STATUS_HISTORY
PRICE_DENOMINATOR
PRICE_EVIDENCE
PRICE_CORPORATE_ACTION_QA
BENCHMARK_HISTORY
BENCHMARK_EVIDENCE
MARKET_TOTAL_RECONCILIATION
QUERY_AND_PAGINATION_COMPLETENESS
RUNTIME_SECRET_GUARD
CLAIM_BOUNDARIES
```

الحالة `DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST` لا تصدر إلا إذا نجحت كل البوابات الحرجة على Evidence حقيقية غير اصطناعية، مع حقوق استخدام متوافقة وسياسة outcome product-specific بقرار مصادق عليه؛ v1 الحالي يمنع `FROZEN`. وإلى أن يُنفّذ إيصال نهائي مستقل مصادق عليه يربط التقرير والحزمة وكل بصمات المكونات والسياسة وفحص المستودع، يرفض الـreader والـschemas أي READY محفوظ حتى لو أُعيد حساب الهاشات المحلية. Fixtures تختبر العقود فقط.

## 7. مصادر البيانات الخارجية

المصدر الرسمي العام يثبت وجود Market وSector indices والفرق المنهجي بين Price Return وTotal Return، لكن استخراج history الكامل قد يعتمد على بوابة البيانات أو export مرخص. وكذلك Complete Daily EOD قد يحتاج export رسمي أو licensed feed لتغطية كل الحقول والمقام. لا يحاول الكود تجاوز Login أو Access Controls، ولا يحفظ أي export Runtime داخل المستودع.
