# قاعدة معرفة مشروع KU-BO

هذا الملف يثبت القرارات المعمارية التي نتجت من التجارب السابقة، حتى لا يعيد المشروع الأخطاء نفسها عند إضافة Source أوModel أوOutput جديد.

## حقيقة المصدر ليست شهرة المصدر

- Boursa Kuwait مصدر رسمي، لكنه قد يعيد `403` أو`Access Denied` أوصفحة ديناميكية ناقصة. فشله يسجل `OFFICIAL_SOURCE_UNAVAILABLE` ولا يوقف السوق كله فقط إذا بقي إيصال هوية رسمي بديل وحديث؛ غياب البديل فشل Structural.
- Investing.com وTradingView وArgaam مفيدة للاكتشاف والسياق والسعر المؤخر، لكنها لا تصبح Official Disclosure ولاExecution Tape.
- Telegram وIndexSignal وFacebook وInstagram وTikTok وX مصادر Attention وSentiment وRumor Leads. لا تثبت عقدًا أوتوزيعًا أوحكمًا قضائيًا أوPrice fact وحدها.
- موقع الشركة وInvestor Relations مصدر Primary Issuer فقط بعد ربط Domain بالشركة و`security_code` في Registry مؤرخ. وللاستخدام التشغيلي يجب أن يكون Registry خارجيًا عن Packet ومصادقًا بـHMAC ومفتاح Runtime؛ إيصال الحزمة الذاتي لا يكفي.
- Google Drive أوأي Storage يحفظ الأدلة ولا ينشئ Market Fact.

## قواعد لا يجوز الرجوع عنها

1. `security_code` أوISIN المؤرخ مطلوب؛ Ticker وحده لا يكفي.
2. كل Finding يرتبط ببايتات خام وSHA-256 وURL ووقت التقاط من المصدر نفسه، ويحمل `fact_type` مسموحًا ويطابق URL الـArtifact حرفيًا.
3. `decision_at` ثابت قبل التحليل، وأي معلومة أتت بعده لا تدخل القرار.
4. الناشر الأصلي أهم من عدد الروابط؛ إعادة نشر خبر واحد لا تزيد الاستقلال.
5. Source availability ليست Data capability، والصفحة المفتوحة بلا Finding ليست Confirmation.
6. Source Mosaic ينتج Research Score فقط، ولا Probability أوRecommendation.
7. Official outage يخفض Confirmation، ولا يساوي غياب الحدث ولا دليلًا سلبيًا.
8. Quorum يجب أن يخدم السهم نفسه، لا أن يكتمل من أخبار أسهم أخرى.
9. Missing ليس Zero، وZero Volume ليس Missing Volume.
10. Signal quality منفصلة عن Tradability. Limit Queue أوSuspension أوغياب Volume قد ينتج `NO_FILL`.
11. لا تُعاد كتابة Forecast أوDecision بعد النتيجة؛ يسجل Amendment لاحقًا في Ledger.
12. لا Backtest بلا Point-in-Time Universe وCorporate Actions وFull Denominator وتكاليف وNon-fill وTrial Registry.
13. Outcome hash يقدمه المتصل ليس Evidence. يجب أن تكون حزمة Manifest/Raw قابلة للحل داخل Ledger، وأن يعاد حساب بايتاتها عند الإضافة والتحقق والختم.

## ترتيب المصادر عند التعارض

لا توجد عملية تصويت بسيطة. يراجع النظام:

- هل المصدر Primary أمSecondary أمEditorial أمCommunity؟
- هل الناشر مستقل فعلًا أمينقل عن أصل واحد؟
- هل المعلومة في اختصاص المصدر المسموح؟
- هل التاريخ هو Publication time أمإعادة نشر؟
- هل يوجد Correction أوRevision أحدث كان متاحًا قبل القرار؟
- هل التعارض في الرقم أوالاتجاه أوهوية الشركة أوالتوقيت؟

إذا بقي تعارض مادي مستقل، تكون النتيجة `WATCH` أو`ABSTAIN` بدل اختيار الرواية الأكثر راحة.

## تحديث المنهج

أي منهج جديد يدخل أولًا إلى `research/methodology_registry.json` مع Reference أصلي وحالة إنتاج وقواعد واختبارات. لا تنتقل Method من `UNVALIDATED_RESEARCH` إلى Probability-bearing production إلا بعد:

- Dataset مؤرخ وقابل لإعادة البناء.
- Purged/Embargoed Walk-Forward.
- Baseline comparison.
- Costs/Spread/Slippage/Non-fill.
- Calibration عند إخراج Probability.
- Prospective ledger وعدد كافٍ من التواريخ المستقلة.
- Model Card وPolicy hash وCode hash.

## معنى كلمة «مكتمل»

اكتمال النواة يعني أن العقود والCLI والاختبارات والـSynthetic Smoke Check تعمل، وأن Source واحدًا يمكن أن يفشل من دون انهيار النظام عندما تبقى الهوية الرسمية الإلزامية متاحة من بديل صالح. لا يعني أن الحسابات الخارجية مفوضة، أوأن بيانات Live/Execution متاحة، أوأن Accuracy أوProbability ثبتت. آلية سجل الثقة الخارجي المصادق عليه منفذة في `0.1.0` وتفشل مغلقًا، لكن القدرة المحمية تظل محجوبة حتى يقدم المشغل خارج Packet سجلًا ومفتاح Runtime صالحين مع Entitlement قانوني ودليل حي مناسب.
