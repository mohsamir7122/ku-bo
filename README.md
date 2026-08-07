# KU-BO Research Engine 0.1.0 — أساس قابل للتدقيق للبحث متعدد المصادر في بورصة الكويت

`KU-BO` أساس برمجي `Auditable Research Foundation` لأعمال `Research Decision-Support`. يجمع Evidence Pack من مصادر متعددة، ويتحقق من التوقيت والهوية واستقلال الناشرين، ثم ينتج ترتيبًا بحثيًا أو `WATCH` أو `ABSTAIN` حسب الأدلة المتاحة. تعطل موقع منفرد لا يوقف البحث تلقائيًا، لكنه قد يحجبه إذا أزال دليل الهوية الرسمي الإلزامي ولم يبق بديل رسمي حديث.

هذه النسخة ليست منصة مكتملة للإنتاج، ولا خدمة جمع حية شاملة، ولا نظام توصيات أوتنفيذ تداول. نجاح العقود والاختبارات الاصطناعية يثبت سلوك الأساس البرمجي فقط، ولا يثبت توافر المصادر الخارجية أوالدقة التنبئية أوالجاهزية التشغيلية المستمرة.

النتيجة الافتراضية الآن هي **Research Rank موثّق للمجموعة التي جرى تغطيتها**. ليست احتمالًا، وليست توصية شراء، ولا تدّعي دقة تاريخية لم تُقَس. يظل المسار القديم الأكثر صرامة موجودًا بصورة منفصلة عندما تكون الحاجة إلى Forecast احتمالي أو Backtest موثوق.

## المبادئ غير القابلة للتجاوز

- الوضع الافتراضي أصبح `research_network`.
- لا يحتاج البحث الأولي إلى Historical Pack كامل أو Model Card.
- يحتاج كل تشغيل إلى حزمة أدلة حديثة من عدة مصادر مستقلة، لا إلى نجاح موقع واحد.
- تعطل بورصة الكويت لا يوقف البحث كله إذا اكتمل النصاب **وبقي إيصال هوية رسمي بديل وحديث**؛ وإلا يكون فشل الهوية Structural. كما يمنع التعطل اعتبار المحفز «مؤكدًا رسميًا» ويخفض السهم المتأثر إلى `WATCH`.
- المنتديات وتليغرام وTradingView Ideas تساهم في المزاج والمخاطر فقط، بحد أقصى 10% للأفق القصير، ولا تستطيع إنشاء حقيقة رسمية أو محفز.
- إعادة نشر الخبر عشر مرات تُحسب أصلًا واحدًا.
- صفحات السوق والتعليقات داخل المنصة نفسها تُحسب ناشرًا واحدًا؛ Investing لا يصبح مصدرين، وكذلك TradingView.
- تضارب إشارتين مستقلتين وقويتين يفرض `WATCH`.
- التأكيد الرسمي يجب أن يطابق `event_key` واتجاه المحفز نفسه؛ إفصاح رسمي مختلف لا يؤكد خبرًا آخر لمجرد تعلقهما بالسهم ذاته.
- لا يُستخدم وصف «الأفضل في السوق» إلا بعد مطابقة 100% من عضوية السوق وتغطيته لحظيًا.
- الافتتاح وIntraday والتنفيذ يظلون `EXECUTION_BLOCKED` من دون Feed مرخّص ومؤقت.

## شبكة المصادر

يسجل الكتالوج شبكة قابلة للتوسع من المصادر وعائلات الناشرين، موزعة على أدوار لا على قائمة ثقة عمياء:

الحالة الحالية في `0.1.0` هي **40 تعريف مصدر** تُحتسب ضمن **35 مجموعة استقلال**؛ عدد الروابط أوالأسطح لا يساوي عدد الناشرين المستقلين.

