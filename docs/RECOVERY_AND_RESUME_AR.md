# عقد الأعطال والتعافي والاستئناف

هذا العقد يجعل فشل خط الكويت حالة قابلة للتدقيق، ولا يحول الفشل أو نقص الدليل إلى نجاح. كل Incident يحمل بصمة ثابتة مشتقة من السوق والمرحلة والتصنيف والمكوّن ورمز الفشل، ويحمل دائمًا `publish_allowed=false`. لا يرسل هذا النظام أوامر تداول ولا يخفّض بوابات المصدر أو المصدرية أو الزمن.

## التصنيف والقرار

- الأعطال العابرة فقط (`transient_network` و`transient_source` و`github_infrastructure` و`robots_unreachable` و`rate_limited`) مؤهلة لإعادة آلية محدودة.
- لا توجد مهلة ثابتة في المسار الحرج. حدث `workflow_run` المكتمل يعيد الوظائف
  الفاشلة فقط فورًا عبر واجهة GitHub الرسمية، بحد أقصى محاولتين آليتين لكل
  fingerprint خلال نافذة 24 ساعة.
- كل محاولة تحمل `idempotency_key` مشتقًا من fingerprint وSHA الكود ومعرّف
  التشغيل ورقم المحاولة. يعيد المدقق حسابه ولا يقبل قيمة يختارها المستدعي.
- `missing_secret` لا يشغّل المسار الثقيل. ينفذ فحص وجود خفيفًا، ثم يسمح بالاستئناف فقط إذا ظهر الـSecret المطلوب.
- `deterministic_code` يحتاج SHA جديدًا ذا صلة، وCI ناجحًا، وsmoke test ناجحًا قبل الاستئناف.
- `security` و`temporal_leakage` يمنعان النشر وإعادة التشغيل الآلية ويستوجبان تنبيهًا فوريًا.
- وجود تشغيل `queued` أو `in_progress` للكويت يمنع dispatch إضافيًا.

الـJSON Schema موجود في `schemas/recovery-incident.schema.json`، والسياسة المقفلة في `config/recovery-policy.json`. التحقق البرمجي يعيد حساب البصمة ومفتاح idempotency، ويطابق التصنيف مع السياسة الموثوقة، ويفرض أن تكون المحاولة الآلية مستحقة فورًا، مع اتساق التوقيت وعدد المحاولات وحالة النشر.

## الاستئناف الفوري والـwatchdog

- يستمع `recovery-controller.yml` إلى اكتمال `Kuwait Market Pipeline` و`CI`.
- أعطال runner وnetwork وtimeout/5xx المؤهلة تستخدم endpoint الرسمي
  `rerun-failed-jobs`؛ لا تعيد pipeline كاملًا ولا تستخدم `sleep`.
- يربط controller الميزانية بـ`github.run_attempt` الموثوق ويمنع معالجة حدث
  مكرر بنفس idempotency state.
- الـwatchdog يعمل كل خمس دقائق، لكنه لا يؤخر المحاولة الأولى. لا يتدخل قبل
  مرور 300 ثانية على incident بلا معالجة، ويستعيد الأحداث المفقودة فقط.
- `missing_secret` يبقى health probe خفيفًا، و`security` لا يعاد آليًا.
- pipeline والـcontroller يشتركان في concurrency group واحدة مع
  `cancel-in-progress=false`، وتمنع probes التشغيل إذا وُجد run في
  `queued` أو `in_progress`.

## التشخيص الآمن

يجب تمرير التقارير عبر `sanitize_diagnostics`. تُحجب قيم Authorization وCookie وBearer والـtokens والـsigned URLs والحقول الحساسة المتداخلة. لا توضع response bodies أو headers خام في Incident أو Issue أو artifact. لا تنفذ وحدة التحكم أوامر مأخوذة من صفحة ويب ولا كودًا منزّلًا غير مراجع.

## الـLease

الـlease يحتوي على `run_id` و`owner` و`process_identity` و`created_at` و`expires_at` و`heartbeat` وبصمة للمحتوى. لا يستبدل lease غير منتهٍ. وعند انتهائه، يظل الاسترداد ممنوعًا إذا كانت العملية المحلية الأصلية حية، أو إذا لم ينجح فحص التشغيلات النشطة لنفس fingerprint، أو إذا أفاد الفحص بوجود تشغيل نشط. تحديث heartbeat أو تحرير الـlease مقصور على المالك والهوية نفسيهما.

## التنبيه والاستئناف

القناة الأساسية هي GitHub Issue واحدة لكل fingerprint بعنوان `[URGENT][KUWAIT MARKET] Pipeline blocked`، مع كبح التكرار ست ساعات. البريد المباشر غير مهيأ حاليًا، والحالة الصريحة هي `DIRECT_EMAIL_NOT_CONFIGURED`; لا تُخمن بيانات اعتماد ولا تُخزن كلمة مرور بريد.

