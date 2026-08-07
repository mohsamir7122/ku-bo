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
- إذا كان المصدر ديناميكي النطاق، يحمل كائن `runtime_authority` منظمًا يتضمن `registry_id` و`verified_domain` و`subject_id` و`security_codes` و`evidence_sha256` و`verified_at`، ويربط الدليل الخام بالهوية الرسمية المطلوبة.

حقول `runtime_authority` داخل Manifest تثبت اتساق Packet فقط ولا تصبح تفويضًا من تلقاء نفسها. عند استخدام مصدر حساس، يتحقق `0.1.0` منها كذلك مقابل سجل ثقة خارجي مصادق عليه بمفتاح Runtime؛ غياب السجل أوفشل المطابقة يحجب التشغيل.

## `universe.json`

هذا الملف مطلوب لكل Scope لإثبات الهوية الفعالة زمنيًا؛ والأعداد داخل `research_run.json` لا تكفي. يتطلب:

- `reconciliation_status = EXACT` و`membership_basis = POINT_IN_TIME_OFFICIAL`.
- قائمتي Security Codes رقمية وفريدة للمتوقع والمغطى، تطابقان الأعداد المعلنة، وتكونان متساويتين عند ادعاء التغطية الكاملة.
- مصدر عضوية من فئة Official أو Licensed وله دور `IDENTITY_REFERENCE`.
- `membership_raw_sha256` محلولًا إلى Artifact من المصدر نفسه ومحاولة مصدر مساهمة.
- صف `securities` لكل ورقة مغطاة، يربط `security_code` بالTicker خلال `valid_from`/`valid_to` الفعالين وقت القرار.
- وقوع `membership_as_of` في تاريخ `decision_at` نفسه بتوقيت `Asia/Kuwait` وألا يكون لاحقًا له، وأن يكون Artifact قد جُمع عنده أوبعده وقبل القرار.

غياب الملف أو فشل ربط الهوية يجعل التشغيل `SOURCE_NETWORK_BLOCKED`. أما نقص تغطية السوق مع سلامة هويات العناصر المغطاة فيسمح ببحث Candidate-set فقط ويمنع `FULL_MARKET_RESEARCH_RANK`.

## `source_observations.json`

كل محاولة مصدر تسجل:

- الحالة: `AVAILABLE`، `PARTIAL`، `BLOCKED`، `ERROR`، `AUTH_REQUIRED`، أو `UNTESTED`.
- طريقة الوصول المسموح بها وتوقيت المحاولة.
- نتيجة الاستعلام: `QUALIFIED`، `ZERO_RESULT`، `BLOCKED`، `ERROR`، `AUTH_REQUIRED`، `PARSER_DRIFT`، أو `DATA_QUALITY_REJECTED`.
- الأدوار التي شوهدت، عدد العناصر المؤهلة، Zero-result الصريح، Hashes الخام، Quality Flags، والقيود.

المصدر لا يساهم لمجرد أن الصفحة فتحت. يحتاج احتساب المصدر في نصاب الأدلة إلى Evidence خام محلول، وArtifact تابع للمصدر نفسه، ونتيجة `QUALIFIED` من دون Data-quality flags، وعنصر مؤهل واحد على الأقل. تُسجل `ZERO_RESULT` فقط لإثبات أن الاستعلام نُفذ وأعاد صفرًا صريحًا؛ لا تملأ Quorum ولا ترفع Coverage. ولا يستطيع `ACCESS_RECEIPT` وحده إنشاء مساهمة.

عند مساهمة مصدر `enabled_by_default = false`، يتطلب Packet الحقول `enabled_for_run = true` و`activation_id` و`activation_evidence_sha256` محلولًا إلى Evidence من المصدر نفسه. وعند مساهمة مصدر `requires_entitlement = true`، يتطلب `entitlement_id` و`entitlement_evidence_sha256` محلولًا إلى `ACCESS_RECEIPT` من المصدر نفسه. هذه الحقول شروط اتساق حالية وليست تفويضًا خارجيًا كافيًا للإنتاج.

## `findings.jsonl`

كل سطر JSON مستقل ويتطلب:

- `finding_id` فريدًا.
- `security_code` رقميًا رسميًا؛ Ticker Alias للعرض فقط.
- مصدرًا تمت ملاحظته ويساهم فعلًا، و`source_url` ضمن النطاق **ومطابقًا حرفيًا لعنوان الـArtifact المشار إليه**.
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

