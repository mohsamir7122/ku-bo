# تسليم KU-BO إلى Codex

تاريخ التسليم: 2026-08-24

## حالة الجاهزية

المستودع جاهز لبدء **مرحلة Codex التالية** من خلال عقد قابل للفحص. هذه الجاهزية
تعني أن المهمة والمسارات والحدود والتجميد محددة؛ ولا تعني أن Collector أو نموذجًا
حيًا أو توصيات يومية أصبحت جاهزة.

نفّذ أولًا من جذر المستودع:

```bash
python scripts/validate_codex_live_bootstrap.py --project-root . --json
```

النتيجة المطلوبة:

```text
PASS_HANDOFF_CONTRACT
READY_FOR_CODEX_EXECUTION
live runtime: NOT_IMPLEMENTED
scheduler: DISABLED_UNTIL_AUTHORIZED
Factor 9: RESEARCH_ASSET_PENDING_ADMISSION
```

أي اختلاف يوقف العمل حتى يُفهم سببه؛ لا يُعدّل Expected value لتجاوز الفشل.

## المشغّل الأساسي على الهاتف

Codex CLI داخل Ubuntu/Termux هو المشغّل الأساسي لبقية المشروع. دور ChatGPT هو
تثبيت الـhandoff والحدود فقط. يجب أن يعمل Codex في وحدات مترابطة صغيرة، وينهي كل
وحدة غيّرت ملفات فعلًا باختبارات وCommit وPush وHandoff، ثم يستأنف من آخر نقطة
مثبتة بدل إعادة العمل من البداية. لا ينشئ Commit فارغًا لو كانت الوحدة تدقيقًا
قرائيًا فقط.

قبل تشغيله، افتح جذر المستودع الموجود على الهاتف وتأكد أن جلسة Codex وGitHub
مسجلتان بالفعل. لا تستخدم `--yolo` أو
`--dangerously-bypass-approvals-and-sandbox`. يشغّل الأمر أدناه
`workspace-write` مع المراجع الآلية للطلبات وNetwork لأن فحص GitHub وجمع المصادر
يحتاجانهما؛ وإذا رفض المراجع إجراءً عالي الخطورة يتوقف Codex ويسجل Blocker بدل
تجاوز الحماية. تظل البيانات الخاصة عبر مسار/Connector `AI Rebuild` المخول ولا
تُنشر في Git.

## أمر START

```bash
cd /root/codexphone/workspaces/ku-bo
codex --search exec \
  --sandbox workspace-write \
  -c 'approval_policy="on-request"' \
  -c 'approvals_reviewer="auto_review"' \
  -c 'sandbox_workspace_write.network_access=true' \
  - <<'CODEX_PROMPT'
Read AGENTS.md, CODEX_START_HERE.md, and docs/codex/CURRENT_TASK.md in the required order. Verify the repository, remote, clean/dirty state, exact local and remote SHAs, main, every branch, every open PR, dependencies, mergeability, and CI before changing anything. Treat KU-BO-MOBILE-CODEX-D01 as the owner's conditional delegation: classify every unmerged ref, preserve and repair unique useful work, run targeted and full tests plus exact-head CI, and merge only validated non-duplicated heads in dependency order. A narrower open or rejected decision always wins: KU-BO-MIG-001 remains USER_DECISION_REQUIRED and unmerged while KU-BO-MIG-D02 is open. Never blindly merge a stale branch. Never force-push, delete, weaken gates, expose secrets, publish private/licensed data, bypass access controls, spend money, fabricate evidence, or perform financial execution. Keep coherent checkpoints as focused commits, pushes, status updates, and handoffs, but never create an empty commit. After green verified main, create the next bounded task and continue KU-BO one security at a time: official identity, 29 terminal source receipts in seven waves, private raw evidence with provenance, durable security-aware checkpoint, reconciliation, and a terminal security seal before the next security. The current Day-One task is read-only for private runtime and Drive; write under AI Rebuild only after the later task explicitly records that authority. Continue until the active acceptance gates pass or a genuine external/user-decision blocker is recorded; do not turn a blocker into an invented success.
CODEX_PROMPT
```

## أمر RESUME

```bash
cd /root/codexphone/workspaces/ku-bo
codex --search exec \
  --sandbox workspace-write \
  -c 'approval_policy="on-request"' \
  -c 'approvals_reviewer="auto_review"' \
  -c 'sandbox_workspace_write.network_access=true' \
  resume --last \
  'Resume from the last proven Git commit, checkpoint, and handoff. Recheck git status, exact local/remote heads, main, PRs, CI, CURRENT_TASK, USER_DECISIONS, and all recorded blockers before acting. Preserve completed work, repair only the next coherent unit, test it, checkpoint it, and continue until the active gates pass or a genuine external/user-decision blocker is recorded.'
```

