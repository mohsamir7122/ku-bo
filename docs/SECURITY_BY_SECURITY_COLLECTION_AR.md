# جمع بيانات الكويت سهمًا بسهم

تاريخ العقد: 2026-08-27

## النتيجة الهندسية

المسار الجديد يثبت وحدة العمل عند مستوى `security_code` الرسمي، وليس مجموعة
أسهم أو Ticker واحد للسوق كله. يُبنى Queue حتمي من الـIssuer Universe المعتمد،
ثم يعمل المنسق بهذا الترتيب:

```text
سهم واحد نشط
→ كل المصادر المخططة لهذا السهم
→ إيصال نهائي لكل مصدر
→ مصالحة وتحقق
→ Seal نهائي للسهم
→ السهم التالي
```

`max_active_securities` يساوي 1. فشل مصدر يخص ذلك المصدر فقط، ولا يلغي محاولة
بقية المصادر. لكن الانتقال إلى السهم التالي ممنوع قبل أن يحصل السهم الحالي على
إحدى الحالات النهائية:

- `SEALED_ALL_SOURCE_ATTEMPTS_TERMINAL`، أي إن محاولات المصادر انتهت من دون
  فجوة وصول، وليس أن ملف الشركة اكتمل؛
- `SEALED_WITH_EXPLICIT_GAPS`؛
- `SEALED_BLOCKED`.

المنسق البرمجي في `kubo.issuer_sequential_collection` ينفذ الحلقة الخارجية
سهمًا بسهم من خلال Adapter محقون. الـAdapter وحده مسؤول عن Network access،
الحقوق، Retries، حفظ Raw bytes، والـParsing. يجب أن يحول كل عطل متوقع إلى
إيصال نهائي؛ Exception أوإيصال مشوه هو خرق قاتل لعقد الـAdapter وليس فشل مصدر
عاديًا. لا يحول العقد وجود مصدر في الكتالوج إلى Connector حي.

## ترتيب المصادر لكل سهم

كل سهم يحصل على الخطة نفسها: 29 مصدرًا موزعة على سبع موجات. لا توجد قاعدة
`first-success`; كل مصدر مخطط يجب أن ينتهي بإيصال صريح.

1. الهوية الرسمية: `boursa_current` و`cma_ifsah`.
2. موقع الشركة الرسمي: `issuer_ir_verified`.
3. الإفصاحات والإجراءات الرسمية: `boursa_disclosure_archive`،
   `boursa_reports_archive`، و`kcc_maqasa_official`.
4. البيانات المرخصة أو المصدرة بإذن: `authorized_broker_feed`،
   `lseg_workspace_authorized`، و`ice_kuwait_archive`.
5. المصادر المنظمة المساندة: `investing_history`، `yahoo_finance_kw`،
   `mubasher_kuwait`، `argaam_kuwait`، `tradingview_screeners`،
   `marketscreener_kuwait`، و`alphastocks_authorized_connector`.
6. السياق الصحفي: `reuters_middle_east`، `kuna`، `alqabas_economy`،
   `alanba_economy`، `alrai_economy`، `aljarida_economy`، `zawya`،
   و`asharq_business`.
7. الاكتشاف والسنتمنت فقط: `indexsignal_forum`، قنوات Telegram الثلاث،
   و`web_search_router`.

Reuters المنقول من خلال LSEG يحتفظ بـReuters كأصل للمعلومة ولا يُحسب مصدرًا
مستقلًا ثانيًا. IndexSignal وTelegram لا يثبتان هوية أو سعرًا أو إفصاحًا رسميًا،
وGoogle/Web Search يوجّه فقط إلى المصدر الأصلي.

## موقع الشركة الرسمي إلزامي

لكل `security_code` عنصر مستقل باسم `issuer_ir_verified`. لا يُخمن النظام اسم
النطاق من اسم الشركة. الربط الصحيح يمر عبر `SIGNED_RUNTIME_TRUST_REGISTRY`
خارجي ومصدق، ويثبت:

- `issuer_id`؛
- `security_code`؛
- النطاق أو النطاقات الرسمية؛
- مدة الصلاحية؛
- بصمة سجل الثقة؛
- Activation عند الحاجة.

إذا لم يوجد الربط، لا يقبل المنسق `COLLECTED` أو`VERIFIED_ZERO` ولو ادعى
الـAdapter وجود صلاحية؛ تسجل المحاولة
`ISSUER_OFFICIAL_SITE_UNRESOLVED` وتظل الفجوة ظاهرة. عند وجود الربط يعيد
التنفيذ فتح السجل عند توقيت المحاولة ويطابق Key ID وبصمة السجل والنطاق ورمز
الورقة وفترة الصلاحية. ويبحث الموقع الرسمي في
التقارير المالية، عروض المستثمرين، الأخبار الرسمية، الحوكمة والملكية، الجمعيات
العمومية، والاستراتيجية والمشروعات والشركات التابعة.

