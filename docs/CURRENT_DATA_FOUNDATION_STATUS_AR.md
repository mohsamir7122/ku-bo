# الحالة الحالية لـData Foundation Pilot

تاريخ اللقطة: `2026-08-09`

الفرع:

```text
build/data-foundation-v0.2
```

الأساس:

```text
main@3be345f667316c49aa0e9210fcefef7231891d51
```

## ما نُفذ

- فصل Pilot Identity Seed عن Vendor Symbol Mapping.
- حصر Pilot في NBK وKFH وMABANEE وZAIN وHUMANSOFT.
- إنشاء Workspace لملفات User Export المصرح بها.
- التحقق من Collection Manifest وSHA-256 والتوقيت والوحدة وPrice Basis.
- تحليل Investing CSV مباشرة من دون توليد HTML وسيط.
- إنتاج `normalized/research_price_history.csv` بعقد مستقل عن Official Complete `daily_eod`.
- إنتاج Data Quality Report وEvidence Manifest وSource Observation.
- إضافة CLI مستقل باسم `kubo-data-foundation`.
- إضافة JSON Schemas واختبارات Unit وEnd-to-End.

## الحدود الحالية

لا توجد داخل المستودع ملفات أسعار سوق حقيقية، ولا Official Identity Artifact، ولاTrading Calendar، ولاSecurity Status History، ولاCorporate Action Ledger، ولاBenchmark.

لذلك أقصى حالة تشغيلية عند نجاح ملفات الأسعار الخمسة هي:

```text
BLOCKED_OFFICIAL_IDENTITY
```

مع حالة فرعية:

```text
RESEARCH_PRICE_HISTORY_READY
```

ولا يسمح هذا الفرع بـForecast أوProbability أوRecommendation أوAccuracy أوReal Backtest.

## معيار القبول

المرجع الحالي لقبول الكود هو GitHub Actions الخاصة بالـPull Request، وتشمل Compile، Full Unit/Adversarial Suite، Parser Gates، Synthetic Smoke Check، Secret Guard، وبناء Wheel.
