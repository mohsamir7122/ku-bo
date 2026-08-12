# حزمة اختبارات القبول الخصومية لـ KU-BO-011

هذه حزمة **Test Spec** اصطناعية وقابلة لإعادة التوليد. تضم 1,280 حالة رفض
مختلفة دلالياً لفرض Run Receipt وStage Binding عند حدود الاستيراد والمصالحة.
لا تنفذ KU-BO-011، ولا تثبت Market Evidence أوBacktest أوForecast أوأي ادعاء
مالي.

## التغطية

البنية مقفلة على:

```text
8 importer/reconciliation boundaries
x 40 mutation families
x 4 concrete attack channels/timings
= 1,280 unique cases and unittest methods
```

تغطي الحالات غياب/تزوير/انتهاء الإيصالات، خلط التشغيلات والدفعات والنوافذ
والمقامات، تغيّر شجرة المرحلة، المسارات غير الآمنة وTOCTOU، روابط المراحل
السابقة، ومنع ترقية Benchmark الخماسي أوFull Market أوD01 أوادعاءات يوليو
المحجوزة. كل حالة تتطلب الرفض قبل نشر Output.

## التدقيق والتشغيل

ثبّت اعتماد الاختبار ثم شغّل:

```bash
python -m pip install -e ".[test]"
python scripts/generate_ku_bo_011_corpus.py --check
python scripts/audit_ku_bo_011_corpus.py --json
python -m unittest tests.test_ku_bo_011_adversarial_corpus -v
```

يشغل الأمر الأخير 1,280 method مولدة بالإضافة إلى اختبارات بنية الحزمة.
يتحقق المدقق من SHA-256 وJSON Schema والتوازن والتطابق الحتمي، ويزيل
`case_id` وrun/time/path noise قبل حساب البصمة الدلالية كي لا يُحسب تغيير الاسم
كاختبار مختلف.

## ربط تنفيذ KU-BO-011

بعد أن يضيف Codex المنفذ Adapter مطابقاً لعقد الـHarness، شغّل الوضع الصارم:

```bash
python tests/ku_bo_011_harness.py \
  --strict-target-adapter \
  --adapter your_module:run_case
```

يجب أن يعيد الـAdapter لكل حالة رفضاً بـstable failure code ومن دون أي كتابة
في Output root. الوضع الصارم يفشل برمز خروج `2` إذا لم يُقدم Adapter؛ لذلك لا
يمكن تمرير الحزمة باعتبارها دليلاً على تنفيذ KU-BO-011 بينما هي مواصفات فقط.

## حدود الادعاء

- `Stage Binding v1.0` الحالي يثبت سلامة البايتات فقط؛ لا يثبت التطابق
  الدلالي مع run/cohort/window.
- يجب أن يضيف KU-BO-011 semantic admission موثقاً وألا يقلب ادعاء v1 القديم
  إلى `true` بلا عقد جديد أوإصدار Schema جديد.
- `KU-BO-008-D01` يبقى `OPEN`.
- Benchmark غير المتوافق، المقام الخماسي، Full Market، July legacy claims،
  Backtest، Forecast، Probability، وRecommendation تظل ممنوعة.