أمثلة محلية:

```bash
python scripts/recovery_controller.py --project-root . validate-policy
python scripts/recovery_controller.py --project-root . validate-incident --incident recovery-incident.json
python scripts/recovery_controller.py --project-root . validate-dispatch --mode resume --incident-id INC-0123456789ABCDEF0123 --checkpoint CHECKPOINT_01
```

بعد وجود الـworkflows على الفرع الافتراضي ومراجعة الدمج، يكون الاستئناف اليدوي المقصود:

```bash
gh workflow run recovery-controller.yml --ref main -f incident_id="INCIDENT_ID" -f force_probe=true
```

الجدولة و`repository_dispatch` لا يتفعّلان من هذا الفرع وحده؛ يحتاجان مراجعة ودمجًا مصرحًا به إلى `main`. وحدة التحكم ممنوعة من تعديل أو دمج `main`.

## robots.txt وبدائل المصدر

مسار المصدر منفصل عن إعادة workflow: timeout وDNS و5xx يحصلون على محاولتين
سريعتين كحد أقصى مع jitter قبل الانتقال فورًا للمصدر التالي. 429 يسجل
`Retry-After` ويفتح circuit للمصدر دون حبس المسار الحرج. 401/403 وpaywall
وrobots/ToS وmissing secret تعطل adapter فقط ولا يعاد طلبها أو تجاوزها.
فشل schema/parser يعزل bytes والـadapter، ثم تستمر المصادر الأخرى. كل محاولة
مقيدة بـfingerprint وidempotency وattempt budget، ولا توجد حلقة retry غير
محدودة.

كل فحص `robots.txt` ينتج `RobotsPolicyReceipt` منقحًا ومربوطًا بـSHA-256. يسجل الإيصال `source_id` والأصل وstatus code وسلسلة redirects ووقت الجلب ووقت التقييم وانتهاء cache والقرار، ولا يسجل query values أو credentials. الحد الأقصى خمسة redirects، وأي loop أو انتقال إلى domain غير مسجل ينتج `ROBOTS_REDIRECT_BLOCKED`. مدة cache موجبة ولا تتجاوز 24 ساعة، ولا تستخدم نتيجة منتهية.

- 2xx: تُحلل السياسة وتطبق على الـURL المطلوب.
- 404/410: ليست حظرًا آليًا، لكنها لا تسمح بالطلب التالي إلا بوجود grant موثوق ومؤرخ يثبت `PERMITTED` للحقوق و`REVIEWED_PERMITTED` للشروط و`CONFIRMED_PUBLIC` للوصول. غياب أي بوابة ينتج `ACCESS_REVIEW_REQUIRED`.
- 401/403: `ACCESS_REVIEW_REQUIRED` دون محاولة التفاف.
- 429: `RETRYABLE_RATE_LIMIT` داخل إيصال السياسة، مع حفظ `Retry-After` الصحيح؛ نتيجة الالتقاط الخارجية تبقى `HTTP_RATE_LIMITED` للتوافق التشغيلي.
- 5xx أو DNS أو TLS أو network failure: `ROBOTS_UNREACHABLE` مع منع مؤقت للجمع وطلب health probe لاحق.

إيصال الوصول لا يثبت جمع بيانات ولا يرفع raw bytes إلى market evidence؛ تحفظ ملفات `robots-policy-receipts.json` الحد `access_receipt_proves_collection=false`. وبغياب grant إنتاجي موثق، يظل 404/410 مغلقًا افتراضيًا، بما في ذلك KCC وBoursa.

عند تعذر المصدر الأولي، يفرض `next_source_fallback` ترتيبًا متتابعًا لا يقبل التخطي أو إعادة الترتيب: API أو export رسمي موثق، ثم صفحة أو مستودع رسمي بديل، ثم إفصاحات الشركة الرسمية، ثم سجلات الجهة التنظيمية، ثم export مصرح يقدمه المستخدم، وأخيرًا مصدر ثانوي للاستكشاف فقط. المرحلة الثانوية لا تؤكد الحقيقة ولا تسمح بالنشر دون أصل أولي.

## حدود الصلاحيات

الحل القانوني يستخدم أقل permission، وواجهات GitHub الرسمية، و`GITHUB_TOKEN` عندما يكفي، وcredential موجودًا أصلًا في GitHub Secrets. إذا لزم secret أو scope جديد فيطلب من المستخدم. الممنوعات تشمل تجاوز CAPTCHA أو paywall أو Authentication، وتدوير IP، واستخراج credentials، وتجاهل rate limit، واستعمال proxy غير مصرح، أو خفض بوابات provenance/freshness/temporal.
