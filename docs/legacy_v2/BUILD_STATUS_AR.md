# حالة بناء V2

تاريخ التحقق: 7 أغسطس 2026.

## مكتمل

- Source catalog بعدد 18 تعريفًا ودورًا صريحًا.
- 13 Product Contract للأهداف المطلوبة.
- 10 Method Contract من Baselines إلى Event/Social/Fundamental/Microstructure.
- Raw Manifest مع Hash/size/domain/timestamp validation.
- Capability attestation مرتبطة بأدلة وتغطية وValidator.
- Collection budget وQuery ledger.
- Point-in-time Security Master وStatus history.
- Trading calendar كامل للنافذة.
- Full-universe EOD denominator.
- Market totals reconciliation.
- Disclosure/Corporate Action validation.
- Event timing, relations, canonicalization, source diversity.
- Feature availability وUnknown-not-zero.
- Coverage-aware heuristic ranker.
- Model Card validation وProbability gate.
- Authorized execution assessment.
- Decision gate يمنع High Buy بلا Prospective model وتنفيذ.
- Forecast append-only ledger وHash chain وSeal.
- Stop gates.
- Evaluator يعيد حساب العوائد والتكاليف وNon-fill وMetrics.
- CLI وSmoke check.
- وثائق التشغيل والتدقيق والمقارنة والهجرة.

## التحقق المنفذ

- Unit/adversarial tests: 45/45 PASS.
- Python compileall: PASS.
- Integration smoke check: PASS.
- Config catalog: 18 sources, 13 products, 10 methods.
- Synthetic evidence pack: PASS للعقود فقط.
- Daily plan with synthetic pack: `DATA_READY_MODEL_UNBOUND`.
- Opening plan without licensed feed: `EXECUTION_BLOCKED`.
- Plan without pack: `EVIDENCE_REQUIRED`.

## غير مكتمل عمدًا

- لا توجد حزمة سوق كويتي تاريخية كاملة في هذا الإصدار.
- لا توجد مراقبة مصدر حية طويلة الأجل.
- لا يوجد مزود Intraday مرخص مهيأ.
- Issuer IR registry يحتاج قائمة Domains رسمية شركةً شركة.
- لا يوجد Arabic Kuwait event corpus مشروح.
- لا يوجد Model training implementation؛ العقد يسبق التدريب.
- لا يوجد Prospective paper ledger لمدة 120 جلسة.
- لا يوجد Backtest نهائي أو نسبة دقة جديدة.

## القرار التشغيلي

الإصدار صالح ليكون بوابة جودة وبنية بحث، وليس صالحًا بعد لإصدار توصيات مالية. أول خطوة بيانات صحيحة هي بناء Pack تاريخي محدود قابل للتدقيق، ثم توسيعه، لا تشغيل نموذج على ملفات غير مثبتة.

## ترتيب العمل التالي

1. إعداد IR Registry رسمي لكل شركة مدرجة.
2. تنفيذ Collector ضمن ميزانية وتوقف آمن على نافذة Pilot قصيرة.
3. بناء Master/Status/Calendar وإثبات Denominator.
4. جمع EOD والإجماليات ومصالحتها.
5. جمع الإفصاحات والإجراءات مع Query Ledger.
6. تشغيل Event extraction وعينة QA بشرية.
7. تجميد Trial لأول Baseline.
8. Walk-forward تشخيصي، ثم Prospective paper forecasts.
9. التوسع إلى Intraday فقط بعد تعاقد Feed مصرح به.