- رسمي/جهة إصدار: بورصة الكويت، تقاريرها وإفصاحاتها، هيئة أسواق المال/iFSAH، ومواقع علاقات المستثمرين الموثقة.
- سوق وتاريخ سعري: Investing.com، TradingView، Argaam، MarketScreener، Mubasher، Yahoo Finance، وTradingEconomics.
- أخبار وأرشيف صحفي: KUNA، Reuters، Zawya، Asharq Business، الراي، الأنباء، الجريدة، والقبس.
- مجتمع ومنتديات: IndexSignal، قنوات تليغرام العامة، وTradingView Ideas.
- أرشيف ويب وتوجيه: Wayback Machine، Common Crawl، والبحث على الويب.
- بيانات مرخّصة: ICE أو Broker/Market Feed مصرح به عند وجود Entitlement حقيقي.

كل مصدر يملك عقدًا يحدد أدواره، نطاقاته، مجموعة استقلاله، أقصى درجة لتوقيت الدليل، وما إذا كان يستطيع إنشاء Finding أم لا.

## نصاب المصادر حسب الأفق

للأفق من جلسة إلى خمس جلسات، يلزم على الأقل مصدران مستقلان لاكتشاف السوق، ومصدر تاريخ سعري، ومصدران إخباريان، وأربع مجموعات مستقلة إجمالًا.

للأفق من 10 إلى 63 جلسة، يلزم مصدران لاكتشاف السوق، ومصدران تاريخيان، ومصدران إخباريان، ومصدر أساسيات، وخمس مجموعات مستقلة.

للأفق 126 أو 252 جلسة، يلزم مصدران تاريخيان، ومصدران إخباريان، ومصدران للأساسيات، وخمس مجموعات مستقلة. مساهمة المجتمع في هذا الأفق تساوي صفرًا.

للافتتاح أو Intraday، يلزم `EXECUTION_TAPE` مرخّص. المواقع العامة لا تعوضه.

## حزمة كل تشغيل

```text
research_run/
  research_run.json
  universe.json              # required effective-dated identity in every scope
  manifest.json
  source_observations.json
  findings.jsonl
  raw/
    ... exact captured bytes ...
```

`research_run.json` يثبت المنتج، `decision_at`، النطاق، تغطية الكون، والميزانية. `universe.json` إلزامي لكل نطاق، ويربط كل `security_code` وTicker بفعالية زمنية ومصدر هوية Official/Licensed وأثر خام. يفسر `membership_as_of` بتوقيت `Asia/Kuwait`، ويجب أن يقع في تاريخ القرار المحلي نفسه وألا يتجاوزه؛ الأعداد وحدها لا تكفي، ووصف السوق كاملًا يتطلب كذلك تغطية 100% وFinding جوهريًا لكل عضو متوقع. يربط `manifest.json` كل أثر خام بعنوانه وتوقيته وحجمه وSHA-256. يسجل `source_observations.json` نجاح أو فشل كل مصدر وسبب قبوله أو رفضه. ويحتوي `findings.jsonl` فقط على الاستنتاجات المرتبطة بأثر خام من المصدر نفسه، مع `evidence_roles` و`fact_type` صالحين؛ ويجب أن يطابق `source_url` عنوان الـArtifact المشار إليه حرفيًا. كما يرتبط التقرير والسجل بـ`evidence_packet_hash` واحد يغطي الملفات القانونية والأدلة المشار إليها في Manifest.

## حالات التشغيل

- `SOURCE_NETWORK_REQUIRED`: لم تُقدم حزمة تشغيل حديثة.
- `SOURCE_NETWORK_BLOCKED`: عقد أو توقيت أو Hash أو هوية غير صالح.
- `RESEARCH_PARTIAL`: الحزمة سليمة لكن نصاب الأدوار غير مكتمل.
- `RESEARCH_READY`: نصاب الشبكة مكتمل ويمكن إخراج Research Rank.
- `EXECUTION_BLOCKED`: المنتج يحتاج Feed تنفيذ مرخّصًا غير موجود.

