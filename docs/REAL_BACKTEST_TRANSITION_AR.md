# التحول إلى Backtest حقيقي Point-in-Time

هذه الوثيقة تحدد الخطوات المطلوبة للانتقال من Pilot جاهز تقنيًا إلى Backtest حقيقي قابل للدفاع عنه. الاسم التشغيلي الدقيق لهذه المرحلة هو:

`Point-in-Time Real Backtest Readiness`

المقصود بها أن كل قرار قديم يعاد بناؤه كما لو كنا نقف في ذلك اليوم فعلًا: نفس الكون المتاح وقتها، نفس الأسعار المتاحة وقتها، نفس الأخبار المتاحة قبل القرار، ونفس قواعد الدخول والخروج قبل معرفة النتيجة.

## 1. الحالة الحالية

المستودع يثبت الآن الآتي:

- توجد طبقة `symbol_mapping` أولية لخمسة أسهم: `KFH`, `NBK`, `ZAIN`, `HUMANSOFT`, `MABANEE`.
- توجد خطة Capture من روابط Investing التاريخية.
- Public capture من Investing يتوقف عند `robots.txt`، لذلك لا نعتمد عليه كمسار عام.
- يوجد مسار `USER_EXPORT` لاستيراد CSV مصرح أو محفوظ يدويًا، وحفظ الخام مع `SHA-256`.
- ينتج `USER_EXPORT` ملفًا موحدًا: `normalized/eod_ohlcv.csv`.
- اختبارات الوحدة تثبت أن المسار يعمل على Fixture تعاقدية، لا على أسعار سوق حقيقية.

هذا يعني أن المشروع جاهز لاستقبال الوقود الحقيقي، لكنه لم يدخل Backtest حقيقي بعد.

## 2. تعريف Go إلى Backtest الحقيقي

لا يبدأ Backtest الحقيقي إلا إذا تحققت الشروط التالية:

- اكتمال `security_code` و`ISIN` لكل سهم داخل `config/symbol_mapping.json`.
- وجود CSV فعلي لكل سهم من مصدر مصرح أو Export يدوي محفوظ.
- وجود `Point-in-Time Universe` بتاريخ كل قرار.
- وجود `Trading Calendar` رسمي أو مرخص يغطي أيام الدخول والخروج.
- وجود `Corporate Action Ledger` يغطي Splits, Bonus, Cash dividends, Suspensions, Name changes.
- وجود Benchmark واضح مثل مؤشر السوق الأول أو العام حسب المنتج.
- وجود `Feature Snapshot` محفوظ قبل القرار، لا يحتوي أي معلومة مستقبلية.
- وجود `Forecast Ledger` يسجل كل قرار قبل النتيجة.
- وجود Outcome Evidence لاحق مستقل لحساب العائد.
- اجتياز `STOP_BACKTEST` gates كلها.

أي نقص في هذه الشروط يعني أن النتيجة لا تسمى Accuracy ولا Probability. أقصى ما يمكن قوله وقتها: Pilot, Dry run, أو Data readiness.

## 3. تجهيز ملفات الأسعار للخمسة أسهم

أنشئ أولًا Workspace جديدًا بواسطة `prepare-price-collection-workspace`، ثم ضع ملفات CSV داخل مجلد `raw_exports/investing/` الناتج. لا تُدخل CSV مباشرة بلا Manifest مراجع.

للاستخدام التعليمي فقط، أسماء الملفات هي:

```bash
KFH.csv
NBK.csv
ZAIN.csv
HUMANSOFT.csv
MABANEE.csv
```

الأعمدة يجب أن تكون بنفس ترتيب Investing:

```text
Date,Price,Open,High,Low,Vol.,Change %
```

التواريخ يجب أن تكون مرتبة من الأحدث إلى الأقدم. إذا كان التاريخ بصيغة مثل `Aug 06, 2026` فيجب أن يكون الحقل مقتبسًا داخل CSV لأن به فاصلة.

## 4. استيراد USER_EXPORT

بعد وضع الملفات وملء `manifests/price_collection_manifest.csv` وتعيين `review_status=ACCEPTED`، شغل من مسار جديد وفارغ:

```bash
PYTHONPATH=src python -m kubo.cli_v3 --project-root . import-investing-user-exports \
  --input-dir runtime/price_collection/seed_run_001/raw_exports/investing \
  --output-root runtime/user_exports/seed_run_001 \
  --observed-at 2026-08-08T12:00:00+03:00
```

