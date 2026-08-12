# تدقيق مستودعات بورصة الكويت ذات الصلة — 2026-08-12

هذا جرد Read-only لحالة المستودعات والفروع في تاريخ التدقيق. لا يمنح إذنًا
بالدمج أوالحذف، ولا يحول أي Dataset قديم إلى دليل صالح لـKU-BO.

## الحكم التنفيذي

```text
ku-bo                  KEEP_AND_BUILD
AI-Mincy               KEEP_SELECTIVE_REFERENCE
KW                     ARCHIVE_SELECTIVE_SALVAGE
KW2                    ARCHIVE_UNMERGED_BRANCH_FIRST
Research               NO_SCORES_OR_BACKTEST_SALVAGE
Factor9-saudiai        ARCHIVE_NEGATIVE_CONTROL_ONLY
-Saudi-Arabia-Ai       NO_DIRECT_KUWAIT_SALVAGE
Social-media           OUT_OF_SCOPE_INDEPENDENT_PROJECT
```

لا يجوز نسخ Scores أوProbabilities أوRecommendations أوBacktest outputs من
أي مستودع إلى `ku-bo`. النقل المسموح مستقبلاً هو لعقد صغير أواختبار سلبي
بعد إعادة كتابته ضد عقود `ku-bo` الحالية وذكر `repository@SHA:path`.

## ku-bo

```text
main: be5fe3883016dedf07fa680905f7199f3906b4d8
latest merged work: PR #9
starting local suite: 513 PASS
GitHub Actions: 31402435102 PASS
```

النواة الحالية هي أفضل أصل للبناء: حماية Symlink/TOCTOU، عدم الكتابة فوق
Evidence، Hash reconciliation، Runtime Trust، وفحص Data Foundation ذي 12
بوابة. لكنها ليست Model/Backtest pipeline مكتملة ولا مصدر بيانات حيًا.

العيب التشغيلي المؤكد: `import-status-history` كان يمرر
`args.imported_at` غير المعرفة إلى دالة لا تقبل هذا الوسيط. يعالج KU-BO-009
العيب ويضيف اختبار Dispatch وInstalled-wheel.

PR #2 وPR #3 ما زالا مفتوحين على قاعدة قديمة وغير قابلين للدمج المباشر.
لا يُستخدمان كقاعدة ولا يُعمل لهما Cherry-pick شامل. إغلاقهما أوقطع فروعهما
قرار مستقل غير ممنوح في هذه المهمة.

## Research

```text
main: ec570513e072944858a4899a96b25629ddbeb38e
open Factor9 Draft PR #4 head: 783e4717b8e01b9b6d461e883965bc409f999423
```

الحكم: `NO-GO` للنتائج والدرجات والقرارات.

- لا توجد Boursa raw bytes أوOHLCV موثقة أوBenchmark أوCorporate Actions
  أوSource receipts أوPIT dataset committed.
- PR #4 يحتوي Package layout ثانية مبنية من Base قديم؛ دمجه يكرر الحزم.
- `BiweeklyBacktester` يطبق ترتيبًا محسوبًا من العينة الحالية على التاريخ؛
  Look-ahead صريح.
- Missing values تُملأ بصفر قبل Completeness، فتستطيع البيانات الغائبة رفع
  Confidence.
- Fundamentals تصنع حقولًا مثل `retained_earnings=net_income` وتستخدم وقت
  الاستخراج كتاريخ التقرير.
- Sentiment مبني جزئيًا على طول العنوان.

ما يمكن حفظه بعد إعادة كتابة: أفكار provider fallback، rate limiting،
PDF/unit-normalization tests، وbounded IR discovery. لا تُنقل معادلات Score
أوConfidence أوBacktest outputs.

## AI-Mincy

```text
main: 85044b681b7048ac373e47e31f6c2bfa7a885c9c
important Draft branch: agent/rebuild-ai-mincy-core-v2-20260805
head: 51eb5449da225ef990facc803ce4c3bb7fb5e6b2
```

الحكم: `KEEP` كمرجع حوكمة ومعرفة سلبية، لا دمج كامل.

