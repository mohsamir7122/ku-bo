# تشغيل شبكة المصادر

## 1. تثبيت وفحص الإعداد

```bash
python3 -m pip install -e .
kubo validate-config
kubo validate-source-network
```

## 2. تعريف التشغيل

حدد المنتج والأفق ووقت القرار بتوقيت الكويت ونطاق البحث وعضوية الكون والميزانية قبل جمع أي Finding. أنشئ `universe.json` لكل Scope مع ربط effective-dated لكل Security Code في تاريخ القرار؛ لا تغير Cutoff أوهوية الكون بعد ظهور نتيجة لاحقة.

أنشئ مجلد تشغيل يحتوي على `raw/` والملفات الأربعة المعرفة في [عقود البيانات](DATA_CONTRACTS_AR.md).

يمكن بدء Capture آمن من Plan:

```bash
kubo capture \
  --plan examples/capture_plan.json \
  --fixture-root examples/synthetic_source_network_run \
  --output-root runtime/capture
```

Public HTTP يستخدم `public_http` داخل Plan ولا يرسل Cookies أوAuthorization. ناتج الجمع Raw فقط ويحتاج Parser validation قبل إنشاء Finding.

لا توفر النسخة `0.1.0` Parsers حية خاصة بالمواقع. يجب أن تبني طبقة Parser/QA منفصلة، تحفظ `fact_type` والهوية والتوقيت والأصل، وتمنع Parser Drift قبل أن تكتب `findings.jsonl`.

## 3. جمع أدوار المصدر

استخدم `config/research_policies.json` لمعرفة النصاب. حاول مصادر مستقلة لكل دور، وسجل المحاولات الفاشلة والصفرية كما تسجل الناجحة. لا تتجاوز CAPTCHA أو Paywall أو Rate Limit ولا تستعمل Endpoint محميًا أو غير مصرح.

احفظ الصفحة أو التنزيل أو Export أولًا، ثم احسب SHA-256 وسجله في Manifest. لا تنشئ Finding من نص في الذاكرة من دون Artifact خام.

## 4. التطبيع

طبع الهوية إلى `security_code` الرقمي، واحتفظ بالTicker كAlias. افصل Publication وAvailability وObservation. صنف الإشارة وحدد Origin حتى يجمع النظام النسخ المعاد نشرها.

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

إذا أعاد المدقق `BLOCKED`، أصلح العقد أو الدليل ولا تتابع. إذا أعاد `PARTIAL`، اذكر الأدوار الناقصة وأخرج Watch/Abstain فقط بحسب المنتج. إذا أعاد `PASS`، راجع Reason Codes والتغطية قبل عرض الرتبة.

لإخراج تقرير حسب الطلب:

```bash
kubo run-request \
  --request examples/analysis_request.json \
  --network-run /absolute/path/to/research_run \
  --output runtime/report.md
```

طلب `FULL_MARKET` لا يقبل Candidate Set، وطلب سهم مسمى لا يقبل Security غير موجود في الحزمة.

## 6. فحص الوصول الحي

```bash
kubo validate-live-probe \
  --probe research/live_source_probe_2026-08-07.json
```

هذا الأمر لا يجمع Market Evidence ولا يثبت Coverage. وظيفته التأكد من أن إيصال اختبار الوصول منضبط ولا ينسب إليه أكثر مما يثبت.

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

## 9. السجل المستقبلي

أضف إلى `run-request`:

```bash
--research-ledger-dir runtime/ledger --ledger-id kuwait-research-v1
```

ثم تحقق:

```bash
kubo verify-research-ledger --ledger-dir runtime/ledger --ledger-id kuwait-research-v1
```

Outcomes تضاف فقط بعد القرار بأمر `append-research-outcome` ومع Evidence hashes. لا تُضاف إلى Decision report. لإنشاء HMAC seal، مرر المفتاح في `KUBO_LEDGER_HMAC_KEY` بصيغة `hex:` أو`base64:` وقت التشغيل، واستخدم `seal-research-ledger --key-id ...`. لا تمرر المفتاح كـCLI argument.
