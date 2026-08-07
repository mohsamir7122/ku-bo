# Security policy

## Secrets and external access

لا تُحفظ Tokens أوCookies أوSessions أوPasswords داخل المستودع أو حزم الأدلة. تستخدم الأسرار من بيئة التشغيل فقط، وتعرض `.env.example` أسماء المتغيرات دون قيم.

تسجيل الدخول إلى Codex أوGitHub لا يمنح وصولًا تلقائيًا إلى Investing.com أوTelegram أوFacebook أوأي Broker. كل مصدر محمي يحتاج تفويضًا منفصلًا ومشروعًا، ولا يجوز للموصل تجاوز Login أوCAPTCHA أوPaywall أوRate Limit أوRobots controls.

## Reporting

عند اكتشاف ثغرة، افتح Security Advisory خاصًا في GitHub بدل Issue عام إذا كانت التفاصيل قد تكشف Secret أوتسمح بتعديل Evidence أوLedger.

## Financial safety boundary

المشروع أداة Research Decision-Support. أي `Evidence Score` ليس Probability ولا Buy Recommendation. Execution-grade output يحتاج Feed مرخّصًا وEntitlement صالحًا وبيانات Quotes/Fills موقّتة.
