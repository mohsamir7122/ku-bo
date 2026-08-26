# تدقيق مصادر التطوير ذات الصلة - نسخة معقمة

هذا سجل Read-only لقرارات الاستفادة من مصادر تطوير سابقة. لا ينشر أسماء
مستودعات خاصة أو فروعًا أو مراجعات أو مواقع ملفات، ولا يمنح إذنًا بالدمج أو
الحذف، ولا يحول أي Dataset أو نتيجة قديمة إلى دليل صالح لـ`KU-BO`.

## الحكم التنفيذي

```text
KU_BO_CANONICAL_ENGINE         KEEP_AND_BUILD
PRIVATE_PREDECESSOR_SOURCE     KEEP_READ_ONLY_SELECTIVE_REFERENCE
LEGACY_KUWAIT_REPOSITORIES     ARCHIVE_SELECTIVE_SALVAGE
RESEARCH_PROTOTYPES            NO_SCORES_OR_BACKTEST_SALVAGE
OUT_OF_SCOPE_PROJECTS          LEAVE_UNCHANGED
```

لا يجوز نسخ Scores أوProbabilities أوRecommendations أوBacktest outputs إلى
`KU-BO`. النقل المقبول هو إعادة تنفيذ وظيفة مستخدم محددة أو اختبار سلبي داخل
الحزمة الأساسية، مع اختبارات جديدة وسقف تشغيلي صريح.

## المحرك الأساسي

`KU-BO` هو الأصل الوحيد للبناء. تبقى حماية Symlink/TOCTOU، وعدم الكتابة فوق
Evidence، وHash reconciliation، وRuntime Trust، وبوابات Data Foundation هي
المرجعية. وجود هذه العقود لا يثبت Model أوBacktest أومصدر بيانات حيًا.

## المرجع السابق الخاص

الموقع وتفاصيل المراجعة محفوظان في التدقيق الخاص فقط. يبقى المصدر للقراءة ولا
يُدمج تاريخه ولا يعمل محركه داخل `KU-BO`.

الأفكار المفيدة التي أعيد تنفيذها أو ربطها بأمان:

- فصل transport success عن semantic success؛
- capability fallback مرتب مع إيصالات zero-result؛
- فصل source certainty عن analytical certainty؛
- resumability وسلسلة receipts؛
- فحص point-in-time للمحفظة والأوامر؛
- ربط كل وظيفة بـcallable داخل الحزمة الأساسية.

لا تنتقل درجات يقين ثابتة، أوBooleans ذاتية، أوEngine قديم، أونتائج أداء، أو
بيانات خاصة. يسجل `config/predecessor_capability_parity.json` الوظائف المعقمة
فقط.

## مصادر الكويت القديمة

الحكم هو `ARCHIVE_SELECTIVE_SALVAGE`: يمكن إعادة كتابة اختبارات هوية وPIT
وProvenance وعقود Raw/Bronze/Silver/Gold بعد مراجعتها. لا تُنقل scripts حية
ذات إشارات ثابتة، أوlabels مصنوعة من ترتيب النسب، أوchallenger lift ثابت، أو
timestamp مفقود يتحول إلى الوقت الحالي، أوsample universe غير موثق.

## نماذج البحث السابقة

الحكم هو `NO-GO` للنتائج والدرجات والقرارات عندما تغيب raw bytes الرسمية أو
OHLCV الموثقة أوBenchmark أوCorporate Actions أوsource receipts أوPIT dataset.

أفكار provider fallback وrate limiting وPDF normalization وbounded issuer
discovery قابلة لإعادة التنفيذ بعد الاختبار. لا تنتقل معادلات Score أوConfidence
أوBacktest outputs، ولا أي مسار يملأ البيانات الغائبة بما يرفع الثقة أو يستخدم
معلومة بعد وقت القرار.

## سياسة الحفظ

1. إبقاء المرجع السابق الخاص للقراءة فقط ومنع دمج تاريخه.
2. حفظ المصادر القديمة خارج المحرك الأساسي قبل أي تنظيف مستقل مفوض.
3. إعادة كتابة العقود المفيدة داخل `kubo` بدل نسخ الحزم أوالفروع.
4. ترك المشروعات الخارجة عن النطاق من دون تعديل.
5. طلب قرار مستخدم منفصل قبل أي حذف أوإغلاق أوMerge.

التفاصيل الخاصة التي تبرر هذه الأحكام تبقى خارج Git. هذا الملف ينشر القرار
الهندسي فقط، وليس محددات المصادر التي أدت إليه.
