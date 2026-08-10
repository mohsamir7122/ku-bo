# Data Foundation Pilot v0.2

## الهدف

هذه المرحلة تبني طبقة Price History بحثية قابلة للتدقيق لخمس أوراق مالية فقط:

- NBK
- KFH
- MABANEE
- ZAIN
- HUMANSOFT

لا تهدف المرحلة إلى تشغيل Forecast أوBacktest أوFull-Market Scan. الهدف هو حفظ User Exports المصرح بها، وربطها ببصمات وVendor Mappings واضحة، ثم إنتاج Dataset بحثية لا تدّعي أنها Official Complete EOD.

## الفصل بين الهوية وVendor Mapping

يوجد عقدان منفصلان:

```text
config/pilot/security_master_seed.json
config/pilot/vendor_symbol_mappings.json
```

`security_master_seed.json` يحتوي Candidate Identity فقط. جميع صفوفه الحالية `UNVERIFIED_SEED` ولا تحمل Raw Official Artifact أوEffective Dates؛ لذلك لا تثبت الهوية الرسمية.

`vendor_symbol_mappings.json` يربط Candidate Security بـInvesting route. هذا الربط لا يستطيع ترقية نفسه إلى Official Identity، حتى عند نجاح Price Import.

## CLI المرحلة

فحص إعداد Pilot:

```bash
kubo-data-foundation --project-root . validate-pilot-config
```

إنشاء Workspace:

```bash
kubo-data-foundation --project-root . prepare-price-collection \
  --output-root runtime/price_collection/pilot-001 \
  --downloaded-by "authorized-user"
```

استيراد الملفات:

```bash
kubo-data-foundation --project-root . import-user-price-exports \
  --input-dir runtime/price_collection/pilot-001/raw_exports/investing \
  --output-root runtime/data_foundation/pilot-001 \
  --observed-at 2026-08-09T12:00:00+03:00
```

فحص Dataset مستقلة:

```bash
kubo-data-foundation validate-research-price-history \
  --path runtime/data_foundation/pilot-001/normalized/research_price_history.csv \
  --manifest runtime/data_foundation/pilot-001/manifest.json
```

## المخرجات

```text
runtime/data_foundation/<run_id>/
  raw/
    <TICKER>.investing_export.csv
  normalized/
    research_price_history.csv
  reports/
    data_quality_report.json
    user_export_import_report.json
  manifest.json
  source_observations.json
  price_collection_manifest.csv
```

## عقد Research Price History

الحقول هي:

```text
trade_date
security_code
ticker
open
high
low
close
volume
change_percent
source_id
source_url
raw_sha256
capture_mode
price_basis
currency
unit
corporate_action_status
```

هذا العقد منفصل عن `daily_eod` الكامل. لا يحتوي عمدًا على حقول غير متاحة في User Export، مثل:

```text
value_traded_kwd
trade_count
reference_price_fils
trading_status
```

لا يجوز اشتقاق هذه الحقول من Close وVolume ثم وصفها بأنها Official.

## حالات التشغيل

- `RESEARCH_PRICE_HISTORY_READY`: كل ملفات Price History المحددة اجتازت Manifest وHash وOHLC وDate وUnit checks.
- `BLOCKED_OFFICIAL_IDENTITY`: Price History جاهزة بحثيًا، لكن Official Identity Artifact وEffective-Dated Bindings ما زالت غائبة. هذه هي الحالة المتوقعة حاليًا حتى استكمال المرحلة التالية.
- `PARTIAL`: بعض الأسهم استوردت وبعضها مفقود أومرفوض.
- `BLOCKED`: لم توجد Dataset قابلة للاستخدام.
- `FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED`: طُلب `all_market` من Seed Mapping لا تثبت الكون الكامل.

## قواعد لا يجوز تجاوزها

- لا Synthetic Price Rows.
- لا Forward Fill.
- لا تحويل Missing Session إلى Zero Volume.
- لا خلط RAW وADJUSTED داخل Series واحدة.
- لا خلط `fils` و`KWD` داخل Series واحدة.
- لا قبول ملف بلا SHA-256 مطابق.
- لا قبول Manifest بلا `review_status=ACCEPTED`.
- لا استخدام Vendor Mapping باعتبارها Official Identity.
- لا Backtest قبل Trading Calendar وSecurity Status History وCorporate Actions وBenchmark.
- لا Forecast أوProbability أوRecommendation أوAccuracy في هذه المرحلة.

## Definition of Done للمرحلة الحالية

تنجح طبقة Price History عندما:

1. توجد الملفات الخمسة المصرح بها.
2. تتطابق SHA-256 مع Manifest.
3. تتطابق Identity fields مع Pilot Catalogs من دون تحويل Seed إلى Official Evidence.
4. تتطابق Date ranges وRow counts مع الملفات.
5. تجتاز OHLC constraints وChange-percent reconciliation.
6. تنتج Dataset قابلة لإعادة البناء من Raw bytes.
7. يظل تقرير الحالة صريحًا بشأن بوابة Official Identity وبقية Data Foundation.

المرحلة التالية بعد ذلك هي Official Identity + Trading Calendar، وليس Model Training.
