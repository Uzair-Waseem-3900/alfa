# Performance Review — Strict Process Rules

These rules govern HOW a performance/scalability review must be run. They override the default "plan first" behavior with a stricter, explicit gate.

1. Do not modify anything by yourself.
2. First inspect and analyze the codebase.
3. Create a detailed plan of recommended changes.
4. Clearly explain why each change is needed and how it improves scalability/performance.
5. Point out anything that can become a bottleneck when data increases.
6. Do not assume anything. If an important decision requires information not yet provided, ask first.
7. **Plan first → ask for approval → only then execute.**
8. Never execute changes before explicit approval.
9. **Never change business logic.** Optimizations must be behavior-preserving: same
   numbers, same statuses, same API responses, same user-visible rules. If a
   performance fix genuinely requires changing business behavior (different
   response shape, different filter semantics, different rounding, new/removed
   side effects), do NOT implement it — flag it to the user as a separate
   decision and wait for explicit approval of the behavior change itself.
