# مسار التأهيل التدريجي لثلاثة أسهم — KU-BO 0.3

هذه المرحلة تجهز الاختبار على دفعات ثابتة، كل دفعة تضم ثلاثة أسهم فقط. هي
طبقة تنظيم وتأهيل بيانات وليست Backtest أوForecast أوتوصية.

## النتيجة التي تنفذها المرحلة

يقرأ النظام سجلًا صارمًا للدفعات، ويتحقق من:

- وجود ثلاثة أسهم بالضبط في كل دفعة؛
- فرادة `security_code` و`ticker` و`ISIN` داخل جميع الدفعات؛
- صحة شكل `ISIN` ورقم التحقق؛
- ترتيب متصل يبدأ من الدفعة الأولى؛
- بقاء الهوية `UNVERIFIED_SEED` إلى أن تُستورد بايتات رسمية مؤرخة ومربوطة
  بـSHA-256؛
- ثبات بوابات Data Foundation الاثنتي عشرة لكل دفعة؛
- اقتصار المخرج على `DATA_QUALIFICATION_REPORT_ONLY`.

ثم ينشئ Workspace جديدة غير قابلة للكتابة فوق مجلد غير فارغ، تحتوي خطة
محمولة، وقائمة فحص عربية، ومجلدًا منفصلًا لكل ورقة مالية. لا تجمع هذه
العملية بيانات من الويب ولا تكتب بيانات سوقية في Git.

## ترتيب الدفعات

### الدفعة 1

```text
tri-001-kfh-ship-aznoula
108 / KFH / KW0EQ0100085
506 / SHIP / KW0EQ0500888
826 / AZNOULA / KW0EQ0504799
```

هذه هي نقطة البدء. القيم مرشحات هوية فقط وليست Official Identity Evidence.

### الدفعة 2

```text
tri-002-nbk-mabanee-zain
101 / NBK / KW0EQ0100010
413 / MABANEE / KW0EQ0400725
605 / ZAIN / KW0EQ0601058
```

### الدفعة 3

```text
tri-003-humansoft-aglty-boubyan
623 / HUMANSOFT / KW0EQ0601694
603 / AGLTY / KW0EQ0601041
109 / BOUBYAN / KW0EQ0102065
```

الدفعتان الثانية والثالثة موجودتان للتخطيط فقط. أمر التحضير يرفضهما قبل أي
كتابة إلى أن يُنفذ عقد Qualification Receipt مستقل للدفعة السابقة؛ فلا
يكفي Flag أوManifest ذاتي الادعاء للانتقال بين الدفعات.

## أوامر التشغيل

تحقق من السجل:

```bash
kubo-data-foundation --project-root /path/to/ku-bo \
  validate-tri-security-pilot
```

جهز الدفعة الأولى في مجلد فارغ جديد:

```bash
kubo-data-foundation --project-root /path/to/ku-bo \
  prepare-tri-security-batch \
  --batch-id tri-001-kfh-ship-aznoula \
  --run-id tri-001-qualification \
  --window-from 2026-01-01 \
  --window-to 2026-08-12 \
  --output-root /safe/runtime/tri-001
```

المخرجات الأساسية:

```text
plan/tri_security_batch_plan.json
scoped_config/pilot/security_master_seed.json
scoped_config/pilot/vendor_symbol_mappings.json
scoped_config/manifest.json
evidence/<security_code>-<ticker>/README.txt
reports/tri_security_batch_checklist_ar.md
reports/tri_security_workspace_report.json
```

المسار يرفض Symlink في مكونات `output-root` ويرفض الكتابة فوق مجلد غير فارغ.
كما يرفض نافذة معكوسة، أوعابرة لسنتين، أوتنتهي بعد `registry.as_of`.

استخدم إعداد الدفعة المقيد في أوامر Pilot القائمة كي لا يعود المقام إلى
الأسهم الخمسة الأصلية:

```bash
kubo-data-foundation --project-root /path/to/ku-bo \
  --pilot-config-dir /safe/runtime/tri-001/scoped_config \
  --expected-pilot-config-manifest-sha256 <SHA256_FROM_WORKSPACE_REPORT> \
  validate-pilot-config

kubo-data-foundation --project-root /path/to/ku-bo \
  --pilot-config-dir /safe/runtime/tri-001/scoped_config \
  --expected-pilot-config-manifest-sha256 <SHA256_FROM_WORKSPACE_REPORT> \
  prepare-price-collection \
  --output-root /safe/runtime/tri-001-prices
```

`scoped_config/manifest.json` يربط ملفات الإعداد الستة ببصماتها وببصمة
الدفعة، وتعيد CLI حساب هذه البصمات قبل أي أمر يستخدم `--pilot-config-dir`.
هذا الربط يثبت مقام الإعداد فقط، ولا يثبت صحة الهوية أوبيانات السوق.

الدفعتان الثانية والثالثة موجودتان في سجل التخطيط، لكن أمر التحضير يرفضهما
حاليًا لأن عقد Qualification Receipt مستقل للدفعة السابقة لم يُنفذ بعد.
هذا Fail-closed مقصود، وليس إذنًا يعتمد على Boolean أوملف ذاتي الادعاء.

هذه المرحلة لا تمرر بعد بصمة `tri_security_batch_plan.json` ونافذتها عبر كل
مخرجات الهوية والحالة وEOD والمصالحة. لذلك تبقى Workspace أداة Preparation
وتأهيل إعداد، ولا يجوز وصفها بأنها اجتازت Qualification end-to-end. أصغر
مرحلة تالية هي عقد Run Receipt يربط بصمة الخطة والنافذة والمقام بكل مكون
Downstream وبالتقرير النهائي المستقل.

## ما يلزم لنجاح التأهيل الحقيقي

كل سهم وكل جلسة داخل النافذة المعلنة تحتاج المرور عبر العقود القائمة، ومنها:

- Effective-dated Official Identity؛
- Official Trading Calendar؛
- Historical Security Status؛
- المقام الكامل لكل `security_code × session`؛
- Price Evidence وOfficial Complete EOD؛
- Corporate Actions ومعاملة Return مجمدة ومعتمدة؛
- Benchmark واضح الأساس وحقوق استخدامه؛
- Query/Pagination/Zero-result receipts؛
- Runtime Secret Guard وExternal Trust؛
- Final Independent Data-Foundation Gate Report.

لا تنشئ Workspace هذه الأدلة. هي تصف المطلوب وتبقى كل البوابات
`PENDING_EXTERNAL_EVIDENCE`.

## حدود الادعاء

لا يعني نجاح فحص السجل أوإنشاء Workspace أيًا مما يلي:

- إثبات الهوية الرسمية أوحالة الإدراج التاريخية؛
- اكتمال بيانات الأسعار أوCorporate Actions؛
- اجتياز الدفعة لتأهيل البيانات؛
- صلاحية Backtest؛
- تغطية السوق الكامل؛
- Forecast أوProbability أوAccuracy؛
- Buy/Sell/Entry/Exit Recommendation.

اختبار ثلاثة أسهم هو اختبار عقد ومسار بيانات. قياس جودة ترتيب سوقي يحتاج
كونًا تاريخيًا Point-in-time ومقامًا كاملًا عبر السوق، وليس الأسهم الثلاثة
الناجحة فقط.

## علاقة المرحلة بالسياسة المفتوحة

يبقى `KU-BO-008-D01` مفتوحًا. لا تحاول هذه المرحلة تثبيت Outcome Session
Policy أوتجاوزها، ولذلك تظل صلاحية Baseline Backtest والتقييم الحقيقي
محجوبة حتى يصدر قرار Product-specific صالح وتتوافر الأدلة الخارجية اللازمة.