## `capture-plan.json`

تطبق خطة الجمع حدودًا ثابتة لا يمكن رفعها من داخل الخطة:

- 32 Task كحد أقصى.
- 128 MiB كحد أقصى لمجموع `max_bytes` المعلن.
- 300 ثانية كحد أقصى لمجموع `timeout_seconds` المعلن.

يتم جمع هذه القيم والتحقق منها قبل إنشاء Connector أوبدء أي Capture أوكتابة Output. تجاوز أي حد يرفض الخطة كاملة بلا I/O للناتج.

## سجل الثقة الخارجي

لا يجوز للحزمة أن تثبت صلاحيتها بنفسها. يطبق `0.1.0` عقد `runtime-trust-registry` ذي `schema_version = 1.0` و`audience = kubo-source-network`. يحتوي السجل `registry_id` وغلاف صلاحية، وقيودًا تربط `source_id` بالـSubject/Account والنطاقات وSecurity codes وActivation/Entitlement وصلاحية القيد، وكائن `authentication` بخوارزمية `HMAC-SHA256` و`key_id` وTag. يصادق النظام المحتوى القانوني Canonical بمفتاح Runtime لا يأتي من Packet، ويتطلب تطابق Key ID وصلاحية السجل والقيد عند وقت القرار.

المصادر Runtime-bound أوDisabled أوLicensed تفشل مغلقًا من دون سجل خارجي مصادق عليه وقيد واحد مطابق لكل استخدام حساس؛ تبقى إيصالات Packet مطلوبة لكنها لا تمنح التفويض ذاتيًا. يسجل ناتج التحقق `runtime_trust_required` و`sensitive_source_ids` و`runtime_trust_registry_id` و`runtime_trust_registry_hash` و`runtime_trust_key_id` كبيانات أصل، ولا ينسخ المفتاح أوTag المصادقة إلى التقرير.

## `live_source_probe`

الـProbe يختبر الوصول فقط. يسجل وقت التجربة، المصدر، الحالة، URL، الملاحظة، وأعلام الجودة. نجاحه لا يُحتسب ضمن Quorum بحث حقيقي، ولا يثبت Market Fact أو Historical Coverage أو Forecast.

## Output Rank

كل مرشح يحمل `score_kind = SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY`، و`probability = null`، و`recommendation = null`، وحالة `RESEARCH_CANDIDATE` أو `WATCH` أو `ABSTAIN` مع Reason Codes.

يحمل التقرير `evidence_packet_hash` مطابقًا للHash الذي حسبه المدقق على ملفات العقد وArtifacts المشار إليها في Manifest. يرفض المسار أي تغير في الحزمة بين التحقق وإصدار الخطة، ويربط Research Ledger الـHash نفسه بالقرار.

## Outcome Evidence Packet

النتيجة المحققة لا تقبل Hashes شكلية من المتصل. يحتاج `append-research-outcome` إلى حزمة داخل Ledger root تتكون من `manifest.json` ومجلد `raw/` مطابق له حرفيًا. يربط Manifest `outcome_id` و`decision_id` و`security_code`، ويسجل لكل Artifact مسارًا آمنًا تحت `raw/` وSHA-256 وحجمًا فعليًا و`source_id` وHTTPS URL وMedia type و`observed_at` داخل نافذة القرار والنتيجة.

المدقق يرفض Path traversal وSymlinks والملفات غير المذكورة والتكرار وHashes أوأحجامًا غير مطابقة، ويحد الحزمة عند 32 Artifact و128 MiB. يخزن Outcome المسار النسبي وPacket hash وArtifact hashes المشتقة، ويعيد `verify` و`seal` فتح الملفات وإعادة حسابها؛ حذف Packet أوتغييره يحجب السجل.

Payload القياس كائن صارم لا يقبل حقولًا إضافية، ويحتوي `schema_version`, `security_code`, `metric_id`, قيمة رقمية منتهية، `unit`, بداية ونهاية القياس، `method_id`, و`notes`. يجب أن يطابق السهم مرشحًا واحدًا في Decision report، وأن تقع أوقات القياس ضمن نافذة القرار والنتيجة. الوحدات المسموحة هي `DECIMAL_RETURN`, `PERCENTAGE_POINTS`, `BASIS_POINTS`, `FILS`, `KWD`, `RATIO`, `COUNT`, و`BOOLEAN_FLAG`.
