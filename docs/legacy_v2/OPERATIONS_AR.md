# التشغيل وجمع البيانات

## مرحلة 0: تعريف Trial قبل الجمع

جمّد قبل النظر إلى النتائج:

- المنتج والأفق والهدف.
- Decision Cutoff.
- الكون والBoard.
- Entry/Exit وBenchmark.
- Costs وNon-fill.
- Baselines.
- Training/Calibration/Test Windows وPurge/Embargo.
- Metrics وMinimum Sample/Power.
- Trial ID وPolicy Hash.

أي تغيير بعد رؤية Outcome هو Trial جديد، لا Revision صامت.

## مرحلة 1: فحص المصدر

سجل Source Access مستقلًا:

- وقت الفحص.
- حالة `AVAILABLE`, `BLOCKED`, `AUTH_REQUIRED`, `NOT_TESTED`.
- الطريقة المصرح بها.
- Error/HTTP أو ملاحظة واضحة.

لا تحول هذه الحالة إلى Capability. هي مجرد Health Observation.

## مرحلة 2: الجمع المحدود

لكل Run:

- ضع Request/Byte/Time budgets.
- حافظ على Zero-yield counter لكل Source Family.
- توقف عند CAPTCHA أو Login أو Rate Limit أو Robots/Protection.
- لا تخمن Endpoints غير موثقة.
- لا تستبدل البيانات الرسمية ببيانات مصطنعة عند الفشل.
- احفظ Response أو الملف كما وصل قبل Parse.

إذا نفدت الميزانية، سجل `BUDGET_EXHAUSTED`. إذا كان المصدر محجوبًا، سجل `BLOCKED`. لا تستخدم كلمة `QUALIFIED` إلا بعد المصالحة.

## مرحلة 3: بناء Pack

رتب الملفات في `raw/`, `normalized/`, `manifests/`. ثم شغّل:

```bash
kubo validate-pack --pack /absolute/path/to/pack
```

لا تنتقل إلى Features إذا لم تكن الحالة `PASS`.

## مرحلة 4: بناء Features

- ابنِ Decision Snapshot لكل ورقة في Denominator، لا المختارة فقط.
- استخدم البيانات ذات `available_at <= decision_at`.
- سجل Unknown بدل Zero عند عدم الرصد.
- احفظ Feature Snapshot ببصمته.
- افصل Core، Official، News، Social إلى Ablations قابلة للمقارنة.

## مرحلة 5: إصدار Forecast

- تحقق من Model Card.
- أنشئ Universe Artifact وCalendar Artifact وPolicy/Code/Feature hashes.
- أضف CREATE Event إلى Ledger قبل Outcome.
- اختم Ledger حسب Cadence ثابتة.
- لا تعدل السطر؛ استخدم AMEND/WITHDRAW/EXPIRE بوقت مستقبلي.

## مرحلة 6: التقييم

- انتظر `outcome_due_at` المجمد.
- ابنِ Outcome لكل صف في Denominator.
- طبق Corporate Actions.
- أعد حساب Benchmark وCosts وFills.
- شغّل Stop Gates.
- إن كانت البوابات سليمة والعينة صغيرة، أعلن `STOP_INFERENCE`.
- إن فشل عقد Critical، أعلن `STOP_BACKTEST` ولا تعرض Accuracy مختصرة.

## Runbook لموقع بورصة الكويت

عند توافر بيانات رسمية قابلة للحفظ:

- احفظ الملف/الاستجابة والبصمة والتوقيت والرابط.
- صنف صفحات التداول العامة كبيانات مؤجلة.
- استخدم البيانات بعد الجلسة في EOD فقط إذا اكتملت وتصالحت.
- سجل أي تعطل حالي في Source Access، ولا تمسح الأرشيف السابق.

عند عدم التوافر:

- لا تجعل Source Failure يختفي.
- استخدم CMA/iFSAH أو IR لإثبات الإفصاح فقط.
- استخدم المصادر الثانوية للاكتشاف والمقارنة لا لادعاء Official Truth.
- اترك Capability مفقودة، ودع المنتج يتوقف.

## Runbook للتنفيذ الحي

قبل تمكين opening/intraday، يجب تسجيل مزود فعلي بدل القالب غير المهيأ، مع:

- Domain/Account/Entitlement موثق.
- Auction وIntraday وL1 وExecution fields.
- Provider timestamp وObserved timestamp وDelay declaration.
- Bid/Ask وReference Price وMarket Phase وTrading Status.
- سياسة Queue, Limit, Spread, Slippage, Impact, Non-fill.

بيانات +10% لا تعني Fill. يجب أن يظل Limit print censored حتى يوجد دليل قابلية دخول.

## أوامر التحقق قبل أي Release

```bash
PYTHONPATH=src:tests python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests scripts
PYTHONPATH=src python3 scripts/smoke_check.py
```

ثم سجل:

- عدد الاختبارات ونتيجتها.
- Hash الحزمة أو Release Archive.
- تاريخ UTC والكود المستخدم.
- الحدود المعروفة.

نجاح الكود لا يساوي نجاح المصدر، ونجاح المصدر لا يساوي اكتمال البيانات، واكتمال البيانات لا يساوي صلاحية النموذج.
