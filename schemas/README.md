# KU-BO machine-readable contracts

هذه الملفات توثّق حدود المدخلات بصيغة JSON Schema 2020-12. التحقق الصارم في وقت التشغيل موجود أيضًا داخل كود Python ولا يعتمد على تثبيت `jsonschema`، حتى يبقى Core بلا تبعيات خارجية.

- `analysis-request.schema.json`: عقد الطلب المرن.
- `research-run.schema.json`: عقد رأس حزمة الأدلة Point-in-Time.
- `capture-plan.schema.json`: عقد مهام الجمع العامة أو الاصطناعية.
- `parser-plan.schema.json`: عقد مصالحة الهوية ومهام Parser المربوطة ببصمات Raw Artifacts.
- `source-capabilities.schema.json`: مصفوفة فصل تعريف المصدر وCapture وParser واختبار Fixture والتشغيل الحي.
- `live-source-probe.schema.json`: إيصال وصول حديث محدود الصلاحية ومربوط بملفات Raw وبصماتها.
- `network-manifest.schema.json`: فهرس البايتات الخام وHash ومصدرها وتوقيت جمعها.
- `source-observations.schema.json`: حالة كل مصدر ونتيجة الاستعلام والأدوار المتاحة.
- `universe.schema.json`: هوية الأسهم وعضوية النطاق بصورة Effective-dated ومربوطة بدليل رسمي.
- `finding.schema.json`: عقد السطر الواحد داخل `findings.jsonl`.
- `runtime-trust-registry.schema.json`: سجل التفويض الخارجي المصادق عليه للمصادر الحساسة.
- `outcome-evidence-manifest.schema.json`: Manifest لأدلة النتيجة المحققة، مربوط بالقرار والسهم والتوقيت والبايتات الخام.
- `vendor-symbol-mapping.schema.json`: عقد Vendor Mapping المنفصل صراحةً عن Official Security Identity.
- `research-price-history.schema.json`: عقد صفوف OHLCV البحثية الثانوية التي لا تدّعي اكتمال `daily_eod`.
- `data-quality-report.schema.json`: عقد تقرير جودة وتغطية Price History وحدود الادعاء المتبقية.
- `official-foundation-manifest.schema.json`: عقد الخمسة Official Artifacts المطلوبة لبناء Current Identity وTrading Calendar، مع SHA-256 ووقت الجمع والمراجعة.
- `official-identity-report.schema.json`: تقرير مصالحة Security Code وISIN وTicker عبر مصدرين رسميين مع إبقاء النطاق `CURRENT_SNAPSHOT_ONLY`.
- `trading-calendar-report.schema.json`: تقرير تقويم سنة واحدة مبني على Official Holidays وTrading Weekdays وSession Regime.
- `official-foundation-import-report.schema.json`: تقرير الحالة النهائية لمرحلة Current Identity and Calendar، مع منع مساواة Current Snapshot بالتاريخ الكامل أوالسماح بـBacktest.
- `status-corporate-manifest.schema.json`: عقد Suspended وDelisted وCorporate Actions rendered captures، مع Snapshot date وFilter/Pagination receipt.
- `security-status-evidence.schema.json`: عقد Current Status Snapshot؛ غياب السهم عن Suspended page لا يثبت أنه كان متداولًا تاريخيًا.
- `corporate-action-schedule.schema.json`: عقد Official entitlement dates مع إبقاء Action Type وAmount وAdjustment Factor في حالة Pending.
- `status-corporate-import-report.schema.json`: تقرير الحالة النهائية لمرحلة Current Status and Corporate Action Schedule مع بوابات التاريخ والعوامل والـBacktest.
- `ca-enrichment-manifest.schema.json`: عقد ربط كل Schedule Row بإفصاح رسمي وReviewed Text Export وOfficial Price Evidence وشروط الحساب.
- `corporate-action-factor-ledger.schema.json`: عقد يفصل Reference-price factor وHistorical-continuity factor وPosition multiplier وReturn-engine multiplier بدل وضع رقم Adjustment واحد غامض.
- `ca-enrichment-import-report.schema.json`: تقرير جاهزية Corporate Action enrichment، مع Queue مستقلة لأي Rights أوComplex Action ما زالت Return-policy blocked.
- `status-history-manifest.schema.json`: عقد البحث التاريخي لكل سهم، وOpening State Evidence، وSuspension/Resumption/Delisting/Relisting notices.
- `status-intervals.schema.json`: عقد الفترات اليومية المتصلة داخل Window معلنة، مع Hashes افتتاحية وNotice boundaries.
- `status-history-import-report.schema.json`: تقرير مصالحة التاريخ المعاد بناؤه مع Current Snapshot، مع منع تعميم النتيجة خارج النافذة.

وجود Schema لا يثبت صحة المحتوى المالي أو اكتمال المصادر. مدققات `kubo.source_network` تفحص حزم البحث، و`kubo.research_price_history` يفحص Price History، و`kubo.official_foundation_import` يفرض Current Identity وتقويم السنة، و`kubo.status_corporate_import` يفصل Current Status عن التاريخ. أما `kubo.ca_enrichment_import` فيربط Terms بالإفصاح والسعر الرسميين ويمنع مساواة Reference Adjustment بعائد المستثمر، بينما `kubo.status_history_import` يطلب Opening State وQuery Receipts وNotices كاملة قبل إنشاء Status Intervals قابلة للتدقيق.