أما `validated_forecast` فيحتفظ ببوابات Historical Pack وModel Card والتحقق المستقبلي. وجوده لا يجعل الوضع البحثي Probability بصورة غير مباشرة.

## البدء

يتطلب Python 3.11 أو أحدث ولا توجد تبعيات خارجية في النواة.

```bash
python3 -m pip install -e .
kubo validate-source-network
kubo validate-live-probe --probe research/live_source_probe_2026-08-07.json
```

واجهة `kubo` تعتمد على ملفات العقود داخل Checkout المشروع. عند تثبيت Wheel وتشغيل الأمر من خارجه، مرر جذر المستودع قبل اسم الأمر:

```bash
kubo --project-root /absolute/path/to/ku-bo validate-source-network
```

إذا لم يكن الجذر صالحًا، يفشل الأمر برسالة واضحة بدل Traceback أو افتراض وجود إعدادات داخل الـWheel.

يمكن أيضًا التشغيل من دون تثبيت:

```bash
PYTHONPATH=src python -m kubo validate-source-network
```

إنشاء خطة بحث من حزمة تشغيل:

```bash
kubo plan \
  --mode research_network \
  --product next_session_rank \
  --network-run /absolute/path/to/research_run
```

إنشاء تقرير مرن من عقد طلب:

```bash
kubo run-request \
  --request examples/analysis_request.json \
  --network-run examples/synthetic_source_network_run \
  --output runtime/report.md
```

`examples/analysis_request.json` اصطناعي. يمكن اختيار `json` أو`markdown` وتحديد Scope والأسهم وعمق التقرير، لكن الوضع `research_network` يرفض صراحة طلب Probability أوBuy Recommendation أوEntry/Exit Price.

## الجمع والموصلات

طبقة الجمع تحفظ البايتات الخام أولًا، ثم Manifest يحتوي URL ووقت الالتقاط والحجم وSHA-256 وحالة المصدر. يوجد Connector للملفات والـFixtures للاختبارات، وPublic HTTP Connector محدود بالـAllowlist والحجم والوقت. الموصل لا يتجاوز Login أوCAPTCHA أوPaywall أوRate Limit أوRobots controls.

خطة الجمع محدودة بثوابت Fail-closed: **32 مهمة كحد أقصى، و128 MiB لمجموع `max_bytes`، و300 ثانية لمجموع `timeout_seconds`**. تُرفض الخطة المتجاوزة قبل إنشاء أي Connector أوبدء الالتقاط أوكتابة مجلد الناتج.

تشغيل Capture Plan اصطناعي:

```bash
kubo capture \
  --plan examples/capture_plan.json \
  --fixture-root examples/synthetic_source_network_run \
  --output-root runtime/capture
```

النتيجة Raw capture فقط، وتبقى `RAW_CAPTURE_PENDING_PARSER_VALIDATION`. لا تدخل في Rank قبل Parsing وIdentity وTiming وEvidence validation.

لا تتضمن النسخة `0.1.0` Parsers حية خاصة بكل موقع تحول صفحات الإنترنت تلقائيًا إلى Findings. إنشاء Findings حقيقية يحتاج Parser/QA مستقلًا يطبق Schema والعقود أعلاه؛ المثال الحالي اصطناعي، وطبقة الجمع وحدها لا تؤهل الدليل.

الموصلات التي تحتاج حسابًا، مثل Investing.com أوTelegram أوFacebook أوInstagram أوTikTok أوX، لا تصبح متاحة بمجرد تسجيل الدخول إلى Codex أوGitHub. كل Connector يحتاج تفويضه المستقل، والحسابات الاجتماعية غير الموثقة لا تُثبت حقائق شركة.

### حد الثقة للمصادر المحمية

