# HUMANSOFT Event-by-Factor Point-in-Time Panel v1

## الغرض

هذه الطبقة تبني عقدًا صارمًا لدراسة كل Event Cluster خاص بسهم `HUMANSOFT` خلال
عشرين جلسة تداول قبل الحدث وعشرين جلسة بعده، مع ربط كل Factor بالبيانات التي
كانت متاحة فعلًا عند الحدث. لا تنشئ هذه الطبقة Forecast أو Probability أو
Buy/Sell recommendation، ولا تستورد أي Score قديم من المستودعات السابقة.

## موضع التنفيذ

- المستودع القانوني الوحيد: `mohsamir7122/ku-bo`.
- المنتج: `HUMANSOFT_EVENT_FACTOR_PANEL_V1`.
- النافذة المجمدة: 20 جلسة قبل الحدث و20 جلسة بعده.
- الدخول التشخيصي: أول إغلاق مؤهل بعد الحدث.
- السعر المقبول: `TOTAL_RETURN_INDEX` فقط.
- Benchmark: Market وSector Point-in-Time إلزاميان.
- Corporate Actions: بيانات معدلة أو Receipt رسمي يثبت عدم وجود Action.
- Missing data: لا تتحول إلى صفر؛ تبقى `UNKNOWN_NOT_OBSERVED` أو `BLOCKED`.

## ما أُضيف

- `src/kubo/event_factor_common.py`: ثوابت وعقود تحقق مشتركة.
- `src/kubo/event_factor_packet.py`: التحقق الصارم من Event وFactor snapshot
  والجلسات وEvidence receipts.
- `src/kubo/event_factor_study.py`: حسابات داخلية للدراسة مع حجبها في المخرج
  العام ما دام Final authority غير موجود.
- `src/kubo/event_factor_audit.py`: تدقيق Aggregate لسجل القرارات القديم.
- `src/kubo/event_factor_panel.py`: واجهة CLI وإعادة تصدير API.
- `schemas/event-factor-panel.schema.json`: عقد الإدخال.
- `schemas/event-factor-panel-result.schema.json`: عقد `STOP_EVENT_STUDY`.
- `config/pilot/humansoft_factor_registry.json`: فهرس Factor Registry.
- `config/pilot/humansoft_factor_registry/*.json`: Shards حسب الفئة.
- اختباران منفصلان للعقد وللتدقيق، مع Fixture مشتركة.

## Factor Registry

يغطي السجل تسعة وعشرين Factor أو Gate، موزعة على Market وExecution وRisk
وValuation وFundamental وGrowth وIncome وEvent وGovernance وExpectations وSocial
وEducation. من أهم العوامل الخاصة بهيومن سوفت:

- Student Count Growth.
- New Student Intake.
- Revenue per Student.
- Scholarship versus Private-Pay Mix.
- Capacity Utilization.
- Accreditation and Program Expansion.
- Receivables Collection.
- Capital Allocation.

كل عامل يسجل Legacy lineage، البيانات المطلوبة، Point-in-Time rule، دوره قبل
الحدث وبعده، حالة البيانات الحالية، وما الذي يحدث عند النقص.

## حدود الاستفادة من المستودعات القديمة

- `Research`: لا يُنقل منه Score أو Backtest؛ التعريفات فقط قد تساعد في Rewrite.
- `Factor9-saudiai`: Architecture وNegative controls فقط؛ الحدود السعودية ليست
  قابلة للنقل إلى الكويت.
- `-Saudi-Arabia-Ai`: لا نقل مباشر إلى الكويت.
- `KW`: Salvage انتقائي للعقود، دون Legacy scores.
- `KW2`: يحتاج أرشفة الفرع غير المدمج أولًا.
- `AI-Mincy`: مرجع تشخيصي؛ Collector readiness لا يساوي Model readiness.
- `Social-media`: Discovery فقط، ولا يثبت Claims مالية.
- `ku-bo`: التنفيذ الرسمي Fail-Closed.

## تدقيق سجل HUMANSOFT المتاح

أُعيد حساب ملف `predictions_sealed.csv` بصورة Aggregate فقط، باستخدام العائد
النسبي بعد عشرين جلسة وتصنيف مادي عند موجب أو سالب أربعة في المئة.

