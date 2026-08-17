# الفصل الكامل بين إفصاحات HUMANSOFT التاريخية والبيانات الحديثة

## القرار البنيوي

أصبح المنتج مبنيًا على خمسة مجالات بيانات مستقلة، لا على ملف واحد مختلط:

1. `HISTORICAL_DISCLOSURE_ARCHIVE`: إفصاحات رسمية تاريخية بنظام Append-Only.
2. `HISTORICAL_EVENT_MARKET_WINDOW`: عشرون جلسة قبل الإفصاح وعشرون بعده، مجمّدة بعد اكتمالها.
3. `HISTORICAL_PUBLIC_OPINION_ARCHIVE`: رأي عام موثق ومجمّد عند تاريخ الالتقاط.
4. `RECENT_DAILY_MARKET_SERIES`: بيانات سوق يومية حديثة Rolling، للسياق الحالي فقط.
5. `LATEST_FINANCIAL_SNAPSHOT`: أحدث Financial Snapshot، للسياق المالي الحالي فقط.

## الإفصاحات والتصحيحات التاريخية

الإفصاح الأصلي لا يُعدّل ولا يُستبدل. أي Correction أو Supplement أو Withdrawal يُحفظ كسجل جديد مع `corrects_record_id` أو `supersedes_record_id`، داخل Canonical Cluster نفسه. وبذلك تبقى الحقيقة التاريخية حول ما كان منشورًا ومتى كان متاحًا محفوظة.

## بيانات السهم اليومية الحديثة

السلسلة اليومية الحديثة قابلة للتحديث لأنها تمثل الحالة الراهنة. لكنها لا تحتوي على `disclosure_id` أو نص الإفصاح أو Financial Snapshot، ولا تستطيع إعادة حساب نتيجة حدث تاريخي مجمّد.

## أحدث البيانات المالية

Latest Financial Snapshot تُستبدل عند ظهور فترة أحدث، لكنها لا تحتوي على أسعار يومية أو رأي عام أو رابط Event Cluster، وتحمل دائمًا:

`historical_reaction_input_allowed = false`

## تحليل الإفصاح

المحرك يقبل فقط المجالات التاريخية الثلاثة: الإفصاح، نافذة السوق التاريخية، والرأي العام التاريخي. ثم يجيب وصفيًا:

- بدأ الارتفاع قبل الإفصاح واستمر بعده.
- بدأ قبل الإفصاح فقط.
- بدأ مباشرة بعد الإفصاح.
- ظهر مؤقتًا بعد الإفصاح ثم تلاشى.
- ظهر متأخرًا بعد الإفصاح.
- لم يظهر ارتفاع واضح.

ولا يعرض سعرًا أو نسبة عائد، ولا يصدر Forecast أو Recommendation، ولا يدعي سببية أو تسريبًا.

## الاختبارات المستهدفة

تغطي الاختبارات:

- رفض أي Price أو Financial field داخل Historical Disclosure.
- رفض نص الإفصاح أو Financial metrics داخل Historical Market Window.
- حفظ التصحيح كسجل مستقل Append-Only.
- منع Recent Daily Market من الإشارة إلى Disclosure أو إعادة حساب حدث تاريخي.
- منع Latest Financial Snapshot من احتواء سعر يومي أو دخول Historical Reaction.
- ثبات نتيجة الحدث التاريخي عند تغيير بيانات السوق الحديثة.
- مطابقة IDs وCanonical Cluster ووقت إتاحة الإفصاح.
- عدم عرض أي رقم سوقي في النتيجة.
- STOP عند نقص الجلسات أو Benchmark أو Corporate Actions evidence.

## الحد الفعلي

هذا الفصل يمنع خلط الطبقات برمجيًا، لكنه لا يخلق البيانات غير الموجودة. تشغيل الدراسة على جميع الإفصاحات الحقيقية ما زال يحتاج أرشيفًا رسميًا كاملًا، وتوقيتات Availability، وCorporate Actions، وأسعار Total Return، وMarket/Sector Benchmarks موثقة.
