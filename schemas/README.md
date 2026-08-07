# KU-BO machine-readable contracts

هذه الملفات توثّق حدود المدخلات بصيغة JSON Schema 2020-12. التحقق الصارم في وقت التشغيل موجود أيضًا داخل كود Python ولا يعتمد على تثبيت `jsonschema`، حتى يبقى Core بلا تبعيات خارجية.

- `analysis-request.schema.json`: عقد الطلب المرن.
- `research-run.schema.json`: عقد رأس حزمة الأدلة Point-in-Time.
- `capture-plan.schema.json`: عقد مهام الجمع العامة أو الاصطناعية.
- `network-manifest.schema.json`: فهرس البايتات الخام وHash ومصدرها وتوقيت جمعها.
- `source-observations.schema.json`: حالة كل مصدر ونتيجة الاستعلام والأدوار المتاحة.
- `universe.schema.json`: هوية الأسهم وعضوية النطاق بصورة Effective-dated ومربوطة بدليل رسمي.
- `finding.schema.json`: عقد السطر الواحد داخل `findings.jsonl`.

وجود Schema لا يثبت صحة المحتوى المالي أو اكتمال المصادر؛ المدققات الدلالية داخل `kubo.source_network` هي التي تفحص التوقيت وHash وهوية المصدر والنصاب وحدود الادعاء.
