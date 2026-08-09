# Authorized Investing user exports

هذا المجلد للتوثيق فقط، ولا يحتوي بيانات سوق حقيقية أوملفات CSV مولدة.

## المسار الآمن

1. أنشئ Workspace محليًا:

```bash
kubo-data-foundation --project-root . prepare-price-collection \
  --output-root runtime/price_collection/pilot-001 \
  --downloaded-by "authorized-user"
```

2. نزّل CSV المصرح به لكل سهم يدويًا، وضعه باسم Ticker الصحيح داخل:

```text
runtime/price_collection/pilot-001/raw_exports/investing/
```

3. املأ `manifests/price_collection_manifest.csv`، وسجّل SHA-256 والتوقيت والوحدة و`price_basis`، ثم اجعل `review_status=ACCEPTED` فقط بعد المراجعة.

4. استورد الملفات إلى حزمة جديدة غير موجودة أوفارغة:

```bash
kubo-data-foundation --project-root . import-user-price-exports \
  --input-dir runtime/price_collection/pilot-001/raw_exports/investing \
  --output-root runtime/data_foundation/pilot-001 \
  --observed-at 2026-08-09T12:00:00+03:00
```

## حدود الناتج

- يحفظ CSV الأصلي ويحسب بصمته.
- يكتب `normalized/research_price_history.csv`.
- لا يولد HTML وسيطًا.
- لا يختلق `trade_count` أو`value_traded_kwd` أو`reference_price_fils`.
- لا يستخدم Forward Fill ولا يحول Missing Session إلى Zero Volume.
- لا يعتبر Vendor Mapping دليل هوية رسميًا.
- يظل Overall Status هو `BLOCKED_OFFICIAL_IDENTITY` حتى تتوفر هوية رسمية مؤرخة وقابلة للتدقيق.
- لا ينتج Forecast أوProbability أوRecommendation أوAccuracy.

لا تُرفع ملفات الأسعار، Sessions، Cookies، Drive identifiers، أوCredentials إلى GitHub.
