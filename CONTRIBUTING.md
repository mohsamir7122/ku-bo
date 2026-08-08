# Contributing

اقرأ `AGENTS.md` والعقد المتعلق بالتغيير قبل البدء. يجب أن يتضمن كل Pull Request:

- سبب التغيير وحدود الادعاء التي يمسها.
- اختبارًا يثبت السلوك الجديد، واختبارًا خصميًا عند تعديل Evidence أوTiming أوIdentity أوLedger.
- تأكيد عدم إضافة Secrets أوبيانات مرخّصة أوCookies.
- تشغيل `python -m compileall -q src tests scripts` و`python -m unittest discover -s tests -v` و`python scripts/smoke_check.py` و`python scripts/secret_guard.py`.

لا يُسمح بتحويل Source Mosaic أوSentiment إلى Probability أوRecommendation من دون Model Card مرتبط بنتائج Prospective Validation مختومة.
