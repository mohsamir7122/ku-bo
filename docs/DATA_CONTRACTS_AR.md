# عقود بيانات شبكة المصادر

## `research_run.json`

يتطلب:

- `schema_version = 3.0`.
- `run_id` فريدًا و`product_id` مطابقًا للمنتج المطلوب.
- `decision_at` بتوقيت واعٍ و`timezone = Asia/Kuwait`.
- `scope`: `NAMED_SECURITIES` أو `CANDIDATE_SET` أو `FULL_MARKET`.
- `expected_universe_count` موجبًا و`covered_universe_count` بين صفر والمتوقع.
- Budget موجبًا للطلبات والبايتات والزمن، وUsage غير سالب ولا يتجاوز الميزانية.

## `manifest.json`

كل Artifact يجب أن:

- يوجد فعليًا داخل `raw/` من دون Path Traversal.
- يطابق `sha256` والحجم المسجلين.
- يرتبط بـ`source_id` مسجل وHTTPS URL داخل نطاق المصدر.
- يحمل `observed_at` واعيًا زمنيًا و`capture_kind` معتمدًا.
- يثبت Runtime Authority أو Entitlement عندما يكون المصدر ديناميكي النطاق أو مرخّصًا.

## `universe.json`

هذا الملف مطلوب لكل Scope لإثبات الهوية الفعالة زمنيًا؛ والأعداد داخل `research_run.json` لا تكفي. يتطلب:

- `reconciliation_status = EXACT` و`membership_basis = POINT_IN_TIME_OFFICIAL`.
- قائمتي Security Codes رقمية وفريدة للمتوقع والمغطى، تطابقان الأعداد المعلنة، وتكونان متساويتين عند ادعاء التغطية الكاملة.
- مصدر عضوية من فئة Official أو Licensed وله دور `IDENTITY_REFERENCE`.
- `membership_raw_sha256` محلولًا إلى Artifact من المصدر نفسه ومحاولة مصدر مساهمة.
- صف `securities` لكل ورقة مغطاة، يربط `security_code` بالTicker خلال `valid_from`/`valid_to` الفعالين وقت القرار.
- وقوع `membership_as_of` في تاريخ `decision_at` نفسه بتوقيت الكويت وألا يكون لاحقًا له.

غياب الملف أو فشل ربط الهوية يجعل التشغيل `SOURCE_NETWORK_BLOCKED`. أما نقص تغطية السوق مع سلامة هويات العناصر المغطاة فيسمح ببحث Candidate-set فقط ويمنع `FULL_MARKET_RESEARCH_RANK`.

## `source_observations.json`

كل محاولة مصدر تسجل:

- الحالة: `AVAILABLE`، `PARTIAL`، `BLOCKED`، `ERROR`، `AUTH_REQUIRED`، أو `UNTESTED`.
- طريقة الوصول المسموح بها وتوقيت المحاولة.
- نتيجة الاستعلام: `QUALIFIED`، `ZERO_RESULT`، `BLOCKED`، `ERROR`، `AUTH_REQUIRED`، `PARSER_DRIFT`، أو `DATA_QUALITY_REJECTED`.
- الأدوار التي شوهدت، عدد العناصر المؤهلة، Zero-result الصريح، Hashes الخام، Quality Flags، والقيود.

المصدر لا يساهم لمجرد أن الصفحة فتحت. يحتاج احتساب المصدر في نصاب الأدلة إلى Evidence خام محلول، وArtifact تابع للمصدر نفسه، ونتيجة `QUALIFIED` من دون Data-quality flags، وعنصر مؤهل واحد على الأقل. تُسجل `ZERO_RESULT` فقط لإثبات أن الاستعلام نُفذ وأعاد صفرًا صريحًا؛ لا تملأ Quorum ولا ترفع Coverage. ولا يستطيع `ACCESS_RECEIPT` وحده إنشاء مساهمة.

## `findings.jsonl`

كل سطر JSON مستقل ويتطلب:

- `finding_id` فريدًا.
- `security_code` رقميًا رسميًا؛ Ticker Alias للعرض فقط.
- مصدرًا تمت ملاحظته ويساهم فعلًا، وURL ضمن النطاق.
- `published_at <= available_at <= decision_at`.
- `capture_mode` و`timing_grade` لا يتجاوز سقف المصدر.
- `raw_sha256` موجودًا في Manifest ومحاولة المصدر نفسها، وأن يكون الـArtifact من `source_id` ذاته وقد جُمع بعد إتاحة المعلومة وقبل `decision_at`.
- `evidence_roles` تربط كل Finding بالدور أو الأدوار التي يثبتها فعلًا، وتكون ضمن عقد المصدر ومحاولة التشغيل ومتوافقة مع `signal_kind`.
- `fact_type` إلزامي ويجب أن يقع داخل `fact_eligibility` المعلن للمصدر.
- `signal_kind`: Catalyst أو Price Activity أو Technical أو Fundamental أو Sentiment أو Liquidity أو Risk أو Archive Context.
- اتجاهًا، Strength وMateriality بين صفر وواحد، Origin ID، Event Key، ونص الادعاء.

قيود خاصة:

- Community: Sentiment/Risk فقط.
- Web archive: Archive Context فقط.
- Search/Storage: لا Findings.
- `SEARCH_INDEX` و`ACCESS_RECEIPT`: لا Findings، حتى لو كان الرابط أو الـHash صحيحًا.
- Licensed Execution: Entitlement إلزامي.

## `live_source_probe`

الـProbe يختبر الوصول فقط. يسجل وقت التجربة، المصدر، الحالة، URL، الملاحظة، وأعلام الجودة. نجاحه لا يُحتسب ضمن Quorum بحث حقيقي، ولا يثبت Market Fact أو Historical Coverage أو Forecast.

## Output Rank

كل مرشح يحمل `score_kind = SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY`، و`probability = null`، و`recommendation = null`، وحالة `RESEARCH_CANDIDATE` أو `WATCH` أو `ABSTAIN` مع Reason Codes.

يحمل التقرير `evidence_packet_hash` مطابقًا للHash الذي حسبه المدقق على ملفات العقد وArtifacts المشار إليها في Manifest. يرفض المسار أي تغير في الحزمة بين التحقق وإصدار الخطة، ويربط Research Ledger الـHash نفسه بالقرار.
