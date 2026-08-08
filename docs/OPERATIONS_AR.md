# تشغيل شبكة المصادر

## 1. تثبيت وفحص الإعداد

```bash
python3 -m pip install -e .
kubo validate-config
kubo validate-source-network
```

## 2. تعريف التشغيل

حدد المنتج والأفق ووقت القرار بتوقيت الكويت ونطاق البحث وعضوية الكون والميزانية قبل جمع أي Finding. أنشئ `universe.json` لكل Scope مع ربط effective-dated لكل Security Code في تاريخ القرار؛ لا تغير Cutoff أوهوية الكون بعد ظهور نتيجة لاحقة.

أنشئ مجلد تشغيل يحتوي على `raw/` والملفات الخمسة: `research_run.json` و`universe.json` و`manifest.json` و`source_observations.json` و`findings.jsonl`.

يمكن بدء Capture آمن من Plan:

```bash
kubo capture \
  --plan examples/capture_plan.json \
  --fixture-root examples/synthetic_source_network_run \
  --output-root runtime/capture
```

Public HTTP يستخدم `public_http` داخل Plan ولا يرسل Cookies أوAuthorization. ناتج الجمع Raw فقط ويحتاج Parser validation قبل إنشاء Finding.

قبل أي Connector أوكتابة، ترفض الأداة الخطة إذا تجاوزت 32 مهمة، أو128 MiB لمجموع `max_bytes`، أو300 ثانية لمجموع `timeout_seconds`. جزّئ العمل إلى تشغيلات مستقلة بدل محاولة رفع الحدود داخل JSON.

توفر النسخة `0.1.0` مسار Parser/QA ضيقًا لمصدرين فقط: هوية Boursa الرسمية وجدول Investing التاريخي. بعد Capture وإنشاء `parser-plan.json` مطابق للعقد، شغّل:

```bash
kubo materialize-parser-run \
  --capture-root /absolute/path/to/capture \
  --parser-plan /absolute/path/to/parser-plan.json
```

يتحقق الأمر من الـHashes والتوقيت والنطاق، ويصالح Security Code/Ticker/ISIN، ويكتب حزمة التشغيل ثم يشغل مدقق الشبكة. لا يفسر أخبارًا أومحفزات، ولا يكمل Quorum تلقائيًا. Fixtures الاختبار مولدة وليست قبولًا حيًا؛ راجع `config/source_capabilities.json` قبل افتراض وجود Parser أوConnector تشغيلي لأي مصدر.

## 3. جمع أدوار المصدر

استخدم `config/research_policies.json` لمعرفة النصاب. حاول مصادر مستقلة لكل دور، وسجل المحاولات الفاشلة والصفرية كما تسجل الناجحة. لا تتجاوز CAPTCHA أو Paywall أو Rate Limit ولا تستعمل Endpoint محميًا أو غير مصرح.

احفظ الصفحة أو التنزيل أو Export أولًا، ثم احسب SHA-256 وسجله في Manifest. لا تنشئ Finding من نص في الذاكرة من دون Artifact خام.

لا تعتبر `runtime_authority` أوActivation أوEntitlement مكتوبًا داخل Packet تفويضًا. عند مساهمة مصدر Disabled أوRuntime-bound أوLicensed، يتطلب `0.1.0` سجل ثقة خارجيًا منفصلًا عن Packet ومصادقًا بـ`HMAC-SHA256`، مع مفتاح وKey ID من بيئة التشغيل. يجب أن يربط السجل المصدر بالحساب/Subject والنطاق وSecurity codes وActivation/Entitlement وفترة الصلاحية؛ غيابه أوفشل المصادقة أوالمطابقة يحجب المصدر قبل قبول مساهمته. لا تحفظ المفتاح أوالسجل التشغيلي داخل Packet أوالمستودع.

ضع السجل في مسار محمي خارج مجلد `research_run`، واضبط المفتاح بطول 32 بايت على الأقل بصيغة `hex:` أو`base64:` ومعرّفه المطابق، ثم مرر المسار صراحة:

```bash
export KUBO_RUNTIME_TRUST_HMAC_KEY='hex:<64-or-more-hex-digits>'
export KUBO_RUNTIME_TRUST_HMAC_KEY_ID='<configured-key-id>'

kubo validate-network-run \
  --product next_session_rank \
  --run /absolute/path/to/research_run \
  --runtime-trust-registry /secure/path/runtime-trust-registry.json
```

الخيار نفسه متاح في `plan` و`run-request`. لا تحتاجه الحزمة التي لا يساهم فيها مصدر حساس، ولا تمرر قيمة المفتاح كـCLI argument.

## 4. التطبيع

طبع الهوية إلى `security_code` الرقمي، واحتفظ بالTicker كAlias. أنشئ Binding مؤرخًا لكل Security مغطى، واجعل `membership_as_of` في تاريخ `decision_at` نفسه بتوقيت الكويت ومن مصدر Official/Licensed مساهم. افصل Publication وAvailability وObservation. صنف الإشارة وحدد Origin حتى يجمع النظام النسخ المعاد نشرها. لكل Finding، عيّن `fact_type` مسموحًا للمصدر واجعل `source_url` مطابقًا حرفيًا لعنوان الـArtifact المشار إليه.