أي نتيجة `COLLECTED` أو`VERIFIED_ZERO` ذات Artifact تحتاج
`artifact_manifest_sha256`. والمصادر ذات Runtime domain أوEntitlement تحتاج
Activation/Entitlement قابلًا للتحقق من سجل الثقة نفسه. يعيد مدقق الـRun حساب
بصمات إيصالات المصادر، وسلسلة بصمات الأسهم، والعدادات، والحدود الزمنية. تقريره
`PASS_RUN_RECEIPT_INTERNAL_CONSISTENCY_ONLY`: هذه Content hashes وليست HMAC أو
دليلًا مصادقًا، وبصمة الـManifest لا تعوض إعادة فتح ملفات الـRaw بواسطة طبقة
الـIngestion المختصة.

## الأوامر

التحقق من سياسة الجمع:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  validate-issuer-sequential-collection-policy
```

بناء خطة من Universe معتمد:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  plan-issuer-sequential-collection \
  --universe /private/runtime/issuer-universe.json \
  --run-id kuwait-security-collection-001 \
  --generated-at 2026-08-27T15:07:00+03:00 \
  --runtime-trust-registry /private/runtime/runtime-trust-registry.json \
  --output /private/runtime/security-collection-plan.json
```

متغيرا HMAC المطلوبان عند ربط سجل الثقة هما
`KUBO_RUNTIME_TRUST_HMAC_KEY` و`KUBO_RUNTIME_TRUST_HMAC_KEY_ID`. لا يدخلا Git.

إعادة فتح الخطة والتحقق منها دلاليًا:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  validate-issuer-sequential-collection-plan \
  --plan /private/runtime/security-collection-plan.json \
  --universe /private/runtime/issuer-universe.json \
  --runtime-trust-registry /private/runtime/runtime-trust-registry.json
```

إعادة فتح إيصال التشغيل وسلسلة الأختام:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . \
  validate-issuer-sequential-collection-run \
  --plan /private/runtime/security-collection-plan.json \
  --run /private/runtime/security-collection-run.json \
  --universe /private/runtime/issuer-universe.json \
  --runtime-trust-registry /private/runtime/runtime-trust-registry.json
```

خيار سجل الثقة مطلوب عند وجود نتيجة موجبة أو`VERIFIED_ZERO` لمصدر حساس،
ولا يلزم لإعادة فتح تشغيل كل مصادره الحساسة محجوبة بإيصالات صريحة.

## حدود الإثبات الحالية

يعيد المدقق فتح Universe خارجيًا ويطابق بصمته وهويات Queue كاملة؛ لذلك لا تكفي
إعادة حساب بصمة Plan مزورة لتغيير سهم أوTicker. الخطة تغطي كل Security موجود في
الـUniverse المدخل، وتفصل حتى ورقتين ماليتين
للشركة نفسها إلى عنصرين مستقلين. لكنها لا تثبت وحدها أن الـUniverse يمثل كل
بورصة الكويت. وصف «كل أسهم السوق» يحتاج Universe حقيقيًا من مصدر رسمي، حالة
`PROVEN_REAL_EVIDENCE`، ومصالحة العدد والهوية Point-in-Time.

التنفيذ الحالي يثبت العقد، الترتيب، العزل، واتساق سلسلة الـContent hashes على
Fixtures، ولا يثبت سلامة البايتات أوDossier مكتملًا. كما يعيد فتح
`source_network.json` و`source_capabilities.json`
وقت التحقق كي لا يستطيع Plan ذاتي الـhash إزالة حق LSEG أوتبديل مقام المصادر.
ولا يزال الآتي خارجيًا أو غير منفذ:

- Universe كويتي حقيقي كامل؛ الموجود للاختبار Synthetic فقط؛
- Adapters حية لكل المصادر الـ29؛
- وصفات وصول لأربعة مصادر ديناميكية أو خارجية؛
- Checkpoint v2 دائم يضيف `security_code` إلى Shards؛
- تشغيل Workflow حي ونشر Drive؛
- أي Training أو Backtest أو Forecast.

لذلك تظل الـWorkflow الحالية fail-closed عند
`COLLECTION_ADAPTER_NOT_ADMITTED`/`BLOCKED_CHECKPOINT_STORE`. هذا العقد لا يدعي
جمع بيانات حقيقية أو `LIVE_OPERATIONAL`.
