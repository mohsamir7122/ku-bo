# KU-BO-017: الجرد الخاص وDaily dry-run

## الحالة

هذه المرحلة تنفذ عقودًا واختبارات فقط. لا تجمع موقعًا عامًا، ولا تدرب نموذجًا،
ولا تصدر أسماء شراء أو أسعار دخول وخروج.

## أوامر التحقق

```bash
kubo --project-root . validate-source-quality-policy
kubo --project-root . validate-ku-bo-live-program
kubo --project-root . validate-factor9-admission \
  --manifest AUTHORIZED_MANIFEST \
  --artifact-root TRUSTED_FACTOR9_ARTIFACT_ROOT
```

تشغيل Dry-run فارغ متعمدًا:

```bash
kubo --project-root . run-live-dry-run \
  --private-runtime-root AUTHORIZED_RUNTIME_ROOT \
  --output-root RUN_OUTPUT_ROOT \
  --run-id RUN_ID \
  --decision-session-date SESSION_DATE
```

غياب Access probe سيجعل المرحلة الثانية `BLOCKED` ويولد عشرة إيصالات دون مرشح
بحثي. التشغيل الكامل يحتاج ملفات خاصة تحت `private-runtime-root` وأربع روابط
`--champion-freeze PRODUCT_ID=RELATIVE_PATH`، ولا تحفظ المخرجات المسارات نفسها.

## Factor 9

الـManifest الخاص يلزم ثمانية أدوار Artifact وسبع بوابات وستة عوائق. المقام
يبقى داخل الـManifest الخاص، والمدقق يفرض أن `Raw = Clean + Excluded` وأن Issue
flags حقل مستقل لا يمكن استخدامه بدل الصفوف المستبعدة.

لا تكفي hashes المعلنة. يعيد المدقق فتح كل Artifact من الجذر الموثوق، ويرفض
symlink وpath traversal والملف المفقود، ويعيد حساب الحجم وSHA-256. كذلك لا تمر
بوابة محلولة إذا كانت أدلتها لا تشير إلى Artifact أعيد فتحه داخل الـManifest.

حتى بعد مرور كل البوابات، الحد الأقصى هو `ADMITTED_RESEARCH_INPUT_ONLY`، مع منع
التدريب والتوصية والترقية الآلية.

## الخصوصية

Git يحتفظ بالكود والعقود فقط. التخزين الخارجي المفوض يحتفظ بالملفات والبصمات
التشغيلية والتقارير. أي URL أوStorage ID أوConnector ID داخل Manifest أوReceipt
يوقف التحقق.
