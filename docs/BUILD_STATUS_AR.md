# حالة بناء الأساس البرمجي KU-BO 0.1.0

هذا الملف يصف ما نُفذ واختُبر داخل المستودع. لا يعلن اكتمال منصة Production، أوتوافر المصادر الخارجية، أوصلاحية النظام للتوصية أوالتنفيذ المالي.

## منفذ ومتحقق منه في الأساس البرمجي

- كتالوج يحوي 40 تعريف مصدر موزعة على 35 مجموعة استقلال، بما فيها Facebook وInstagram وTikTok وX كتعريفات سياسة معطلة افتراضيًا وليست موصلات API عاملة.
- أربع سياسات تغطي 13 منتجًا بحثيًا وزمنيًا.
- Capture layer آمنة للملفات وPublic HTTPS مع Domain Allowlist وRobots وTimeout وMax bytes ومنع Auth/CAPTCHA/Paywall bypass. ترفض Capture Plan قبل Connector أوI/O إذا تجاوزت 32 مهمة، أو128 MiB مجموع بايتات، أو300 ثانية مجموع مهلات.
- حزمة تشغيل Per-run مع Hash وتوقيت ونطاق وميزانية ومصالحة `raw_bytes`.
- Quorum لكل ورقة مالية، لا على مستوى السوق فقط.
- ربط Raw Hash بالمصدر نفسه، ورفض Late Capture وStale Finding وAccess Receipt وSearch Snippet كدليل.
- Effective-dated identity binding في جميع النطاقات ومنع Ticker mismatch.
- تحقق Packet-level من بنية Runtime authority لمواقع الشركات والحسابات الديناميكية ومن Activation للمصادر المعطلة. هذا تحقق اتساق داخلي، وليس Root of Trust إنتاجيًا.
- Entitlement gate داخل الحزمة للمصادر المرخصة، مع تعطيلها افتراضيًا. لا يثبت وحده ترخيص Vendor حيًا أوتفويضًا خارجيًا.
- Dedup لإعادة النشر وNear-duplicate النصي المحافظ، ورصد تضارب المصادر المستقلة.
- Research Rank بلا Probability أوRecommendation، ورفض طلب Entry/Exit في `research_network`.
- Output Contracts بصيغتي JSON وMarkdown، بالعربية والإنجليزية، وبمستويات Brief وStandard وDeep.
- تحليل وصفي شفاف للسعر والنشاط والسيولة والأساسيات وSentiment، مع فصل Tone عنTruth.
- قياس Illiquidity ومحاكاة `NO_FILL` و`PARTIAL_FILL` وLimit Queue وSuspension.
- Purge/Embargo primitives للتحقق الزمني.
- Research Decision Ledger وOutcome stream منفصلان، Hash chain، File locking، وHMAC seal اختياري.
- CLI للجمع، التحقق، التخطيط، التقارير، Ledger verification/sealing، وإضافة Outcome.
- JSON Schemas وMethodology Registry ووثائق تشغيل وSecurity policy.
- GitHub Actions على Python 3.11 و3.12 و3.13 و3.14 مع Compile وFull Suite وSmoke وSecret Guard وبناء Wheel واختباره بعقد `--project-root`.

## حالة التحقق

- Full Unit/Adversarial Suite: راجع نتيجة GitHub Actions الخاصة بالـCommit؛ لا يثبت هذا المستند عددًا محليًا قابلًا للتقادم.
- `scripts/smoke_check.py`: PASS.
- `scripts/secret_guard.py`: PASS.
- `compileall`: PASS.
- بناء Wheel `0.1.0`: PASS. تشغيله خارج Checkout يتطلب `--project-root` يشير إلى مستودع يحتوي `config/`؛ وهو ليس Wheel مستقل الإعدادات.
- JSON config/schemas: PASS.

## غير مكتمل عمدًا ولا يجوز الادعاء بعكسه

- لا توجد Credentials أوSessions لمنصات Investing.com أوTelegram أوMeta أوTikTok أوX.
- لا يوجد Licensed Broker/Market Feed مهيأ؛ Intraday/Opening/Execution-grade outputs محجوبة.
- Social policy definitions لا تعني أن API platform connector مفوض أوعامل.
- لا توجد Forecasts حية أوProbability معايرة أوAccuracy مثبتة.
- Near-duplicate detection محافظ قائم على النص، وليس Semantic embedding model معتمدًا.
- Entitlement receipt يتحقق داخل الحزمة ولا يستعلم حيًا من Vendor licensing service.
- لا يوجد بعد سجل ثقة خارجي موقّع ومستقل عن Packet يثبت Runtime authority أوActivation أوEntitlement ويربطها بالمصدر والحساب/Subject والنطاق وSecurity codes وفترة الصلاحية ومفتاح التوقيع. لذلك تبقى المصادر المحمية غير مخولة لتشغيل Production، حتى لو اجتاز إيصال داخل الحزمة فحص الاتساق الحالي.
- Full historical backtest يظل محجوبًا حتى Point-in-Time Universe وCorporate Actions وExecution data وSealed prospective denominator.
- لا توجد خدمة Production منشورة، أوScheduler تشغيلي، أومراقبة توافر مستمرة، أوضمان لاستقرار أي مصدر خارجي.
- لا توجد Parsers حية خاصة بالمصادر تحول Raw Capture تلقائيًا إلى Findings مؤهلة؛ التحويل الحقيقي يحتاج Parser وQA ومراقبة Drift لكل مصدر.

## معيار التسليم

النسخة `0.1.0` أساس هندسي قابل للتدقيق للعقود والجمع العام المحدود والتحليل البحثي المحافظ. ليست Production-complete وليست منصة توصيات حية. الانتقال إلى Forecast أوExecution أوتشغيل Production يتطلب Capabilities خارجية موثقة، وعمليات نشر ومراقبة، ثم Prospective Validation جديدة؛ ولا يجيزه مجرد نجاح الاختبارات الاصطناعية.
