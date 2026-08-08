# تدقيق وتقوية شبكة المصادر — V3.1

هذه وثيقة تدقيق هندسي تاريخية لمرحلة تقوية الشبكة داخل إصدار الأساس `0.1.0`. نجاح البنود أدناه لا يعني اكتمال منصة Production أوتوفر موصلات حية شاملة.

## الحكم

نجح استبدال شرط «Historical Archive كامل أو Model معتمد» في مسار البحث اليومي فقط. أصبح `research_network` قادرًا على البدء من Evidence Packet جديد في كل تشغيل وإصدار `Research Rank` أو `WATCH` أو `ABSTAIN`، من دون الادعاء باحتمال أو توصية شراء.

لا يلغي ذلك متطلبات الأرشيف، الختم المستقبلي، Denominator، التكاليف، وModel Card عندما يكون المطلوب Probability أو Backtest أو قياس دقة.

## ما كشفه التدقيق الجديد

كانت النسخة السابقة تمرر اختباراتِها، لكن المراجعة وجدت أربع فئات من المخاطر:

- كان Raw Hash محلولًا على مستوى الحزمة كلها، لا على مستوى المصدر؛ لذلك أمكن نظريًا أن ينسب Source A ملف Source B إلى نفسه.
- كان `QUALIFIED` يقبل صفر عناصر، وكان Access Receipt أو Search Index قابلًا نظريًا للدخول في سلسلة الدليل.
- كانت بعض أسطح المنصة الواحدة تحمل Independence Groups مختلفة؛ فكان يمكن أن يظهر Investing أو TradingView كأكثر من ناشر مستقل.
- كان وجود أي Catalyst رسمي للسهم يكفي لتأكيد Catalyst ثانوي آخر، حتى إن اختلف الحدث.

## الإصلاحات

- أصبح كل Raw Hash مرتبطًا إلزاميًا بـ`source_id` نفسه في Manifest وSource Observation وFinding.
- يُرفض أي Artifact جُمع بعد `decision_at`، وأي Raw Evidence سبق وقت إتاحة المعلومة.
- `QUALIFIED` يتطلب عنصرًا مؤهلًا واحدًا على الأقل، ولا يستطيع `ACCESS_RECEIPT` أو `SEARCH_INDEX` إنشاء Finding.
- يحمل كل Finding قائمة `evidence_roles`، ولا يستطيع دور سعري ملء نصاب الأخبار أو دور Community إثبات Catalyst.
- يُحسب نصاب الدور بصورة محافظة من أقل عدد بين الناشرين والأصول والأحداث المستقلة؛ تعدد الصفحات أو النسخ لا يصنع Quorum.
- أصبح Investing وتعليقاته Independence Group واحدة، وكذلك TradingView وIdeas.
- لا يتأكد Catalyst ثانوي إلا بوجود دليل Official/Issuer يطابق `event_key` والاتجاه نفسه.

## التجربة الحية

أُعيد Access Probe في 7 أغسطس 2026 الساعة 09:54 بتوقيت الكويت. هذا Probe يثبت الوصول فقط ولا يدخل في Research Rank.

- فتحت [بورصة الكويت](https://www.boursakuwait.com.kw/en/) وأكدت الصفحة أن بيانات السوق العامة متأخرة 15 دقيقة.
- ظهر فهرس [Market Summary التاريخي](https://reports.boursakuwait.com.kw/en/products-and-services/historical-data/reports/market-summary) من 2012 إلى 2026، لكن اكتمال الملفات يومًا بيوم لم يُثبت.
- ظهرت واجهة [Historical Disclosures](https://www.boursakuwait.com.kw/en/announcements/disclosures-and-announcements/historical-disclosures-and-announcements/) من دون Materialize للنتائج الديناميكية.
- فُتحت بوابة [CMA](https://www.cma.gov.kw/en/) وظهر رابط iFSAH، لكن محتوى نتائج iFSAH لم يُجمع في هذا Probe.
- فتحت صفحات الكويت في [TradingView](https://www.tradingview.com/markets/stocks-kuwait/)، [Investing.com](https://sa.investing.com/equities/kuwait)، [Argaam](https://www.argaam.com/kw-ar)، و[MarketScreener](https://www.marketscreener.com/stock-exchange/shares/middle-east/kuwait-116/).
- فتح Mubasher، لكن الصفحة المعروضة احتوت نسبًا قطاعية غير معقولة وحقول Render غير مستقرة؛ لذلك لا يُقبل منفردًا كمرجع رقمي.
- أعاد IndexSignal `403` عند الفتح المباشر، بينما ظهرت صفحاته في Search؛ والـSearch Snippet لا يُعد Evidence.
- لم يُرجع Yahoo Finance محتوى صالحًا، وانتهت محاولة KUNA المباشرة بـTimeout.
- ظهرت مواد حديثة قابلة للفتح من Reuters والراي كمصادر Editorial، لا كبديل للإفصاح الرسمي.
- فُتح [Common Crawl](https://commoncrawl.org/) و[Wayback Machine](https://web.archive.org/) للسياق والاسترجاع، لا كسجل سوق كامل أو First-public timestamp.
- تعرض [ICE](https://developer.ice.com/fixed-income-data-services/catalog/kuwait-stock-exchange-boursa-kuwait) Historical وLevel 1/2 ومنتجات Tick-by-tick، لكن استخدامها يتطلب Entitlement تجاريًا.

## نتيجة التحقق

- نجحت مجموعة Unit/Adversarial Tests المرافقة لهذا التدقيق. يُعاد حساب العدد في كل إصدار بواسطة CI، ولا يُعامل العدد التاريخي في إيصالات التشغيل المحلية بوصفه حالة الفرع الحالية.
- Python Compileall نجح.
- Smoke Check الاصطناعي نجح في اختبار العقود، لا في قياس أداء سوقي أوجاهزية تشغيل حية.
- المثال الاصطناعي وصل إلى `RESEARCH_READY` بلا Historical Pack أو Model Card.
- منتج Opening/Intraday بقي `EXECUTION_BLOCKED` بلا Feed مرخّص.
- Live Access Probe Validator نجح على 21 سجل مصدر، مع بقاء كل حالات `PARTIAL` و`ERROR` و`UNTESTED` ظاهرة.

## الرأي النهائي

هذا التصميم أصلح كأساس بحثي قابل للتدقيق لأنه لا يتوقف بسبب فشل موقع واحد، ويستخدم المنتديات والأرشيفات في الدور المناسب بدل إلغائها أوتصديقها بلا حدود. لكنه لا يمثل منصة Production مكتملة.

لكنه ليس Model بديلًا. الناتج الحالي يقيس قوة Mosaic Evidence داخل المجموعة المغطاة، لا احتمال ارتفاع السعر. أفضل مسار هو إبقاء شبكة المصادر افتراضية، ثم ختم نتائجها مستقبلًا في Ledger ثابت؛ وبعد تراكم جلسات كافية فقط يمكن تقييم ما إذا كانت سياسة الترتيب ذات قيمة تنبؤية فعلية.
