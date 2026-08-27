# Saudi review — design only, deferred

Status: `DESIGN_ONLY_BLOCKED_UNTIL_KUWAIT_GATES_PASS`

No Saudi collection runtime, training, blind test, forecast, or promotion was
started in this stage. The five review findings are frozen in
`config/saudi-deferred-design-gates.json` and guarded by schema and unit tests:

1. Resolve `source_role` and `rights_status` from a trusted `source_id` registry;
   reject caller-authored values.
2. Keep suspended securities inside the point-in-time universe denominator with
   `tradable=false`.
3. Apply global temporal cutoffs across every cohort and fail closed on leakage.
4. Treat a missing or uncovered official holiday calendar as `BLOCKED`, not an
   empty calendar.
5. Reject an observation when `observed_at > request.known_at`.

Saudi activation remains gated on validated Kuwait training, a passed locked
Blind Test, and a measurement report. Shared software architecture does not
authorize mixed symbols, calendars, market rules, or data stores.