يفحص `0.1.0` البنية والروابط الداخلية لحقول `runtime_authority` وActivation وEntitlement داخل Packet، لكن هذه الحقول **ليست Root of Trust** لأنها قد تكون منشأة مع الحزمة نفسها. التصميم الأمني المطلوب قبل أي تشغيل Production هو سجل ثقة خارجي منفصل وموقّع يربط `source_id` بالحساب/Subject والنطاق و`security_code` والاستحقاق وفترة الصلاحية ومفتاح التوقيع. إلى أن ينفذ هذا السجل والتحقق من توقيعه، تبقى المصادر المعطلة أوالديناميكية أوالمرخصة غير مخولة للإنتاج حتى لو احتوت الحزمة على إيصال ذاتي متسق.

## منهج التحليل

- `source_network` يفرض Point-in-Time cutoff ويربط كل Finding بأثر خام من المصدر نفسه.
- `research_rank` يزيل إعادة النشر على مستوى Origin/Publisher Family ويكشف التعارضات.
- `liquidity` يفصل جودة الإشارة عن قابلية التنفيذ، ويمثل `NO_FILL` و`PARTIAL_FILL` والحدود السعرية والتعليق.
- `methodology_registry.json` يربط كل منهج بمرجعه العلمي وحالته واختباراته المطلوبة.
- أي Model أوProbability يبقى محجوبًا حتى Prospective Validation وTemporal Calibration وModel Card مختوم.

## Degraded Mode

- فشل بورصة الكويت: يستمر البحث فقط إذا بقي إيصال هوية Official/Licensed بديل وحديث؛ وتُخفض Official Confirmation للأسهم المتأثرة.
- فشل Social Media: يستمر التحليل من دون طبقة Sentiment.
- فشل مصدر سعري أوخبري: يستمر ما دام Quorum المستقل مكتملًا.
- نقص أدلة سهم واحد: يتحول السهم إلى `WATCH` أو`ABSTAIN`، ولا يتوقف السوق كله.
- `SOURCE_NETWORK_BLOCKED` ينتج من تلف العقود أوالهوية أوالأدلة. حجب موقع منفرد لا يكفي وحده، لكن غياب بديل يفي بعقد الهوية الإلزامي يكفي للحجب.

## Research Ledger

يمكن تجميد التقرير الصادر في Decision stream مستقل عن Outcome stream:

```bash
kubo run-request \
  --request examples/analysis_request.json \
  --network-run examples/synthetic_source_network_run \
  --research-ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1

kubo verify-research-ledger \
  --ledger-dir runtime/ledger \
  --ledger-id kuwait-research-v1
```

السجل Append-only مع Hash chain ولا توجد API لتعديل قرار قديم. Outcomes تضاف بأمر منفصل بعد وقت القرار. يمكن إنشاء HMAC Seal باستخدام `KUBO_LEDGER_HMAC_KEY` وقت التشغيل فقط بصيغة `hex:` أو`base64:` ومع `--key-id`. لا تحفظ قيمة المفتاح في `.env.example` أوGitHub.

تشغيل المثال الاصطناعي للتحقق من العقود فقط:

```bash
PYTHONPATH=src python3 scripts/smoke_check.py
```

المثال الاصطناعي ليس بيانات بورصة ولا توقعًا.

## التحقق

```bash
PYTHONPATH=src python3 -m compileall -q src tests scripts
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 scripts/smoke_check.py
PYTHONPATH=src python3 scripts/secret_guard.py
```

تشغّل GitHub Actions هذه البوابات على Python `3.11` و`3.12` و`3.13` و`3.14`. لا تثبت الوثائق عدد اختبارات ثابتًا؛ نتيجة CI الخاصة بالـCommit هي المرجع.

تغطي الاختبارات حالات غياب بورصة الكويت، فتح قناة رسمية بلا Finding، المجتمع وحده، Finding مستقبلي، Hash تابع لمصدر آخر، Artifact جُمع بعد القرار، Access Receipt أوSearch Snippet كدليل، تضارب مستقل، إعادة النشر، Counts بلا Universe Receipt، Probability غير مدعومة، السيولة الصفرية، التعليق، Limit Queue، وPartial Fill.