النتيجة على 23 قرارًا:

- Raw concordance: 15 من 23، أي 65.22%.
- Always-neutral baseline: 17 من 23، أي 73.91%.
- Balanced Accuracy: 47.71%.
- Macro F1: 50.49%.
- Directional signals: ست إشارات.
- Material directional hits: إشارتان من ست، أي 33.33%.
- Sign-only directional hits: أربع من ست، أي 66.67%.
- Pearson score/return: نحو 0.676.
- Spearman score/return: نحو 0.683.

هذه ليست Prospective Accuracy، لأن Protocol نفسه Retrospective، وأفق النموذج
الأصلي خمس جلسات بينما التدقيق يستخدم عشرين جلسة، كما أن نوافذ النتائج متداخلة.
لذلك لا يحسب النظام P-value أو Probability ولا يسمح بادعاء Accuracy إنتاجية.

## لماذا تتوقف دراسة جميع الإفصاحات؟

المسح الكامل لكل Event Cluster يحتاج، لكل حدث:

- Lifetime official disclosure archive مع Pagination receipts.
- Exact event available-at timestamp.
- Corporate-actions ledger كامل.
- Total-return history موثقة للسهم.
- Market وSector benchmark history Point-in-Time.
- Factor snapshots منشورة أو قابلة لإعادة الإنتاج عند الحدث.
- Independent final authority receipt يربط البايتات والـParser والنتيجة.

هذه الحزمة غير مكتملة حاليًا؛ لذلك المخرج العام دائمًا `STOP_EVENT_STUDY`،
وتبقى `metrics = null` و`accuracy_claim_allowed = false` حتى وجود Authority
حقيقية. Caller-provided hashes أو Receipt مصطنعة لا تستطيع تجاوز هذا التوقف.

## قواعد منع التسرب

- أي Factor يصبح متاحًا بعد `event.available_at` يُرفض.
- Factor IDs التي تشير إلى Future أو Outcome أو Target أو Post-event ممنوعة داخل
  Pre-event snapshot.
- `PRICE_REACTION` Post-event diagnostic فقط ول٧ يدخل توقعًا سابقًا للحدث.
- Market وSector benchmarks ليست اختيارية.
- Session-level evidence hashes يجب أن تطابق Top-level receipts.
- Unadjusted price history تُرفض.
- Duplicate Event documents يجب دمجها في Canonical Event Cluster واحد.

## الاختبارات المحلية

شُغّل:

```bash
PYTHONPATH=src python -m unittest discover -s tests \
  -p 'test_event_factor_panel_*.py' -v
python -m compileall -q src tests
```

النتيجة: 18 من 18 PASS.

الاختبارات تغطي Valid 20/20 packet، JSON Schemas، Future-factor rejection،
Unadjusted-price rejection، Benchmark and receipt binding، Wrong-window rejection،
STOP metrics withholding، Mutation resistance، Registry uniqueness، Duplicate
decision rejection، Fractional-horizon rejection، Aggregate-only CSV output،
Always-neutral baseline، وConfusion-matrix recomputation، ورفض Duplicate documents،
Credential-bearing URLs، وFactor timestamps التي تتجاوز Snapshot، وإنشاء Packet قبل اكتمال
Post-event observations.

## ما لا يفعله هذا التغيير

- لا يدمج أي مستودع قديم.
- لا يرفع بيانات خاصة أو Row-level predictions.
- لا يشغل Collector حيًا.
- لا يدرب Model.
- لا يصدر Probability أو Recommendation أو Trade instruction.
- لا يغيّر Forty-Session Replay القائم.
- لا يتجاوز Rights أو Source authority أو Production gates.

## القرار البحثي

النتيجة الحالية هي:

`RESEARCH_SIGNAL_ONLY — NOT_PRODUCTION_VALIDATED`

الـScore المستمر قد يحمل Ranking signal أوليًا، لكن Thresholds الحالية لا تتفوق
على Always-neutral baseline في Accuracy الخام. فتح القياس الكامل مشروط بإكمال
Official disclosure archive وCorporate Actions وBenchmarks وPIT snapshots ثم
Walk-forward validation مستقل مع Purge وEmbargo.
