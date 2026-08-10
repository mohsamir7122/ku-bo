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

وجود Schema لا يثبت صحة المحتوى المالي أو اكتمال المصادر. مدققات `kubo.source_network` تفحص حزم البحث، بينما `kubo.research_price_history` يفحص Price History البحثية ويحجب أي ادعاء بأنها Official Complete EOD أوBacktest-ready.