المخرجات المتوقعة:

```text
runtime/user_exports/seed_run_001/manifest.json
runtime/user_exports/seed_run_001/price_collection_manifest.csv
runtime/user_exports/seed_run_001/source_observations.json
runtime/user_exports/seed_run_001/parser_plan_investing_user_export_draft.json
runtime/user_exports/seed_run_001/normalized/eod_ohlcv.csv
runtime/user_exports/seed_run_001/user_export_import_report.json
```

إذا ظهر `missing_exports` أو`rejected_exports` أوManifest error، لا يبدأ Backtest. والـParser file الناتج Draft محجوب؛ لا يُمرر إلى `materialize-parser-run` قبل إضافة Artifact هوية رسمي وEffective-dated bindings موثقة.

## 5. تحويل الأسعار إلى Daily EOD حقيقي

ملف `normalized/eod_ohlcv.csv` الناتج من USER_EXPORT هو بداية جيدة، لكنه ليس كافيًا وحده للـBacktest. يجب ترقيته إلى عقد `daily_eod` الكامل، وفيه على الأقل:

```text
trade_date,security_code,ticker,open_fils,high_fils,low_fils,close_fils,volume,value_traded_kwd,trade_count,reference_price_fils,trading_status,corporate_action_status,raw_sha256
```

يجب تحديد هل الأسعار Adjusted أم Raw. إذا كانت Raw يجب استخدام `corporate_actions.csv` لحساب `price_adjustment_factor` عند التقييم.

## 6. بناء Universe مؤرخ

لكل يوم قرار يجب إنشاء `universe.json` يثبت أن الأسهم المختبرة كانت ضمن الكون المتاح في ذلك اليوم.

للخمسة أسهم فقط، يكون Scope:

```text
NAMED_SECURITIES
```

ولا يجوز تسمية هذا Full Market. لا يصبح Full Market إلا بعد تغطية كل الشركات المدرجة في ذلك التاريخ، مع إثبات العضوية من مصدر رسمي أو مرخص.

## 7. بناء Trading Calendar

يجب إنشاء `trading_calendar.csv` يغطي كل أيام الدخول والخروج، ويثبت:

- هل اليوم جلسة تداول أم عطلة.
- هل السهم موقوف.
- هل يوجد تداول فعلي أو سعر مرجعي فقط.
- اليوم الصحيح للخروج حسب Horizon، مثل جلسة واحدة أو خمس جلسات.

بدون Calendar لا يمكن حساب Horizon بدقة.

## 8. بناء Corporate Action Ledger

يجب إنشاء `corporate_actions.csv` لكل سهم في النافذة الزمنية، مع Evidence raw لكل حدث.

الأحداث الحرجة:

- Cash dividend.
- Bonus shares.
- Stock split أو reverse split.
- Capital increase.
- Suspension.
- Delisting أو ticker/name change.

إذا لم توجد أحداث، نحتاج Zero-result موثق، وليس ترك الملف فارغًا بلا دليل.

## 9. بناء Benchmark

كل Outcome يحتاج Benchmark entry وexit. يجب اختيار Benchmark قبل التشغيل:

- مؤشر السوق الأول إذا كان المنتج يركز على الأسهم القيادية.
- مؤشر السوق العام إذا كان المنتج يغطي السوق كله.
- Benchmark مخصص للقطاع إذا كان الاختبار قطاعيًا.

لا يجوز تغيير Benchmark بعد ظهور النتيجة.

## 10. إنشاء Feature Snapshots

لكل قرار قديم، يجب حفظ ملف Features يحتوي فقط ما كان معروفًا قبل `decision_at`.

أمثلة Features مسموحة:

- Price momentum حتى آخر جلسة متاحة قبل القرار.
- Volume trend حتى آخر جلسة متاحة قبل القرار.
- News أو disclosures منشورة ومتاحة قبل القرار.
- Sentiment من Telegram أو منتديات بشرط إثبات `available_at`.

الممنوع:

- سعر نفس اليوم بعد القرار.
- خبر منشور بعد القرار.
- Corporate action أُعلن بعد القرار.
- أي Ranking بني على Outcome لاحق.

## 11. إنشاء Forecast Ledger

كل Prediction يجب أن يكتب إلى Ledger قبل معرفة Outcome، ويحتوي:

