# جاهزية Backtest الحقيقي الحالية

تاريخ الفحص: `2026-08-08`

قرار الحالة الحالية:

`NO-GO_FOR_REAL_BACKTEST`

السبب ليس في كود الاختبار نفسه، بل في اكتمال أدلة السوق المطلوبة قبل القياس.

## ما أصبح جاهزًا

- خريطة أولية للخمسة أسهم داخل `config/symbol_mapping.json`.
- أُدخلت قيم Seed لـ`security_code` و`ISIN` للخمسة أسهم، واجتازت التحقق البنيوي؛ لكنها لا تُعد إثبات هوية رسميًا قابلًا للتدقيق قبل حفظ التقرير الرسمي وبصمته وفعاليته الزمنية.
- روابط Investing التاريخية للخمسة أسهم.
- خطة Capture للـLive Pilot.
- مسار `USER_EXPORT` لاستيراد CSV مصرح بعد التحقق من Collection Manifest والـHash والهوية والوحدة.
- إنتاج `normalized/eod_ohlcv.csv` من ملفات CSV.
- إنتاج Parser Plan Draft محجوب بدل ادعاء وجود Plan صالح بلا Artifact هوية رسمي.
- اختبارات وحدة ومسار Smoke ناجحة.

## حالة الأسهم الخمسة

```text
NBK: security_code 101، ISIN KW0EQ0100010
KFH: security_code 108، ISIN KW0EQ0100085
MABANEE: security_code 413، ISIN KW0EQ0400725
ZAIN: security_code 605، ISIN KW0EQ0601058
HUMANSOFT: security_code 623، ISIN KW0EQ0601694
```

## ما يمنع Backtest الحقيقي الآن

- لا توجد ملفات CSV حقيقية وCollection Manifest بحالة `ACCEPTED` للخمسة أسهم داخل Run-scoped Workspace.
- لا يوجد Artifact هوية رسمي حديث وEffective-dated bindings يسمحان بتحويل Draft إلى Parser Plan قابل للتنفيذ.
- لا يوجد `daily_eod` كامل بالعقد المطلوب.
- لا يوجد `trading_calendar.csv` للفترة.
- لا يوجد `corporate_actions.csv` موثق أو Zero-result موثق.
- لا يوجد Benchmark price series للفترة.
- لا توجد Feature snapshots مؤرخة.
- لا توجد Forecast ledger predictions حقيقية.
- لا توجد Outcome evidence packets.
- لم تصل Stop gates إلى `READY_TO_SCORE`.

## الخطوة التالية المباشرة

الخطوة التالية ليست تشغيل Evaluation، بل سد فجوة ملفات الأسعار الحقيقية ثم بقية أدلة السوق:

1. إنشاء Workspace جديد بواسطة `prepare-price-collection-workspace`.
2. وضع CSV حقيقي للخمسة وملء Manifest بالـSHA-256 والوحدة والحالة `ACCEPTED`.
3. تشغيل `import-investing-user-exports` إلى Output جديد.
4. إضافة Artifact الهوية الرسمي وبناء Parser Plan صحيح.
5. تحويل الناتج إلى `daily_eod` كامل.
6. إضافة Calendar وCorporate Actions وBenchmark.
7. إنشاء أول مجموعة Decisions محدودة.
8. تشغيل Stop gates.

خريطة الـSeed ليست إكمالًا لإثبات الهوية. يظل التشغيل `BLOCKED` ما لم توضع ملفات CSV الحقيقية داخل `runtime/price_collection/<run>/raw_exports/investing/` ويُستكمل Collection Manifest الخاص بالـRun بحالة `ACCEPTED`، ثم يُضاف Artifact الهوية الرسمي؛ فالمجلد `examples/investing_user_exports/` للتوثيق فقط ولا يسمح النظام بتوليد أسعار مصطنعة للـBacktest الحقيقي.

لا يتم استخدام كلمة Accuracy إلا بعد اكتمال هذه الخطوات.
