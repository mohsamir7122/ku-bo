# الحالة الحالية لـData Foundation Pilot

تاريخ اللقطة: `2026-08-09`

سلسلة الفروع المتراكمة:

```text
build/data-foundation-v0.2
  └── build/official-identity-calendar-v0.2
        └── build/security-status-corporate-actions-v0.2
```

قاعدة المرحلة الحالية:

```text
build/official-identity-calendar-v0.2@67b5babe0926b94cafd40806dd341a3b25e160e2
```

## ما أصبح موجودًا في طبقة Price History

- فصل Pilot Identity Seed عن Vendor Symbol Mapping.
- حصر Pilot في NBK وKFH وMABANEE وZAIN وHUMANSOFT.
- إنشاء Workspace لملفات User Export المصرح بها.
- التحقق من Collection Manifest وSHA-256 والتوقيت والوحدة وPrice Basis.
- تحليل Investing CSV مباشرة من دون توليد HTML وسيط.
- إنتاج `normalized/research_price_history.csv` بعقد مستقل عن Official Complete `daily_eod`.
- إنتاج Data Quality Report وEvidence Manifest وSource Observation.

## ما أصبح موجودًا في Current Official Identity and Calendar

- مصالحة Security Code وISIN وTicker والاسم عبر مصدرين رسميين.
- حفظ Primary وSupporting Evidence Hashes لكل Security Master row.
- وسم الهوية الناتجة صراحةً بـ`CURRENT_SNAPSHOT_ONLY`.
- بناء صف لكل يوم مدني في سنة 2026 داخل `trading_calendar.csv`.
- فصل Listing Date عن Effective-Dated Identity.

## ما أضيف في مرحلة Security Status and Corporate Actions

- Workspace لصفحات Suspended Companies وDelisted Companies وCorporate Actions.
- Parser يقبل Empty Suspended table فقط عند وجود Rendered Headers الصحيحة.
- Current Status row لكل سهم من الأسهم الخمسة.
- فصل `CURRENT_SNAPSHOT_ONLY` عن Historical Status History.
- حفظ Official Delisting Archive وتعارضه مع Current Identity.
- Query/Pagination receipt لصفحة Corporate Actions.
- حفظ كل Market Schedule Rows ثم فصل Pilot Rows بعد مطابقة Security Code وTicker وISIN.
- إنشاء `corporate_action_enrichment_queue.csv` لكل Action تحتاج Official Disclosure.
- إبقاء Action Type وAmount وAdjustment Factor في حالة Pending.
- إضافة Schemas وتقارير واختبارات Unit وEnd-to-End.

## أقصى الحالات الممكنة للمرحلة الحالية

عند نجاح Current Status ووجود Corporate Action rows:

```text
CURRENT_STATUS_AND_CA_SCHEDULE_READY
```

تعني أن Official Schedule Dates جُمعت، ولا تعني أن Action Type أوAmount أوAdjustment Factor معروف.

عند نجاح Current Status وثبوت Zero Result داخل Query Window:

```text
CURRENT_STATUS_AND_CA_ZERO_RESULT_READY
```

تعني Zero Result للفترة المحددة فقط.

## ما لا تزال الحالات السابقة لا تعنيه

- Historical suspension and resumption intervals جاهزة.
- Historical Point-in-Time Universe جاهزة.
- Corporate Action factor ledger جاهزة عندما توجد Action rows.
- Benchmark جاهز.
- Official Complete EOD جاهز.
- Backtest أوForecast مسموح.

## البيانات غير المرفوعة إلى GitHub

لا يحتوي الفرع على:

- Real Market CSV.
- Official rendered HTML captures فعلية.
- Browser sessions أوCookies.
- Credentials أوTokens.
- Drive identifiers.

جميع ملفات Runtime وRaw Evidence تبقى خارج Git.

## البوابات التالية

```text
HISTORICAL_SUSPENSION_AND_RESUMPTION_NOTICES
CORPORATE_ACTION_DISCLOSURE_ENRICHMENT
CORPORATE_ACTION_ADJUSTMENT_FACTORS
BENCHMARK_HISTORY
OFFICIAL_COMPLETE_DAILY_EOD
```

ولا يسمح هذا الفرع بـForecast أوProbability أوRecommendation أوAccuracy أوReal Backtest.

## معيار القبول

المرجع الوحيد لقبول الكود هو GitHub Actions على أحدث Head للـPull Request، وتشمل Compile، Full Unit/Adversarial Suite، Official Identity/Calendar Gates، Status/Corporate Parsers and Materialization Gates، Synthetic Smoke Check، Secret Guard، وبناء Wheel وتشغيل أوامر CLI بعد تثبيته.
