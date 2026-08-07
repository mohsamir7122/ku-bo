# الانتقال من V2 إلى V3

## التغيير الافتراضي

كان `plan` في V2 ينتظر Historical Evidence Pack وModel Card. في V3 أصبح الوضع الافتراضي `research_network` وينتظر Per-run Source Packet.

الأمر القديم:

```bash
kubo plan --product next_session_rank --pack /path/to/pack
```

أصبح صراحة:

```bash
kubo plan --mode validated_forecast --product next_session_rank --pack /path/to/pack
```

والبحث الجديد:

```bash
kubo plan --mode research_network --product next_session_rank --network-run /path/to/run
```

## ما بقي متوافقًا

الهوية التاريخية، Manifest، Capability Pack، Model Card، Ledger، Execution Gates، Stop Gates، والتقييم الزمني ما زالت موجودة للمسار الصارم. لم تُخفف حماية الاحتمالات أو التنفيذ.

## ما تغير دلاليًا

- `RESEARCH_READY` لا تعني `FORECAST_POLICY_READY`.
- `research_score` لا يعادل `probability`.
- `RESEARCH_CANDIDATE` لا يعادل Buy.
- Source access لا يعادل Source evidence.
- Source quorum لا يعادل Full-market coverage.

وثائق V2 الأصلية محفوظة في `docs/legacy_v2/` للرجوع التاريخي، ولا تصف الوضع الافتراضي الحالي.