المفيد: فصل transport success عن semantic success، capability fallback،
zero-result receipts، source certainty مقابل analytical certainty، وأدوات
signed/source receipts. لكن بعض مسارات V2 تثق في Booleans ذاتية ودرجات يقين
ثابتة، فلا تنقل Engine أوWalk-forward كما هما.

## KW

```text
main: 408e0869104e172289c377bb214692d924e41eeb
repository state: archived
```

الحكم: `ARCHIVE` مع إنقاذ انتقائي للعقود والاختبارات. لا توجد فروع حالية
بمسارات فريدة لا تظهر في `main`.

المفيد: entity resolution، governance، historical snapshot، phase contracts،
و33 اختبارًا سلبيًا في `tests/test_rules.py`. غير الصالح: live script ذي
الإشارات الثابتة، labels المصنوعة من ترتيب النسب، challenger lift ثابت،
تحويل timestamp مفقود إلى `now`، وsample universe غير موثوق.

## KW2

```text
main: c5ac4085bd8c114baf74f3ad23fd737646a53455
unmerged branch: mohx-fresh-rebuild
head: efcb3053b12b70bdcda4785bade6f27fe748d2de
```

`main` شبه فارغ، لكن الفرع غير المدمج يحتوي `AGENTS.md` و`README.md` فريدين.
يجب Snapshot للفرع قبل أي حذف مستقبلي. يحمل عقد Raw/Bronze/Silver/Gold،
حقول Provenance، واختبارات هوية/PIT جيدة؛ أهمها أن Ticker ليس Primary Key،
وأن Raw وAdjusted prices منفصلان، وأن أي Feature بعد Prediction timestamp
مرفوضة.

## Factor9-saudiai

```text
main: 76df65b506f96b5383f469a6d4bb3582c4ea896b
repository state: archived
```

رغم الاسم السعودي، تحوي ZIPs مواد كويتية. يجب أرشفة المستودع كاملًا وجرد
`1.zip` و`2.zip` الكبيرين قبل أي حذف. البيانات ليست Training evidence صالحة.

نتائج التدريب المحفوظة Negative control فقط:

```text
rows: 264
symbols: 12
dates: 22
folds: 2
combined AUC: 0.422891
news-only AUC: 0.423210
docs-only AUC: 0.442563
```

النتائج أقل من 0.5، وتقارير overlap تفيد بأن أسعار الويب الحديثة لا تتقاطع
مع الأحداث القديمة. كما أن manifests/metrics المشار إليها غير مكتملة. لا
تُستخدم هذه الملفات للتدريب أوالتوصية؛ تحفظ كأثر تاريخي يمنع تكرار مسار فاشل.

## مستودعات أخرى

- `-Saudi-Arabia-Ai@bf9df77...`: لا إنقاذ مباشر للكويت؛ بعض القوالب فقط
  مرجع عام. التنفيذ يجعل official/verified افتراضيًا ويحتوي خطر Future
  leakage وfallback Demo قد يعيد `ok`.
- `Social-media@d5fb520...`: مشروع مستقل خارج نطاق تنظيف سوق الكويت. يمكن
  الرجوع إلى أنماط leases/idempotency فقط، ولا يجوز حذفه ضمن هذه المهمة.
- المستودعات الطبية والعامة الأخرى ليست مصدرًا واضحًا لبورصة الكويت.

## ترتيب الحفظ المقترح قبل أي تنظيف مستقبلي

1. إبقاء `AI-Mincy` كما هو.
2. حفظ `KW2/mohx-fresh-rebuild` قبل لمس المستودع.
3. حفظ `Factor9-saudiai` كاملًا ثم جرد ZIPs الكبيرة محليًا بأداة bounded.
4. حفظ رؤوس PRs المفتوحة في `Research` وفصل المادة الطبية عن السوقية.
5. حفظ تاريخ Git كاملًا لـ`KW` ثم إعادة كتابة الاختبارات المفيدة فقط.
6. عدم لمس `Social-media` أوالمشروعات الطبية في تنظيف الكويت.

كل حذف أوإغلاق PR أوBranch يحتاج قرار مستخدم منفصل مسجل في
`docs/codex/USER_DECISIONS.md`.
