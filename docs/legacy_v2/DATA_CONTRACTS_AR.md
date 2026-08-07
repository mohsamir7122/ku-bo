# عقود البيانات

## قواعد عامة

- كل Timestamp كامل وواعٍ بالمنطقة الزمنية.
- كل تاريخ مدني بصيغة ISO `YYYY-MM-DD`.
- كل Price للأسهم بوحدة `fils`، لا KWD عائم مجهول الوحدة.
- كل Raw Reference هو SHA-256 بطول 64 حرفًا ويحل إلى Manifest.
- لا تستخدم قيم Placeholder مثل `TBD`, `N/A`, `UNKNOWN` داخل بيانات مؤهلة.
- عدم الرصد ليس صفرًا.
- لا توجد ملفات Data مختلطة تجمع Raw وNormalized وFeature وOutcome.

## `manifests/file_manifest.json`

الإصدار `2.0`، ويحتوي قائمة غير فارغة من Artifacts. كل Artifact يحتاج:

- `path` داخل `raw/` فقط ومن دون Path Traversal.
- `sha256` مطابق للبايتات الفعلية.
- `size_bytes` مطابقًا للحجم.
- `source_id` موجودًا في Source Catalog.
- `source_url` ضمن Domains المصدر المسجل.
- `observed_at`.
- `provider_as_of` عند توفره، ولا يتجاوز `observed_at`.
- `content_type`.

## `manifests/collection_run.json`

يحدد:

- `pack_id`.
- `as_of`.
- `window_from`, `window_to`.
- `timezone = Asia/Kuwait`.
- `included_boards = ["cash"]` في V2.
- `run_status`: `QUALIFIED`, `INCOMPLETE`, `BLOCKED`, أو `BUDGET_EXHAUSTED`.
- ميزانية Requests/Bytes/Wall Time/Zero-yield attempts.
- الاستهلاك الفعلي.

تجاوز الميزانية من دون حالة `BUDGET_EXHAUSTED` خطأ عقدي.

## `manifests/capability_report.json`

كل Attestation يحتاج:

- Capability من Vocabulary ثابتة.
- Status صريح.
- مصادر أدوارها مسموحة لهذه القدرة.
- Raw Evidence Hashes قابلة للحل.
- مسار ملف منظم داخل `normalized/` وبصمته.
- `validator_id` يبدأ بـ`kubo.` وVersion.
- `validated_at`.
- `access_class` مصرحًا به للقدرات التنفيذية.
- Coverage Numerator/Denominator؛ حالة PASS تتطلب التطابق الكامل.
- Limitations صريحة.

المصدر الثانوي لا يثبت `daily_eod` الرسمي، وSocial لا يثبت إفصاحًا، وGoogle Drive لا يثبت أي قدرة سوقية.

## `security_master.csv`

الحقول المطلوبة:

`security_code, ticker, isin, name_ar, name_en, board, market_segment, currency, valid_from, valid_to, listing_status, raw_sha256`

العقد:

- Currency للسوق النقدي `KWD`.
- فترات الصلاحية غير متداخلة لنفس Code/Board.
- ISIN، إذا وجد، صالح ولا يتصادم مع ورقة أخرى في فترة متداخلة.
- Ticker لا يُستخدم مفتاح Join وحيدًا.

## `security_status_history.csv`

الحقول المطلوبة:

`security_code, board, status, effective_from, effective_to, reason_code, notice_id, raw_sha256`

الحالات المدعومة تشمل `TRADING`, `SUSPENDED`, `HALTED`, `DELISTED`, `LISTED_NOT_YET_TRADING`. تمنع الفترات المتداخلة.

## `trading_calendar.csv`

الحقول المطلوبة:

`trade_date, is_trading_day, session_type, session_regime_id, continuous_start, continuous_end, trade_at_last_end, raw_sha256`

يجب وجود صف لكل يوم مدني في نافذة الحزمة، لا لأيام التداول فقط. يوم التداول يحتاج Session Regime وأوقاتًا صالحة.

## `eod_ohlcv.csv`

الحقول المطلوبة:

`trade_date, security_code, ticker, open_fils, high_fils, low_fils, close_fils, volume, value_traded_kwd, trade_count, reference_price_fils, trading_status, corporate_action_status, raw_sha256`

العقد:

- صف وحيد لكل Security/Session متوقعة.
- صف `TRADED` يحتاج OHLC ونشاطًا موجبًا مع قيود High/Low صحيحة.
- `NO_TRADE`, `SUSPENDED`, `HALTED` لا تحمل OHLC صناعيًا.
- `corporate_action_status` صريح.
- عدد الأزواج الفعلي يساوي Denominator المبني من Master + Status + Calendar.

## `daily_market_totals.csv`

الحقول المطلوبة:

`trade_date, board, traded_security_count, total_volume, total_value_kwd, total_trade_count, raw_sha256`

تُعاد تجميع EOD وتُطابق مع إجمالي السوق. الهدف كشف الصفوف المفقودة ووحدات القيمة الخاطئة والتكرار.

## `manifests/query_ledger.csv`

الحقول المطلوبة:

`query_id, dataset, window_from, window_to, pages_declared, pages_received, result_count_declared, rows_normalized, zero_result, raw_sha256`

يمنع العقد اعتبار «لا يوجد ملف» نتيجة صفرية. يجب إثبات Query مكتملة الصفحات، وتطابق عدد النتائج والصفوف، أو `zero_result=true` بتعدادات صفرية.

## `disclosures.csv`

الحقول المطلوبة:

`security_code, ticker, news_id, announcement_type, event_at, published_at, relation_type, original_news_id, fetched_at, raw_sha256`

كل خبر مرتبط بهوية رسمية وتوقيت نشر والتقاط. يجب أن يتصالح عدد الصفوف مع Query Ledger، وتحفظ علاقات التصحيح والاستكمال وإعادة النشر.

## `corporate_actions.csv`

الحقول المطلوبة:

`security_code, ticker, action_id, action_type, announcement_date, ex_date, record_date, payment_date, adjustment_factor, factor_status, raw_sha256`

عامل التعديل لا يستخدم إلا إذا كان `factor_status=official`. Pending ليس Fact قابلًا لإعادة حساب العائد.

## Feature Snapshot

كل صف Feature يحتاج:

- Decision/Security/Feature identity.
- `decision_at`.
- `available_at` و`fetched_at` عند الرصد.
- Capture Mode.
- Availability Grade.
- Evidence Hashes.
- Parser Version.

إذا كانت الحالة `UNKNOWN_NOT_OBSERVED` يجب أن تكون القيمة وEvidence فارغتين. لا يُسمح بتحويلها إلى صفر.

## Forecast Payload

قائمة الحقول مسموحة مسبقًا. الحقول الأساسية تشمل Decision/Security/Product/Target/Times/Horizon/Model/Entry/Eligibility/Selection/Abstention/Thesis.

ممنوع إدخال أي Outcome أو Realized/Future/Exit field. يجب أن يكون `outcome_due_at > decision_at`، وتكون Booleans حقيقية، ويوجد Score أو Probability واحد على الأقل.

## Outcome Artifact

Outcome منفصل عن Ledger، ويثبت:

- وقت النتيجة المطابق للوقت المجمد.
- أسعار السوق القابلة للمقارنة.
- أسعار التنفيذ عند Fill.
- Benchmark entry/exit.
- Corporate Action factor والتوزيعات.
- Fees/Spread/Slippage/Impact.
- Fill Status.
- Evidence Hashes للسعر والBenchmark والإجراء والنتيجة.

المقيّم يعيد الحساب ولا يثق في Return جاهز.