## خريطة الملفات

- `config/source_network.json`: سجل المصادر والأدوار والاستقلال وحدود الحقيقة.
- `config/research_policies.json`: نصاب كل أفق وأوزان Research Rank.
- `src/kubo/source_network.py`: مدقق كتالوج الشبكة وحزمة التشغيل والـLive Probe.
- `src/kubo/research_rank.py`: ترتيب الأدلة مع Dedup وتعارض المصادر.
- `src/kubo/request_contracts.py`: عقد الطلب المرن وحدود الحقول.
- `src/kubo/reporting.py`: مخرجات JSON وMarkdown حسب الطلب.
- `src/kubo/liquidity.py`: قياسات السيولة ومحاكاة تنفيذ محافظة.
- `src/kubo/pipeline.py`: المسار الافتراضي الجديد والمسار التاريخي المنفصل.
- `src/kubo/cli_v3.py`: واجهة الأوامر.
- `schemas/`: عقود JSON Schema القابلة للقراءة الآلية.
- `research/methodology_registry.json`: الأبحاث والقواعد والاختبارات المنهجية.
- `.github/workflows/ci.yml`: Compile وUnit/Adversarial Tests وSmoke Check وSecret Guard.
- `tests/test_source_network.py`: اختبارات الشبكة الخصمية.
- `research/live_source_probe_2026-08-07.json`: إيصال تجربة الوصول الحية؛ يثبت الوصول فقط.
- `docs/SOURCE_NETWORK_REPLACEMENT_AR.md`: تقرير تاريخي لمرحلة استبدال الشبكة قبل إصدار `0.1.0` الحالي.
- `docs/V3_1_HARDENING_AR.md`: لقطة تاريخية لتدقيق V3.1؛ الأرقام النهائية الحالية موثقة في `docs/BUILD_STATUS_AR.md`.
- `docs/OPERATIONS_AR.md`: طريقة بناء تشغيل حقيقي.
- `docs/legacy_v2/`: وثائق V2 التاريخية للرجوع، وليست مسار التشغيل الافتراضي.

## الحد الفاصل المهم

نجاح الشبكة يعني أن الأدلة الحالية كافية لترتيب بحثي محدود النطاق. لا يعني أن السهم سيرتفع، ولا أن هناك نسبة نجاح، ولا أن الشراء ممكن بالسعر الظاهر. تحويل النتيجة إلى احتمال أو ادعاء دقة يحتاج Forecasts مستقبلية مختومة، Outcomes منفصلة، Denominator كامل، تكاليف، واختبارًا زمنيًا لم تُغيّر سياسته بعد رؤية النتائج.

## حدود النسخة 0.1.0

النواة والاختبارات وCLI تعمل بلا Credentials. أما الوصول الحي الكامل إلى المنصات المحمية وExecution-grade data فيتوقف عمدًا على التفويض وEntitlement القانوني، وعلى تنفيذ سجل الثقة الخارجي الموقّع الموضح أعلاه. لا يحتوي المستودع على Cookies أوTokens، ولا يدّعي أن Connector غير مفوض يعمل. كما لا يصف Synthetic Smoke Check بأنه Backtest أوأداء حقيقي. وعند تشغيل Wheel من خارج Checkout، يجب تمرير `--project-root` إلى نسخة من المستودع تحتوي ملفات `config/`؛ فالـWheel ليس حزمة إعداد مستقلة.

## الترخيص

المشروع Proprietary وجميع الحقوق محفوظة باسم Mohamed Samir Rashed Shaheen. الاطلاع على المستودع لا يمنح حق الاستخدام أوالنسخ أوالتعديل أوالتوزيع؛ راجع `LICENSE`.
