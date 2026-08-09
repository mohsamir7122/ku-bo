# الحالة الحالية لـData Foundation Pilot

تاريخ اللقطة: `2026-08-09`

المرحلة الأساسية:

```text
build/data-foundation-v0.2
```

المرحلة المتراكمة الحالية:

```text
build/official-identity-calendar-v0.2
```

قاعدة المرحلة المتراكمة:

```text
build/data-foundation-v0.2@5d64510f5fa442f1cdb832553bc2c2e9917a7a06
```

## ما أصبح موجودًا في طبقة Price History

- فصل Pilot Identity Seed عن Vendor Symbol Mapping.
- حصر Pilot في NBK وKFH وMABANEE وZAIN وHUMANSOFT.
- إنشاء Workspace لملفات User Export المصرح بها.
- التحقق من Collection Manifest وSHA-256 والتوقيت والوحدة وPrice Basis.
- تحليل Investing CSV مباشرة من دون توليد HTML وسيط.
- إنتاج `normalized/research_price_history.csv` بعقد مستقل عن Official Complete `daily_eod`.
- إنتاج Data Quality Report وEvidence Manifest وSource Observation.
- إضافة CLI مستقل باسم `kubo-data-foundation`.

## ما أضيف في مرحلة Official Identity and Calendar

- Workspace منفصلة لخمس Official Boursa Artifacts.
- Parser لجدول Security Code وISIN الرسمي.
- Parser لجدول Listed Companies بعد Client Rendering.
- مصالحة `security_code` و`ISIN` و`Ticker` والاسم عبر مصدرين رسميين.
- حفظ Primary وSupporting Evidence Hashes لكل Security Master row.
- منع مساواة Listing Date بتاريخ صلاحية الهوية.
- وسم الهوية الناتجة صراحةً بـ`CURRENT_SNAPSHOT_ONLY`.
- Parser لصفحة Market Holidays لسنة واحدة.
- Parser لـSunday–Thursday من صفحة Contact الرسمية.
- Parser لـSession Regime الساري من 12 أكتوبر 2025.
- بناء صف لكل يوم مدني في سنة 2026 داخل `trading_calendar.csv`.
- إضافة Schemas وتقارير واختبارات Unit وEnd-to-End.

## أقصى حالة ممكنة للمرحلة الحالية

عند وضع Official Artifacts صحيحة ومراجعة:

```text
CURRENT_IDENTITY_AND_CALENDAR_READY
```

هذه الحالة تعني:

- Current Official Identity للأسهم الخمسة اجتازت المصالحة.
- Trading Calendar لسنة 2026 اجتاز التحقق.

ولا تعني:

- Historical Point-in-Time Universe جاهزة.
- Security Status History جاهزة.
- Corporate Actions جاهزة.
- Benchmark جاهز.
- Official Complete EOD جاهز.
- Backtest أوForecast أصبح مسموحًا.

## البيانات غير المرفوعة إلى GitHub

لا يحتوي الفرع على:

- Real Market CSV.
- Official HTML captures فعلية.
- Browser sessions أوCookies.
- Credentials أوTokens.
- Drive identifiers.

جميع ملفات Runtime وRaw Evidence تبقى خارج Git.

## بوابات المرحلة التالية

```text
HISTORICAL_IDENTITY_AND_RENAMES
SECURITY_STATUS_HISTORY
CORPORATE_ACTION_LEDGER
BENCHMARK_HISTORY
OFFICIAL_COMPLETE_DAILY_EOD
```

ولا يسمح هذا الفرع بـForecast أوProbability أوRecommendation أوAccuracy أوReal Backtest.

## معيار القبول

المرجع الوحيد لقبول الكود هو GitHub Actions على أحدث Head للـPull Request، وتشمل Compile، Full Unit/Adversarial Suite، Official Parser and Materialization Tests، Synthetic Smoke Check، Secret Guard، وبناء Wheel وتشغيل أوامر CLI بعد تثبيته.
