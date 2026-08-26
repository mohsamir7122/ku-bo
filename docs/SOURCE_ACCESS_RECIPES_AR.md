# وصفات الوصول وسجل فحص القدرة

## الفكرة

هذه الطبقة تحول خبرة فحص المواقع إلى عقد قابل للاختبار قبل بناء Collectors أو
Parsers إضافية. السؤال الذي تجيب عنه هو: هل توجد طريقة وصول معلنة ومحدودة يمكن
اختبارها وتسجيل نتيجتها؟ ولا تجيب عن: هل توجد بيانات سوق كاملة أو Feed حي أو ميزة
تنبؤية؟

المسار هو:

```text
Source Network definition
  -> DEFINED_ONLY access recipe
  -> PLANNED_NOT_EXECUTED capability-probe plan
  -> operator-performed hash-bound access receipt
  -> PASS_ACCESS_ONLY or BLOCKED
```

لا تنفذ الخطة اتصالًا بالإنترنت، ولا تنشئ Market Finding، ولا تغيّر
`config/source_capabilities.json`.

## الحالة الحالية

- 14 وصفة تغطي 30 مصدرًا ذا أولوية من كتالوج يحوي 68 مصدرًا.
- التغطية تشمل بورصة الكويت الحالية والتقارير والإفصاحات، CMA/iFSAH، Investing،
  TradingView، Yahoo، Mubasher، Argaam، MarketScreener، Trading Economics، مجموعة
  أخبار محلية وإقليمية، IndexSignal، سبع قنوات Telegram، Wayback، Common Crawl،
  وICE المرخص.
- 38 مصدرًا لا يملك وصفة في هذه المرحلة ويظل غير قابل للتخطيط بهذا العقد.
- `authorized_broker_feed` غير مغطى لأن الكتالوج لا يملك Start URL أو مزودًا
  مصرحًا به؛ لا يجوز اختراع عنوان تشغيل له.
- كل الوصفات `DEFINED_ONLY` و0 منها `LIVE_OPERATIONAL`.

## قواعد المواقع المترجمة إلى وصفات

بورصة الكويت تستخدم Public page أو Public download بصورة `ONE_OFF` فقط. الصفحات
الديناميكية تحتاج Rendered identity sentinels؛ HTTP 200 أو SPA shell أو Fragment
وحده لا يكفي. صفحات التداول العامة تبقى Delayed ولا تثبت Entry أو Fill.

Investing وTradingView وYahoo في هذا المسار تعتمد `USER_EXPORT` مصرحًا به، لا
Public API مفترضًا ولا Scraping. تحفظ Symbol mapping والوحدة و Raw/Adjusted والوقت
والبصمة. Investing يملك Importer مراجعًا لكن سقف ترقيته
`PRICE_IMPORT_READY_ONLY`، وليس Official EOD أو Execution tape.

Mubasher و Argaam و MarketScreener و Trading Economics مصادر ثانوية. Template أو Test
Data أو Ticker suffix غير محلول أو Timestamp قديم أو وحدة متضاربة ينتج
`DATA_QUALITY_REJECTED` أو`PARTIAL`، ولا يُنتقى منه حقل مناسب وحده.

Reuters والصحف ومصادر الأخبار تقدم Context أو Routing. لا يُستنتج محتوى Paywall
من Headline أو Snippet، وتُجمع النسخ المعاد نشرها تحت Origin واحد. حقيقة الشركة
المادية تحتاج تأكيدًا رسميًا أو Issuer-primary مناسبًا.

IndexSignal و Telegram يظلان Community sentiment أو Routing فقط. تحفظ هوية الرسالة
والقناة والوقت والتعديل والتحويل، ولا يثبتان Price أو Disclosure أو Corporate
Action أو Execution.

Wayback و Common Crawl يثبتان وجود Archive capture في سياقه فقط، لا اكتمال الأرشيف
ولا First-public time. المصدر المرخص يحتاج Entitlement خارجيًا ونطاقًا مصرحًا به؛
وجوده في الكتالوج ليس Root of Trust.

## التشغيل

تحقق من سجل الوصفات:

```bash
PYTHONPATH=src python3 -m kubo.cli_v3 --project-root . \
  validate-source-access-recipes
```

أنشئ خطة لا تُستبدل إذا كان الملف موجودًا:

```bash
PYTHONPATH=src python3 -m kubo.cli_v3 --project-root . \
  plan-source-access-probe \
  --planned-at 2026-08-24T09:00:00+03:00 \
  --source boursa_current \
  --source investing_history \
  --output /absolute/path/to/source-probe-plan.json
```

بعد إجراء الفحص المصرح به خارج مولد الخطة وحفظ Raw bytes تحت `raw/`، تحقق من
الإيصال الحالي ذي Schema `3.1-access-probe` وربطه بالخطة:

```bash
PYTHONPATH=src python3 -m kubo.cli_v3 --project-root . \
  validate-source-access-probe \
  --plan /absolute/path/to/source-probe-plan.json \
  --probe /absolute/path/to/access-probe.json
```

المطابقة تتطلب Source set مطابقًا، URL مخططًا، وقت محاولة داخل نافذة 24 ساعة،
Raw artifact و SHA-256 للحالات المقروءة، و Reason code مضبوطًا للحالات الطرفية.
إيصال `BLOCKED` يمكن أن يجتاز العقد كـ`PASS_ACCESS_ONLY` إذا وصف المنع بأمان؛ هذا
نجاح للتدقيق لا نجاح للوصول.

الخطة الشاملة الحالية تحتوي 30 مهمة، وتُرفض قبل الكتابة إذا تجاوزت 32 مهمة أو
128 MiB إجمالية أو 300 ثانية إجمالية. المهلة الحالية 10 ثوانٍ لكل مهمة، أي 300
ثانية بالضبط عند تخطيط المصادر المغطاة كلها.

## ما يبقى ممنوعًا

- لا تجاوز Login أو CAPTCHA أو Paywall أو Robots أو Rate limit.
- لا جمع Systematic من Public pages من دون Rights evidence مناسب.
- لا ترقية Recipe أو Probe أو Fixture إلى Connector أو Parser أو `LIVE_OPERATIONAL`.
- لا استخدام Access receipt كدليل سعر أو حدث أو تغطية تاريخية.
- لا Forecast أو Probability أو Recommendation أو Backtest من هذه الطبقة.
- لا Credentials أو Cookies أو Sessions أو بيانات سوق حقيقية داخل Git.
