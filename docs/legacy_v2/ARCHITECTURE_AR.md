# المعمارية وحدود المسؤولية

## المبدأ المركزي

كل طبقة تصدر Artifact مستقلًا، ولا يحق للطبقة التالية اختلاق مدخل ناقص. المسار هو:

`Source Catalog → Raw Evidence → Capability Attestation → Normalized Pack → Point-in-Time Features → Model Card → Forecast Ledger → Execution Assessment → Outcomes → Evaluation`

## طبقة المصادر

`config/sources.json` لا يعني أن كل مصدر يعمل الآن. هو Policy Catalog يحدد:

- دور المصدر.
- Domain المسموح.
- طرق الوصول المشروعة.
- القدرات التي يمكن للمصدر أن يساهم فيها.
- نوع التأخير.
- هل يصلح كدليل سوقي أم للتخزين فقط.

الأدوار منفصلة:

- `OFFICIAL_TRUTH`: البورصة والجهة المنظمة.
- `AUTHORIZED_TAPE`: مزود مرخص أو Broker مصرح به.
- `ISSUER_PRIMARY`: علاقات المستثمرين الرسمية.
- `DISCOVERY`, `CROSS_CHECK`, `CONTEXT`: اكتشاف وسياق ومقارنة.
- `SENTIMENT`: انتباه وانتشار، لا حقيقة رسمية.
- `STORAGE_ONLY`: تخزين Artifacts، لا دليل سوقي.

## طبقة الأدلة والقدرات

`EvidenceManifest` يتحقق من البايتات الخام. ثم `CapabilityReport` يتحقق أن القدرة:

- مدعومة بمصدر ذي دور مسموح.
- مرتبطة ببصمة خام موجودة.
- مرتبطة بملف منظم محفوظ ببصمته.
- مرت عبر Validator ذي Version.
- لديها Numerator وDenominator متصالحان.
- تستخدم Access Class مصرحًا به إذا كانت قدرة تنفيذية.

بعد ذلك فقط يشغّل `PackValidator` تحققًا دلاليًا لكل Dataset. وجود CSV لا يكفي.

## طبقة الهوية والكون

`IdentityResolver` يحتاج `security_code` أو ISIN، مع Board وتاريخ. Ticker وحده مرفوض.

الكون اليومي يُبنى من:

- Security Master الفعال في التاريخ.
- Status History الفعال في التاريخ.
- Calendar يثبت أن اليوم جلسة.

كل ورقة مؤهلة تحتاج صف EOD، حتى لو كانت `NO_TRADE` أو `SUSPENDED`. هذا هو Denominator الذي يمنع Survivorship وSelection Bias.

## طبقة الأحداث والميزات

LLM/NLP المقترح هنا مستخرج أدلة:

- يربط الحدث بالورقة الرسمية.
- يصنف نوع الحدث واتجاهه وجدته.
- يحفظ النص الخام والبصمة.
- يحدد العلاقات: Original, Supplementary, Corrective, Republished.

لا يعطي LLM قرار شراء مباشرًا. `canonicalize_events` يدمج النسخ، و`build_event_features` يستخدم فقط ما كان متاحًا قبل Cutoff.

## طبقة المنتجات والطرق

المنتج يثبت مسبقًا:

- الأفق بالجلسات، لا بأيام مدنية مبهمة.
- Target Rule.
- الكون المؤهل.
- Benchmark.
- سياسة التكلفة والتنفيذ.
- قدرات البيانات المطلوبة.
- الحد الأدنى المبدئي للتواريخ المستقلة.

الطريقة لا تدخل المنتج إلا إذا كانت تدعم المنتج وتملك كل القدرات المطلوبة. ترتيب الاختبار المقصود:

1. Baselines السوق والقطاع والسيولة.
2. Price/Activity مع continuation وreversal منفصلين.
3. Official Event Study.
4. Ranker خطي منتظم وشفاف.
5. Social Ablation بعد الطبقات السابقة.
6. نموذج غير خطي محدود فقط إذا تفوق خارج العينة.
7. Microstructure محجوب حتى يصل Feed التنفيذ.

## طبقة Model Card

Model Card هو عقد الإصدار، لا وصف تسويقي. يربط:

- Product وTarget وHorizon.
- Feature Availability Rules.
- Training وCalibration وLocked Test Windows.
- Purge وEmbargo.
- Baselines وMetrics حسب النافذة والنظام السوقي.
- Costs, Fills, Abstention, Calibration.
- Trial Registry وHashes للكود والنموذج والسياسة.
- Retirement Triggers.

الحالات تتدرج من `CANDIDATE` حتى `PROSPECTIVE_VALIDATED`. لا يسمح Probability قبل الحالة الأخيرة وعقد مكتمل.

## طبقة السجل

`ForecastLedger` يفصل Process Assessment عن Outcome. Forecast يصدر قبل النتيجة، ويحتوي:

- Decision ID والورقة والمنتج.
- Decision Time وOutcome Due Time.
- Score أو Probability المسموح.
- الكون والميزات والكود والسياسة والتقويم ببصماتها.
- Selection وAbstention وEntry Rule.

لا يكتب Outcome في السجل. التعديل Forward-Timed Event جديد، ولا يعيد كتابة الحدث الأصلي.

## طبقة التنفيذ

`assess_execution` يختبر:

- Access Class مصرحًا به.
- Entitlement ID.
- Raw Evidence قابل للحل.
- Provider/Observed/Decision timestamp order.
- عمر Snapshot.
- Market Phase.
- Trading Status.
- Bid/Ask صالحين.
- عدم الوقوف عند +10% أو -5% كحالة تنفيذ عادية.

النتيجة إما `EXECUTABLE` أو `DETECTED_NOT_EXECUTABLE`؛ اكتشاف الحركة لا يساوي القدرة على الدخول.

## طبقة القرار

`HIGH_BUY_OPPORTUNITY` لا يصدر لمجرد Score مرتفع. يحتاج:

- Pack وIdentity وTiming وUniverse وCorporate Actions وFeature Snapshot وPolicy Hash ناجحة.
- Model Card بحالة `PROSPECTIVE_VALIDATED`.
- Expected Edge أعلى من Cost + Safety Margin.
- Execution Assessment ناجح.

دون تنفيذ يمكن، في أفضل الحالات، إصدار `QUALIFIED_RESEARCH_NOT_YET_EXECUTABLE`.

تصنيفا `SPECULATIVE_PROFILE` و`INVESTMENT_PROFILE` وصفان لخصائص الورقة، وليس أحدهما Target أو Recommendation.

## طبقة Stop Gates والتقييم

قبل Backtest يجب وجود عشر بوابات أساسية، منها Artifact Resolution وLedger/Seal وLeakage وFull Denominator وIdentity وCorporate Actions.

- فشل Critical Gate يعيد `STOP_BACKTEST`.
- العقود صحيحة لكن العينة ضعيفة تعيد `STOP_INFERENCE`.
- فقط الحالة `READY_TO_SCORE` تسمح بحساب Metrics.

التقييم يعيد حساب العوائد والتكاليف، ويعرض Rank IC وPrecision وRecall وNet Excess وNon-fill وBrier عند السماح بالاحتمال. لا توجد Metric Headline من دون Coverage = 1 للكون المجمد.
