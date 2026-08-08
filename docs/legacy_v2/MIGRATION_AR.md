# الانتقال من النسخة السابقة إلى V2

## ما لم يحدث

- لم تُحذف النسخة السابقة.
- لم تُنقل نتائجها أو نسبها إلى V2.
- لم تتحول بياناتها تلقائيًا إلى Evidence Pack مؤهل.
- لم يُعتبر نجاح اختبارات النسخة السابقة دليل مصدر أو Backtest.

## ما يمكن نقله

يمكن نقل مادة خام أو ملفات منظمة فقط بعد:

1. تحديد مصدرها ورابطها وطريقة الوصول.
2. وجود البايتات الخام الفعلية.
3. حساب SHA-256 والحجم.
4. تسجيل `observed_at` و`provider_as_of` إن وجد.
5. إدخالها في `file_manifest.json`.
6. تحويلها إلى Schema V2.
7. اجتياز Validator الدلالي وDenominator reconciliation.

أي CSV بلا Raw Bytes أو توقيت إتاحة يظل مادة تشخيصية، لا Point-in-Time Evidence.

## خرائط مفاهيمية

- `sources.json` القديم → يعاد تصنيفه إلى Role وAuthority وCapabilities، ولا ينقل Status الحالي.
- `targets.json` القديم → يوزع على 13 Product Contracts بأهداف وجلسات وتكاليف.
- Forecast قديم → `IMPORTED` فقط إذا كان له ختم زمني مستقل؛ وإلا Historical Reconstruction بعلامة واضحة، لا Prospective.
- News/Social قديم → يحتاج Content Hash وعلاقات Original/Repost وتوقيت إتاحة.
- Price CSV قديم → يحتاج Full-universe denominator وStatus rows وCorporate Action status.

## معيار القبول

لا يقبل أي Artifact قديم لأنه «موجود». يقبل فقط إذا أمكن الإجابة بالأدلة عن:

- ما البايتات الأصلية؟
- من المصدر؟
- متى كانت متاحة؟
- لأي ورقة رسمية؟
- ما تغطيتها؟
- هل تشمل الغائب وعدم التداول؟
- هل تغيرت بعد الجمع؟

إن تعذرت الإجابة، يبقى الملف خارج Backtest النهائي.
