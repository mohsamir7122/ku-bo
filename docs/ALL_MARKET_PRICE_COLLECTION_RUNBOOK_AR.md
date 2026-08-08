# تشغيل Price Collection Pilot

هذه الوثيقة تخص الفرع:

`agent/final-price-collection-test`

الهدف هو اختبار إطار تجميع ملفات الأسعار، وليس الادعاء بأن كل أسهم Boursa Kuwait أصبحت مغطاة أو أن Backtest حقيقي أصبح جاهزًا.

## حدود المرحلة

- `config/symbol_mapping.json` يغطي حاليًا خمسة أسهم فقط: `KFH`, `NBK`, `ZAIN`, `HUMANSOFT`, و`MABANEE`.
- إنشاء Workspace لا يجمع أسعارًا من الإنترنت ولا يرفع ملفات إلى Google Drive.
- `USER_EXPORT` لا يقبل CSV بلا Collection Manifest مكتمل ومراجع.
- نجاح استيراد الأسعار يعطي `PRICE_IMPORT_READY_ONLY`؛ ولا يعطي `READY_TO_BACKTEST`.
- طلب `all_market` يبقى محجوبًا حتى توجد Point-in-Time Universe reconciliation من Artifact رسمي أو مرخص، لا من وصف ذاتي داخل Config.

## 1. البوابات قبل التشغيل

من جذر المستودع:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . validate-config
PYTHONPATH=src python -m compileall -q src tests scripts
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/smoke_check.py
PYTHONPATH=src python scripts/secret_guard.py
```

يجب أن يعرض `validate-config` قسمًا باسم `symbol_mapping`. فشل هذا القسم يمنع إنشاء Workspace أو Import.

## 2. إنشاء Workspace جديد

استخدم مسارًا جديدًا وفارغًا لكل تشغيل؛ الأمر يرفض Overwrite لمجلد غير فارغ لحماية Manifest سبق ملؤه.

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  prepare-price-collection-workspace \
  --output-root runtime/price_collection/seed_run_001 \
  --source-name investing \
  --downloaded-by "authorized operator" \
  --expected-scope mapped
```

المخرجات الأساسية:

```text
runtime/price_collection/seed_run_001/
  manifests/price_collection_manifest.csv
  raw_exports/investing/*.csv.placeholder
  normalized/
  quarantine/
  reports/price_collection_checklist.md
  reports/price_collection_workspace_report.json
```

إذا استُخدم `--expected-scope all_market` في هذه المرحلة، يجب أن تكون النتيجة Blocking؛ لأن Seed من خمسة أسهم لا يثبت Full Market.

## 3. وضع الملفات وملء Manifest

استبدل كل Placeholder بملف مصرح به يحمل الاسم الدقيق `{ticker}.csv`. لا تعدّل Provider bytes داخل الملف الخام.

املأ لكل سهم داخل `price_collection_manifest.csv` على الأقل:

- الهوية المطابقة لـ`security_code` و`ISIN`.
- رابط Investing المطابق للخريطة.
- `downloaded_at` بتوقيت واعٍ.
- `downloaded_by`.
- `file_sha256` المحسوب من CSV نفسه.
- أول وآخر تاريخ، وعدد الصفوف.
- `price_basis`: إما `RAW` أو`ADJUSTED`.
- `currency=KWD` و`unit` إما `fils` أو`KWD`.
- `allowed_use=USER_EXPORT`.
- `review_status=ACCEPTED` بعد المراجعة البشرية.

أي نقص أوHash مختلف أوملف Symlink يرفض السهم. الملف المشكوك فيه يذهب إلى `quarantine/` ولا يأخذ `ACCEPTED`.

## 4. استيراد ملفات الأسعار

استخدم Output جديدًا وفارغًا:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  import-investing-user-exports \
  --input-dir runtime/price_collection/seed_run_001/raw_exports/investing \
  --output-root runtime/user_exports/seed_run_001 \
  --observed-at 2026-08-08T15:00:00+03:00
```

يعثر الأمر على Manifest داخل Workspace، ويطابق Hash والهوية والفترة والوحدة قبل إنشاء `normalized/eod_ohlcv.csv`. ويحفظ نسخة byte-for-byte باسم `price_collection_manifest.csv` مع بصمتها داخل التقرير حتى تبقى المراجعة قابلة لإعادة الإنتاج.

المخرج `parser_plan_investing_user_export_draft.json` Draft محجوب عمدًا، وليس Parser Plan قابلًا للتمرير إلى `materialize-parser-run`. يلزمه أولًا Artifact هوية رسمي حديث وEffective-dated bindings موثقة. لا تُختلق `valid_from` من تاريخ افتراضي.

## 5. تفسير الحالات

- `PRICE_IMPORT_READY_ONLY`: اكتملت ملفات Seed ومراجعتها وتطبيعها، لكن Official identity artifact وCalendar وCorporate Actions وBenchmark ما زالت مطلوبة.
- `PARTIAL`: دخل بعض الملفات، وبقيت ملفات ناقصة أومرفوضة.
- `BLOCKED`: لم يدخل أي ملف صالح.
- `FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED`: طُلب Full Market بلا Universe reconciliation رسمية مؤرخة.
- `STOP_BACKTEST`: لا يجوز حساب Performance أوAccuracy.

أي حالة ناقصة أوDegraded يجب أن ترجع Exit code غير صفري في CLI.

## 6. Google Drive

انسخ `config/drive_price_collection_pilot.example.json` محليًا إلى:

`config/drive_price_collection_pilot.local.json`

املأ رابط المجلد واسم `rclone remote` محليًا. الملف المحلي Ignored من Git، ولا يجوز أن يحتوي Tokens أوCookies أوService-account keys.

بعد اكتمال المراجعة يمكن مزامنة Workspace بواسطة Connector مصرح أو`rclone` محلي. ارفع الخام إلى `raw_exports`، والـManifest إلى `manifests`، والمرفوض إلى `quarantine`. لا ترفع ملفًا مشكوكًا فيه إلى `normalized`.

Codex Web يصلح لتوليد Workspace وفحص Manifest وتشغيل الاختبارات إذا كانت الملفات متاحة له. Codex CLI على الكمبيوتر هو الأنسب لتنزيل User exports المصرح بها ومزامنة ملفات كبيرة بحساب Google Drive المحلي.

## 7. شرط Full Market الحقيقي

لا يكفي تغيير `coverage.scope` إلى `ALL_LISTED_SECURITIES`. يلزم Artifact رسمي أوLicensed يثبت عضوية السوق عند كل تاريخ قرار، مع Hash ومصالحة العدد والهوية لكل `security_code`. بعد ذلك تُضاف الأسعار وTrading Calendar وCorporate Actions وBenchmark وForecast/Outcome ledgers، ثم تُشغّل Stop Gates قبل أي Evaluation.
