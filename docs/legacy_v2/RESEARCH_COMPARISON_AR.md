# مقارنة طرق التحليل والمشاريع المشابهة

تاريخ التحقق: 7 أغسطس 2026.

## قاعدة المقارنة

المقارنة هنا معمارية ومنهجية. لا ننقل رقم أداء من سوق أو فترة أخرى إلى بورصة الكويت، ولا نعتبر كثرة Agents أو LLMs دليلًا إحصائيًا.

الـRegistry الآلي موجود في `research/competitor_registry.json`.

## Qlib

المفيد:

- فصل Dataset/Model/Backtest/Portfolio workflow.
- Experiment tracking وBaselines قابلة للتكرار.
- التعامل مع البحث الكمي كمنظومة لا Script واحد.

المطبق في KU-BO:

- Catalog للمنتجات والطرق.
- Model Card وTrial Registry hashes.
- Baseline-first وWalk-forward gates.

غير المنقول:

- لا نفترض أن Data adapters أو Results في أسواق أخرى تصلح للكويت.

## FinGPT

المفيد:

- Financial NLP وRetrieval على الأدلة.
- فصل النص المالي عن النموذج الرقمي النهائي.

المطبق:

- LLM/NLP كـEvent Extractor لا كمصدر Probability مباشر.
- Evidence hashes وتوقيت الإتاحة والربط بالورقة.

غير المنقول:

- أي Label أو sentiment benchmark غير كويتي لا يصبح تلقائيًا Alpha.

## TradingAgents وFinRobot

المفيد:

- فصل أدوار التحليل والمخاطر والمراجعة.
- إخراج Thesis منظم وقابل للنقد.

المطبق:

- فصل Evidence extraction وRanking وRisk/Execution وEvaluation.

المرفوض:

- اتفاق Agents ليس Ensemble مستقلًا إذا كانوا يعتمدون النموذج والبيانات نفسيهما.
- لا يسمح Agent بتجاوز Model Card أو Stop Gates.

## Janus-Q

المفيد:

- تمثيل الخبر كحدث مرتبط بسهم ونوع واتجاه.
- ربط الحدث بـCAR أو رد فعل غير طبيعي عبر أفق واضح.
- Event taxonomy بدل sentiment ثنائي فقط.

المطبق:

- Event identity والعلاقات والتجميع.
- Official Event Study كطريقة مستقلة.
- قياس Event windows متعددة بعد ضبط Point-in-Time.

غير المنقول:

- حجم corpus أو taxonomy أو النتائج المنشورة لا تثبت أداءً في الكويت.

## ECON

المفيد:

- Social لا يدخل خامًا.
- القطاع والسياق الاقتصادي والاحتمال الكبير/التقلب عوامل منفصلة.

المطبق:

- Social diffusion لا Fact count.
- منتجات Rare-event منفصلة عن اتجاه العائد.
- Benchmark السوق والقطاع.

## Evidence Map لأنظمة Agentic Trading

الرسالة الأهم ليست أن Agents تفشل دائمًا، بل أن الدليل المنشور غالبًا ضعيف في Time splits والتكاليف وSurvivorship وإعادة الإنتاج.

المطبق في KU-BO:

- Chronological walk-forward وPurge/Embargo Gates.
- Full denominator.
- Costs/Non-fill/Limit censoring.
- Trial Registry وLedger/Seal.
- `STOP_INFERENCE` عند قلة التواريخ المستقلة.

## طريقة المقارنة التي سيستخدمها المشروع

لكل Method Candidate:

1. سجل الفرضية والTarget والأفق قبل الاختبار.
2. قارنه بـNaive/Market/Sector/Liquidity baseline.
3. اختبر Core فقط.
4. أضف Official Events.
5. أضف News context.
6. أضف Social diffusion في Ablation مستقل.
7. استخدم Walk-forward مع Purge/Embargo.
8. أعد الحساب بعد Costs وNon-fill.
9. اعرض الأداء حسب التاريخ والسيولة والقطاع والنظام السوقي.
10. لا ترقِّ النموذج إلا بنتيجة Prospective مختومة.

## ما الذي نبحث عنه على الإنترنت دوريًا؟

- مشاريع Open-source ذات Code وData contracts وBacktest موثق.
- أبحاث Event extraction وArabic financial NLP.
- دراسات تنفيذ Microstructure في أسواق ذات حدود سعرية.
- Evidence maps أو Replication studies، لا Leaderboard فقط.
- تغييرات رسمية في قواعد بورصة الكويت وCMA.

كل تحديث يسجل تاريخ الفحص والرابط والادعاء القابل للاختبار وما تم تبنيه وما تم رفضه.
