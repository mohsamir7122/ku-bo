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
- تحقق Packet-level من بنية Runtime authority لمواقع الشركات والحسابات الديناميكية، ومن Activation للمصادر المعطلة، ومن Entitlement للمصادر المرخصة؛ هذه الحقول شروط اتساق وليست Root of Trust ذاتية.
- سجل ثقة خارجي `1.0` يفشل مغلقًا للمصادر الحساسة، مع مصادقة `HMAC-SHA256` بمفتاح وKey ID من Runtime وربط فريد للمصدر والحساب/Subject والنطاق وSecurity codes وActivation/Entitlement وفترة الصلاحية. يسجل ناتج التحقق Registry ID وبصمة المحتوى وKey ID ولا يسجل المفتاح.
- Dedup لإعادة النشر وNear-duplicate النصي المحافظ، ورصد تضارب المصادر المستقلة.
- Research Rank بلا Probability أوRecommendation، ورفض طلب Entry/Exit في `research_network`.
- Output Contracts بصيغتي JSON وMarkdown، بالعربية والإنجليزية، وبمستويات Brief وStandard وDeep.
- تحليل وصفي شفاف للسعر والنشاط والسيولة والأساسيات وSentiment، مع فصل Tone عنTruth.
- قياس Illiquidity ومحاكاة `NO_FILL` و`PARTIAL_FILL` وLimit Queue وSuspension.
- Purge/Embargo primitives للتحقق الزمني.
- Research Decision Ledger وOutcome stream منفصلان، Hash chain، File locking، وHMAC seal اختياري يرفض Downgrade. Outcome يتطلب Evidence packet فعليًا داخل Ledger ويعيد التحقق من Manifest والبايتات عند الإضافة والتحقق والختم، ولا يقبل Hash من المتصل.
- CLI للجمع، التحقق، التخطيط، التقارير، Ledger verification/sealing، وإضافة Outcome.
- محلل هوية خاص ببورصة الكويت ومحلل جدول تاريخ سعر خاص بـInvesting، مع مصالحة Security Code/Ticker/ISIN وفشل مغلق عند Parser Drift. اجتاز المسار اختبارًا من البايتات إلى Finding ثم Network Validation على Fixtures مولدة غير سوقية.
- مصفوفة قدرات آلية تفصل تعريف المصدر وCapture وParser وFixture evidence عن `LIVE_OPERATIONAL`؛ لا تسجل أي مصدر حيًا تشغيليًا في هذه النسخة.
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
- Entitlement receipt وسجل الثقة يتحققان محليًا ولا يستعلمان حيًا من Vendor licensing service؛ لا يوجد Entitlement تشغيلي أوFeed مرخص مهيأ داخل المستودع.
- لا يحتوي المستودع على سجل ثقة تشغيلي أومفتاح Runtime. الآلية منفذة، لكن تشغيل مصدر محمي يبقى محجوبًا حتى يقدمهما المشغل خارج Packet مع التفويض القانوني اللازم.
- Full historical backtest يظل محجوبًا حتى Point-in-Time Universe وCorporate Actions وExecution data وSealed prospective denominator.
- لا توجد خدمة Production منشورة، أوScheduler تشغيلي، أومراقبة توافر مستمرة، أوضمان لاستقرار أي مصدر خارجي.
- لا توجد Captures حية مسجلة ومصرح بها تثبت قبول المحللين على الصفحات الخارجية الحالية. المحللان المنفذان مختبران على Fixtures تعاقدية مولدة فقط، وبقية المصادر بلا Parsers عاملة. التشغيل الحقيقي يحتاج تفويض الوصول وFixtures مصرح بها وQA ومراقبة Drift.
- CI الحالي Linux فقط. حزمة `tzdata` أصبحت Runtime dependency مثبتة تلقائيًا كي يعمل `Asia/Kuwait` على Windows أوContainer مصغر بلا System IANA tzdb؛ ولا يزال دعم منصة إضافية خارج اختبارات الـwheel المعزولة غير مُدّعى بلا CI خاص بها.

## معيار التسليم

النسخة `0.1.0` أساس هندسي قابل للتدقيق للعقود والجمع العام المحدود والتحليل البحثي المحافظ. ليست Production-complete وليست منصة توصيات حية. الانتقال إلى Forecast أوExecution أوتشغيل Production يتطلب Capabilities خارجية موثقة، وعمليات نشر ومراقبة، ثم Prospective Validation جديدة؛ ولا يجيزه مجرد نجاح الاختبارات الاصطناعية.
