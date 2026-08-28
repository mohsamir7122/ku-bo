# Contributing

اقرأ `AGENTS.md` والعقد المتعلق بالتغيير قبل البدء. يجب أن يتضمن كل Pull Request:

- سبب التغيير وحدود الادعاء التي يمسها.
- اختبارًا يثبت السلوك الجديد، واختبارًا خصميًا عند تعديل Evidence أوTiming أوIdentity أوLedger.
- تأكيد عدم إضافة Secrets أوبيانات مرخّصة أوCookies.
- تشغيل `python -m compileall -q src tests scripts` و`python -m unittest discover -s tests -v` و`python scripts/smoke_check.py` و`python scripts/secret_guard.py`.

جهّز بيئة التطوير أولًا بحزمة الاختبار كاملة حتى لا تُتخطى اختبارات Schema أوتفشل Imports بسبب اعتماد اختياري غير مثبت:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
python -m pip check
```

لا يُسمح بتحويل Source Mosaic أوSentiment إلى Probability أوRecommendation من دون Model Card مرتبط بنتائج Prospective Validation مختومة.