وفق [OpenAI Docs](https://developers.openai.com/codex/non-interactive-mode)، يدعم
`codex exec` التشغيل غير التفاعلي والقراءة من stdin، ويدعم
`codex exec resume --last` استئناف آخر جلسة محفوظة من مجلد العمل الحالي. لا
تستخدم `--ephemeral` لأن الاستئناف مطلوب.

لا يحتاج المستخدم إلى إعادة شرح تاريخ المشروع؛ `CODEX_START_HERE.md` وملفات
`docs/codex/` وملف bootstrap هي ذاكرة التشغيل الرسمية.

## AI Rebuild

الجذر الخاص هو `AI Rebuild`. المسارات التي أُعدت لـKU-BO هي:

```text
00_Indexes/KU_BO
02_Google_Drive/KU_BO/PRIVATE_CONVERSATION_ARCHIVE
02_Google_Drive/KU_BO/AUTHORIZED_EXPORTS
04_Curated_Core/KU_BO/00_Manifests
04_Curated_Core/KU_BO/01_Factor9_Research
04_Curated_Core/KU_BO/02_Event_Evidence
04_Curated_Core/KU_BO/03_Market_Data
04_Curated_Core/KU_BO/04_Model_Freezes
04_Curated_Core/KU_BO/05_Daily_Reports
90_Quarantine_Duplicates/KU_BO
99_Reports/KU_BO
```

Codex يكتشف معرفات هذه المجلدات وقت التشغيل من Connector المخول. لا يكتبها في
Git أو Documentation أو Logs عامة. كل نقل إلى Curated Core يحتاج Hash وProvenance
وحقوقًا ومراجعة، ولا تُحذف النسخ المكررة؛ تُنقل أولًا إلى Quarantine.

## ترتيب Daily dry-run

1. التحقق من جلسة السوق والحصول على Run lock.
2. فحص الوصول المصرح للمصادر.
3. جمع الأدلة وحفظ البايتات الخاصة وبصماتها.
4. Validation وتطبيع Point-in-Time.
5. بناء Event/Factor snapshot.
6. تشغيل Champion السابق المعتمد فقط.
7. ختم تقرير البحث اليومي.
8. إنضاج وتقييم نتائج التقارير السابقة.
9. تدريب Challengers في مساحة منفصلة بعد فتح بوابة التدريب.
10. إنشاء Draft change proposals دون دمج ذاتي.

إذا لم توجد Freeze صالحة من جلسة سابقة، فالنتيجة `ABSTAIN` أو إيقاف التقرير؛ لا
يُستخدم Challenger اليوم نفسه كحل بديل.

## التوقيت

الوقت الأساسي 15:07 الكويت والـWatchdog عند 15:37. Workflow الظل يختبر العقود
فقط وهو مغلق افتراضيًا خلف `KUBO_DAILY_SHADOW_ENABLED`. كما أن GitHub scheduling
best-effort ولا يضمن التنفيذ في الدقيقة نفسها. تفعيل Workflow لا يفتح Network
collection ولا التدريب ولا التوصيات تلقائيًا.

## مخرجات المرحلة الأولى

المرحلة التالية تنتج Private inventory وFactor 9 admission report وDaily dry-run
receipts واختبارات. لا تنتج أسماء أسهم للشراء أو أسعار دخول وخروج.

المنتجات الأربعة تصبح تقارير بحث فقط بعد اكتمال Data Plane وChampion freeze.
الانتقال إلى توصيات أو Quotes تنفيذية يحتاج بيانات رسمية/مرخصة، اختبارًا مقفلًا
500-600 حدث، prospective validation، وسياسة مخاطر وقرار استخدام منفصل.

## التطوير الذاتي الآمن

Codex مسموح له أن يقرأ النتائج، يسجل Failure mode، يبني Challenger، ويقترح تعديل
كود أو وزن في Task branch. ليس مسموحًا له أن يغير Champion الجاري، يعيد كتابة
تقرير قديم، يدمج PR، أو يختار الأوزان على Locked test. بهذه الحدود يصبح التطوير
مستمرًا وقابلًا للرجوع بدل أن يكون تعديلًا حيًا غير قابل للتدقيق.
