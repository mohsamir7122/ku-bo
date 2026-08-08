# معمارية الأساس البرمجي KU-BO 0.1.0

هذه المعمارية تصف أساسًا قابلًا للتدقيق واختبار العقود، لا منصة Production مكتملة أوخدمة بيانات حية مضمونة التوافر.

## المساران

```mermaid
flowchart TD
    A["Analysis Request"] --> B{"نوع المخرج"}
    B -->|"Research Rank"| C["شبكة مصادر لكل تشغيل"]
    B -->|"Probability / Accuracy"| D["أرشيف + نموذج + ختم مستقبلي"]
    C --> E["Capture → Parser/QA → Validate → Rank"]
    E --> G["JSON / Markdown / Ledger"]
    D --> F["Forecast policy gate"]
```

`research_network` هو المسار الافتراضي. يعتمد على دليل حديث متعدد المصادر ويعمل من دون أرشيف كامل أو نموذج. `validated_forecast` هو مسار V2 الصارم؛ لا يسمح باحتمال أو ادعاء أداء إلا عند استيفاء Pack وModel Card والتحقق المستقبلي.

## مكونات مسار الشبكة

- `SourceNetworkCatalog`: يقرأ 40 تعريف مصدر و35 مجموعة استقلال وسياسات الأفق، ويتحقق من الأدوار والنطاقات والاستقلال وحدود التوقيت.
- `ingestion` و`capture_plan`: يجمعان البايتات العامة أوUser exports بصورة محدودة، ويحفظان Raw وManifest دون ترقيتها تلقائيًا إلى Finding. خطة واحدة لا تتجاوز 32 مهمة أو128 MiB أو300 ثانية إجمالًا، ويحدث رفض التجاوز قبل Connector/I/O.
- `Parser/QA`: يحتوي محلل هوية Boursa ومحلل تاريخ سعر Investing فقط، مع مصالحة ISIN واختبارات Drift ونهاية إلى نهاية على Fixtures مولدة. مصفوفة `source_capabilities.json` تفصل `END_TO_END_TESTED` عن `LIVE_OPERATIONAL`؛ ولا توجد في المستودع Fixture حية مصرح بها ترفع أي مصدر إلى الحالة الثانية.
- `RuntimeTrustRegistry`: يصادق سجلًا خارجيًا بـ`HMAC-SHA256` ومفتاح Runtime، ويتحقق من الجمهور والصلاحية ويربط المصادر الحساسة بالحساب/Subject والنطاق وSecurity codes وActivation/Entitlement.
- `SourceNetworkRunValidator`: يتحقق من عقد التشغيل، وهوية Effective-dated إلزامية لكل Scope، والأثر الخام، وManifest، ومحاولات المصادر، و`fact_type`، وتطابق Finding URL مع Artifact URL، والتوقيت، والـQuorum.
- `rank_research_candidates`: يجمع الإشارات بعد Dedup، ويطبق سقف ثقة فئة المصدر وسقف المزاج، ويرصد التعارض.
- `analysts` و`liquidity`: ينتجان إشارات وصفية شفافة ويقيسان Tradability؛ لا ينتجان Probability.
- `ResearchPipeline`: يحول نتيجة التحقق إلى `RESEARCH_READY` أو حالة توقف/نقص، ثم يعيد مرشحين بحدود الادعاء.
- `request_contracts` و`reporting`: يطابقان Scope ونوع التقرير واللغة والعمق، ويرفضان Claims غير مسموحة.
- `research_ledger`: يجمد Decision وOutcome في streamين منفصلين مع Hash chain وSeal؛ ويربط Outcome بحزمة Raw داخل Ledger يعاد التحقق منها عند القراءة والختم، لا بـHash يقدمه المتصل.
- `cli_v3`: يوفر أوامر الجمع والتحقق والتخطيط والتقرير والسجل.

## استقلال المصادر

الاستقلال يُحسب حسب الناشر/الأصل، لا حسب الرابط. صفحات Boursa الحالية والتقارير والإفصاحات تنتمي إلى مجموعة واحدة. كذلك Investing وصفحات تعليقاته مجموعة واحدة، وTradingView وIdeas مجموعة واحدة. المقالات المنسوخة من Reuters تُجمع في أصل واحد. إعادة إرسال رسالة Telegram لا تنشئ مصدرًا ثانيًا.

لا يكفي أن يعلن المصدر أنه أدى دورًا. كل Finding يحمل `evidence_roles`، ويُحسب نصاب الدور لكل ورقة مالية من الناشرين والأصول والأحداث المستقلة المرتبطة فعليًا بهذه Findings. `ZERO_RESULT` لا يملأ Quorum، والنتائج المحايدة أوذات Strength/Materiality صفر لا ترفع Coverage. وعند تأكيد محفز، يجب أن يطابق المصدر الرسمي `event_key` والاتجاه نفسه.

## حدود الحقيقة

- الرسمي/جهة الإصدار: يستطيع تأكيد حدث أو هوية رسمية.
- Structured secondary: يستطيع إنشاء Observation منسوبًا للمزود، لا حقيقة رسمية.
- Editorial: يستطيع إنشاء سياق/خبر منسوبًا للمصدر، مع Dedup للأصل.
- Community: `SENTIMENT` و`RISK` فقط.
- Web archive: `ARCHIVE_CONTEXT` فقط.
- Search/Storage: لا ينشئ Finding.
- Licensed: يمكنه دعم Execution فقط مع Entitlement وتوقيت مثبتين.

## حد الثقة والتفويض

الـPacket كيان غير موثوق حتى يثبت العكس؛ لذلك لا يستطيع إيصال `runtime_authority` أوActivation أوEntitlement داخله أن يكون Root of Trust لنفسه. يفرض `0.1.0` سجل ثقة خارجيًا مهيأ خارج Packet ومصادقًا بـ`HMAC-SHA256` ومفتاح Runtime للمصادر Disabled/Runtime-bound/Licensed، ويربط المصدر بالـSubject/Account والنطاق وSecurity codes وActivation/Entitlement وفترة الصلاحية. غياب السجل أوالمفتاح، أوفشل المصادقة أوعدم وجود قيد فريد مطابق، يحجب المصدر Fail-closed.

## بوابات الفشل

أي Hash غير مطابق، أو Hash تابع لمصدر آخر، أو Artifact جُمع بعد القرار، أو مسار Raw غير آمن، أو مصدر غير مسجل، أو URL خارج النطاق، أو Finding مستقبلي، أو Search Snippet/Access Receipt مستخدم كدليل، أو محاولة ترقية المنتدى إلى Catalyst تجعل الحزمة `BLOCKED`.

نقص نصاب الأدوار يجعلها `PARTIAL`. تعطل مصدر منفرد لا يوقفها إذا اكتمل النصاب من مجموعات مستقلة أخرى **وبقيت هوية Official/Licensed بديلة وحديثة لكل Security مغطى**؛ وإلا يكون فشل الهوية `SOURCE_NETWORK_BLOCKED`.

الـRanker لا يستطيع إزالة Blocking Error، ولا يستطيع توليد Probability أو Recommendation.