## 5. التحقق والتخطيط

```bash
kubo validate-network-run \
  --product next_session_rank \
  --run /absolute/path/to/research_run

kubo plan \
  --mode research_network \
  --product next_session_rank \
  --network-run /absolute/path/to/research_run \
  --top-k 5
```

أضف `--runtime-trust-registry /secure/path/runtime-trust-registry.json` إلى الأمر عند مساهمة مصدر حساس، مع متغيري البيئة المذكورين أعلاه.

إذا أعاد المدقق `BLOCKED`، أصلح العقد أو الدليل ولا تتابع. إذا أعاد `PARTIAL`، اذكر الأدوار الناقصة وأخرج Watch/Abstain فقط بحسب المنتج. إذا أعاد `PASS`، راجع Reason Codes والتغطية قبل عرض الرتبة.

لإخراج تقرير حسب الطلب:

```bash
kubo run-request \
  --request examples/analysis_request.json \
  --network-run /absolute/path/to/research_run \
  --output runtime/report.md
```

طلب `FULL_MARKET` لا يقبل Candidate Set، وطلب سهم مسمى لا يقبل Security غير موجود في الحزمة.

إذا تعذرت بورصة الكويت، لا تتابع إلا إذا بقي دليل هوية رسمي بديل وحديث، مثل Receipt صالح من CMA/iFSAH ضمن عقد المصدر. اكتمال Quorum الخبري أوالسعري وحده لا يعوض فشل الهوية.

## 6. فحص الوصول الحي

```bash
kubo validate-live-probe \
  --probe /absolute/path/to/fresh_access_probe.json
```

يجب أن يكون Probe بإصدار `3.1-access-probe`، صالحًا لمدة لا تتجاوز 24 ساعة، وأن يربط كل حالة `AVAILABLE` أو`PARTIAL` بملف داخل `raw/` وحجمه وSHA-256. هذا الأمر لا يجمع Market Evidence ولا يثبت Coverage؛ وملاحظات `research/manual_access_notes_2026-08-07.json` تاريخية ولا يقبلها المدقق كإيصال حي.

## 7. مسار Forecast الصارم

عند الحاجة إلى Probability أو Accuracy، استخدم صراحة:

```bash
kubo plan \
  --mode validated_forecast \
  --product next_session_rank \
  --pack /absolute/path/to/evidence_pack \
  --model-card /absolute/path/to/model_card.json
```

لا تحول Rank خرج من الشبكة إلى Probability داخل Report أو خارجه.

## 8. التحقق الشامل

```bash
PYTHONPATH=src python3 -m compileall -q src tests scripts
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 scripts/smoke_check.py
```

يشغّل CI المجموعة على Python 3.11 و3.12 و3.13 و3.14. لا تعتمد رقم اختبارات من وثيقة ثابتة؛ راجع نتيجة GitHub Actions للـCommit المقصود.

## 9. السجل المستقبلي

أضف إلى `run-request`:

```bash
--research-ledger-dir runtime/ledger --ledger-id kuwait-research-v1
```

ثم تحقق:

```bash
kubo verify-research-ledger --ledger-dir runtime/ledger --ledger-id kuwait-research-v1
```

Outcomes تضاف فقط بعد القرار ولا تُضاف إلى Decision report. أنشئ لكل Outcome مجلدًا داخل Ledger root يحوي `manifest.json` وقائمة `raw/` مطابقة تمامًا للManifest، ثم مرر Payload قياس صارم والحزمة نفسها:

```bash
kubo append-research-outcome \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1 \
  --outcome-id outcome-101-next \
  --decision-id synthetic-demo-request \
  --observed-at 2026-08-08T14:00:00+03:00 \
  --payload runtime/outcome-101-next.json \
  --evidence-pack outcome_evidence/outcome-101-next
```

يُحل مسار `--evidence-pack` النسبي من داخل `--ledger-dir`. لا يقبل الأمر Evidence hash من المتصل؛ بل يشتق بصمة Packet وHashes الـArtifacts من البايتات، ويربط Identity القرار والسهم والتوقيت، ثم يعيد `verify` و`seal` قراءة Manifest وRaw وإعادة حسابها. يجب أن يحتوي Payload الحقول الصارمة `schema_version`, `security_code`, `metric_id`, `value`, `unit`, `measurement_start_at`, `measurement_end_at`, `method_id`, و`notes`. لا تكفي حزمة سليمة لإثبات سلامة Parser أومنهج القياس؛ راجعهما خارج السجل كذلك.

لإنشاء HMAC seal، مرر المفتاح في `KUBO_LEDGER_HMAC_KEY` بصيغة `hex:` أو`base64:` وقت التشغيل، ولا تمرره كـCLI argument:

```bash
kubo seal-research-ledger \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1 \
  --seal runtime/ledger/research-ledger.seal.json \
  --key-id operations-2026

kubo verify-research-ledger \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1 \
  --seal runtime/ledger/research-ledger.seal.json \
  --expected-key-id operations-2026
```

عند وجود مفتاح Runtime يرفض التحقق Seal غير `HMAC-SHA256` أوKey ID غير المتوقع. يربط Decision كذلك بصمة كود الحزمة المنفذة فعليًا، وبصمة Config/Research مستقلة من `--project-root`.
