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

## إصدار الوصف التنفيذي v3

يصنف الإصدار `ku-bo-011-adversarial-case-v3` كود الفشل ومرحلته عند النقطة
التي يستطيع فيها مسار الإنتاج اكتشاف الخلل فعلياً، لا بحسب اسم قناة الإدخال
وحده. لذلك يصحح 32 حالة Atomic Output موزعة بالتساوي على الحدود الثمانية:

- 8 حالات يظهر فيها Output root بعد فحص الغياب الأولي، وتصنف
  `OUTPUT_ROOT_CHANGED_DURING_COMMIT / PRE_COMMIT_RECHECK`.
- 16 حالة يتغير فيها Parent أوDestination أثناء commit، وتصنف
  `OUTPUT_ROOT_CHANGED_DURING_COMMIT / PRE_COMMIT_RECHECK`.
- 8 حالات يستبدل فيها staging المؤقت بـsymlink، وتصنف
  `PARTIAL_OUTPUT_FORBIDDEN / PRE_COMMIT_RECHECK`.

لا يغيّر هذا التصحيح الأبعاد `8 × 40 × 4` أوعدد الحالات، ولا يحوّل الحزمة
إلى إثبات Runtime. يبقى حد الادعاء
`TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM` كما هو.

ويضيف v3 إلى كل حالة كائن `materialization` إلزامياً وقابلاً للتنفيذ، من دون
أن يكرر نتيجة الرفض المتوقعة. يربط الكائن `handler_id` بعائلة mutation نفسها،
ويحدد بدقة:

- `ingress`: مسار CLI أوDirect API أوserialized admission أوpre-commit hook.
- `artifact` و`field`: الملف/الكائن والحقل المادي اللذان يتغيران فعلياً.
- `action` و`timing`: العملية وموضعها في مسار الإنتاج.
- `resign_policy`: هل تبقى المصادقة قديمة عمداً، أم يعاد التوقيع بسلطة Run أو
  Stage أوSemantic المستقلة.
- `value`: البايتات أوالقيمة الفعلية التي يكتبها handler، أو`null` للحذف.

ولهذا لم تعد `mutation.value` و`attack_shape` أوصافاً افتراضية مختلفة بين
القنوات؛ بل هما إسقاط وصفي للعمل نفسه الذي ينفذه production adapter. الفرق
بين القنوات موثق في `ingress` و`timing`، مع استثناءات حقيقية مثل حذف staging
في variant serialized من output commit، أوتغيير request path إلى`None` في
مساري CLI وDirect API لعائلتي missing authority.

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

لتشغيل المنفذ الإنتاجي المطابق لعقد الـHarness، استخدم:

```bash
python tests/ku_bo_011_harness.py \
  --strict-target-adapter \
  --adapter kubo.ku_bo_011_adapter:production_adapter
```

لا يمرر الـHarness `expected` أوحد الادعاء إلى الـAdapter، لكنه يمرر
`materialization` كي يطبق handler المعلن على artifact حقيقي. يجب أن تكون نتيجة
الرفض مستخرجة من استثناء الإنتاج `failure_code/failure_phase`، ومن دون أي كتابة
باقية في Output root أوcase surface. الوضع الصارم يفشل برمز خروج `2` إذا لم
يُقدم Adapter؛ لذلك لا يمكن تمرير الحزمة باعتبارها دليلاً على تنفيذ KU-BO-011
بينما هي مواصفات فقط.

## حدود الادعاء

- `Stage Binding v1.0` الحالي يثبت سلامة البايتات فقط؛ لا يثبت التطابق
  الدلالي مع run/cohort/window.
- يجب أن يضيف KU-BO-011 semantic admission موثقاً وألا يقلب ادعاء v1 القديم
  إلى `true` بلا عقد جديد أوإصدار Schema جديد.
- `KU-BO-008-D01` يبقى `OPEN`.
- Benchmark غير المتوافق، المقام الخماسي، Full Market، July legacy claims،
  Backtest، Forecast، Probability، وRecommendation تظل ممنوعة.
