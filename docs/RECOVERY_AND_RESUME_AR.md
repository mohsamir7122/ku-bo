# عقد الأعطال والتعافي والاستئناف

هذا العقد يجعل فشل خط الكويت حالة قابلة للتدقيق، ولا يحول الفشل أو نقص الدليل إلى نجاح. كل Incident يحمل بصمة ثابتة مشتقة من السوق والمرحلة والتصنيف والمكوّن ورمز الفشل، ويحمل دائمًا `publish_allowed=false`. لا يرسل هذا النظام أوامر تداول ولا يخفّض بوابات المصدر أو المصدرية أو الزمن.

## التصنيف والقرار

- الأعطال العابرة فقط (`transient_network` و`transient_source` و`github_infrastructure` و`robots_unreachable` و`rate_limited`) مؤهلة لإعادة آلية محدودة.
- التأخيرات المقفلة هي 30 ثم 60 ثم 120 دقيقة، بحد أقصى ثلاث محاولات خلال نافذة 24 ساعة.
- `missing_secret` لا يشغّل المسار الثقيل. ينفذ فحص وجود خفيفًا، ثم يسمح بالاستئناف فقط إذا ظهر الـSecret المطلوب.
- `deterministic_code` يحتاج SHA جديدًا ذا صلة، وCI ناجحًا، وsmoke test ناجحًا قبل الاستئناف.
- `security` و`temporal_leakage` يمنعان النشر وإعادة التشغيل الآلية ويستوجبان تنبيهًا فوريًا.
- وجود تشغيل `queued` أو `in_progress` للكويت يمنع dispatch إضافيًا.

الـJSON Schema موجود في `schemas/recovery-incident.schema.json`، والسياسة المقفلة في `config/recovery-policy.json`. التحقق البرمجي يعيد حساب البصمة، ويطابق التصنيف مع السياسة الموثوقة، ويفرض اتساق التوقيت وعدد المحاولات وحالة النشر.

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

## حدود الصلاحيات

الحل القانوني يستخدم أقل permission، وواجهات GitHub الرسمية، و`GITHUB_TOKEN` عندما يكفي، وcredential موجودًا أصلًا في GitHub Secrets. إذا لزم secret أو scope جديد فيطلب من المستخدم. الممنوعات تشمل تجاوز CAPTCHA أو paywall أو Authentication، وتدوير IP، واستخراج credentials، وتجاهل rate limit، واستعمال proxy غير مصرح، أو خفض بوابات provenance/freshness/temporal.
