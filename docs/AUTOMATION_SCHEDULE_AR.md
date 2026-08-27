# عقد جدولة الكويت المتتابع

هذا العقد يثبت نوافذ التشغيل المطلوبة بتوقيت `Asia/Kuwait` وتحويلها إلى UTC
لأن GitHub Actions يقرأ cron بتوقيت UTC. وهو لا يثبت أن الجمع أو التدريب أو
التوقع الحي أصبح جاهزًا.

| المهمة | توقيت الكويت | UTC | GitHub cron |
| --- | --- | --- | --- |
| الجمع/التحقق الرئيسي اليومي | 15:00 | 12:00 | `0 12 * * *` |
| فحص حي مبكر | 04:00 | 01:00 | `0 1 * * 0-4` |
| فحص حي ثانٍ | 07:00 | 04:00 | `0 4 * * 0-4` |
| افتتاح السوق | 09:00 | 06:00 | `0 6 * * 0-4` |
| فحص 11 صباحًا | 11:00 | 08:00 | `0 8 * * 0-4` |
| فحص 12 ظهرًا | 12:00 | 09:00 | `0 9 * * 0-4` |
| نهاية التداول المستمر | 13:00 | 10:00 | `0 10 * * 0-4` |

الأرقام `0-4` في يوم الأسبوع تعني الأحد إلى الخميس. صفحة Boursa Kuwait
الرسمية الحالية تسجل التداول المستمر 09:00–13:00، ثم مزاد الإغلاق حتى 13:10
وTrade at Last حتى 13:15. وسجل عطلات 2026 الرسمي يحدد 27 أغسطس 2026 عطلة؛
لذلك يحولها resolver إلى `MAINTENANCE_ONLY_NO_TRADE`. وإذا انتهت تغطية التقويم
من دون تحديث رسمي، يفشل الفحص الحي بالطريقة نفسها بدل افتراض يوم تداول.

المصادر الرسمية، ووقت الوصول، وتاريخ الحدث المنفصل عند توفره موجودة في
`config/kuwait_automation_schedule.json`. لا توجد بيانات اعتماد أومعرّفات Drive
في الملف.

## الترتيب وبوابة التفعيل

الـworkflow الجديد يفرض:

```text
gate → collection → validation → live_scoring
```

ويستخدم concurrency واحدة بلا إلغاء تشغيل قائم، وtimeouts مستقلة، وسياسة retry
لا تزيد عن محاولتين للأخطاء العابرة. يسجل gate وقت بدء الخطوة الفعلي؛ ولا يدعي
أن GitHub يضمن الدقيقة المحددة.

يبقى `implementation_ready=false` حتى نجاح قبول مصدر حقيقي وبناء adapter جمع
قابل لإعادة التشغيل. حتى لو أضيفت المتغيرات أوالأسرار مصادفة لا يمكن تجاوز هذه
البوابة. عند التفعيل لاحقًا يلزم:

- Variable: `KUBO_KUWAIT_AUTOMATION_ENABLED=true`.
- Variable: `KUBO_KUWAIT_DATA_ADMISSION_READY=true`.
- Secret: `KUBO_AUTHORIZED_SOURCE_ACCESS`.
- Secret: `KUBO_DRIVE_RUNTIME_CONFIG`.

لا يطبع الـworkflow قيم الأسرار؛ يمرر فقط نتيجة وجودها كقيمة Boolean. وضع
`CONTRACT_CHECK` اليدوي يتحقق من العقد وينتج إيصالًا من دون تشغيل أي مرحلة سوق.
وضع `EXECUTE` يفشل بوضوح إذا حاول المالك التفعيل مع نقص controls. أما عندما يكون
التفعيل نفسه غير مفعل، فيسجل `BLOCKED_DISABLED` ولا يهدر jobs السوق.

الـworkflow القديم عند 15:07/15:37 أصبح `workflow_dispatch` يدويًا فقط، وحُفظ
كتوافق تاريخي حتى لا يتداخل مع الجدول الملزم الجديد. ولن تعمل cron الجديدة على
فرع العمل؛ GitHub يشغل schedules من الفرع الافتراضي فقط، والدمج إلى `main` ما
زال ممنوعًا إلى أن تنجح بوابات البيانات وBlind Test.

## أوامر قابلة لإعادة التشغيل

```bash
PYTHONPATH=src .venv/bin/python scripts/validate_kuwait_automation_schedule.py
PYTHONPATH=src .venv/bin/python scripts/validate_kuwait_automation_schedule.py \
  --resolve --slot-id market_open_0900 \
  --actual-started-at 2026-08-27T06:00:00Z --mode CONTRACT_CHECK
PYTHONPATH=src .venv/bin/python -m unittest tests/test_automation_schedule.py -v
```