- `decision_id`
- `security_code`
- `decision_at`
- `outcome_due_at`
- `horizon_sessions`
- `score`
- `rank`
- `selected`
- Hashes للـfeatures, universe, calendar, policy, code

أي Prediction غير موجود في Ledger لا يدخل التقييم.

## 12. بناء Outcomes

بعد حلول `outcome_due_at`، أنشئ Outcome لكل سهم في الكون، وليس فقط الأسهم التي نجحت.

كل Outcome يحتاج:

- Entry price.
- Exit price.
- Benchmark entry وexit.
- Corporate action adjustment factor.
- Cash distribution return.
- Fees, spread, slippage, market impact إذا كان الاختبار تنفيذًا حقيقيًا.
- Evidence hash لكل مصدر سعر وBenchmark وCorporate action.

## 13. تشغيل Stop Gates

قبل التقييم شغل أو ابن تقرير gates. النتيجة المقبولة الوحيدة للانتقال إلى التقييم:

```text
READY_TO_SCORE
```

إذا ظهرت:

```text
STOP_BACKTEST
```

فلا يوجد Backtest حقيقي.

إذا ظهرت:

```text
STOP_INFERENCE
```

فالبيانات قد تكون سليمة لكن عدد التواريخ أو الأحداث لا يكفي للاستنتاج.

## 14. تشغيل Evaluation

بعد اكتمال Predictions وOutcomes وLedger وModel card، يمكن استخدام `evaluate_forecasts` لحساب:

- Rank IC.
- Hit Rate.
- Precision@TopK.
- Recall.
- Gross return.
- Net excess return.

الناتج لا يصبح Probability إلا إذا كان `model_card` يسمح بذلك صراحة وبشروط Prospective validation.

## 15. خطة التنفيذ العملية للخمسة أسهم

ابدأ بهذه الخطة الصغيرة:

1. أكمل `ISIN` و`security_code` للخمسة أسهم.
2. ضع CSV حقيقي لكل سهم من 2024-01-01 إلى 2026-08-08.
3. شغل `import-investing-user-exports`.
4. راجع `user_export_import_report.json`.
5. حول `eod_ohlcv.csv` إلى عقد `daily_eod` الكامل.
6. ابن `trading_calendar.csv` لنفس الفترة.
7. ابن `corporate_actions.csv` مع Evidence أو Zero-result موثق.
8. ابن Benchmark daily close لنفس الفترة.
9. اختر Horizon واحدًا فقط كبداية، مثل خمس جلسات.
10. أنشئ Decisions شهرية أو أسبوعية، ولا تبدأ بكل يوم من البداية.
11. احفظ Feature snapshot لكل قرار.
12. اكتب Forecast Ledger.
13. ابن Outcomes بعد Horizon.
14. شغل Stop Gates.
15. إذا ظهرت `READY_TO_SCORE` فقط، شغل Evaluation.

## 16. معيار القرار النهائي

قرار `GO` إلى Backtest الحقيقي:

- لا توجد ملفات CSV ناقصة.
- لا توجد Rejections في USER_EXPORT.
- كل Raw artifact له Hash.
- Universe مؤرخ ومكتمل للخمسة.
- Calendar يغطي كل Horizon.
- Corporate actions موثقة أو Zero-result موثق.
- Benchmark موجود.
- Ledger موجود ومختوم أو قابل للتحقق.
- Stop gates تعطي `READY_TO_SCORE`.

قرار `NO-GO`:

- أي سعر بلا Raw hash.
- أي سهم بلا `security_code` أو `ISIN`.
- أي Outcome بلا Benchmark.
- أي Corporate action status يظل `raw_unadjusted` من غير Ledger.
- أي قرار بني بعد معرفة النتيجة.
- أي محاولة لا تحتوي Denominator كامل لكل الأسهم المختبرة.

## 17. الخلاصة التشغيلية

المرحلة الحالية اسمها:

`Live Pilot Data Import`

المرحلة التالية المطلوبة قبل Backtest:

`Point-in-Time Real Backtest Readiness`

أول Backtest حقيقي مسموح به يجب أن يكون محدودًا:

```text
5 أسهم، Horizon واحد، فترة قصيرة، Denominator كامل، وSTOP gates = READY_TO_SCORE
```

بعد نجاح ذلك فقط يمكن التوسع إلى 30 سهمًا ثم إلى Full Market.
