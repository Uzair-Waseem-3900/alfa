# Verification checklist (required, not optional)

Before step 1: if this is the first `migrate` this session, or DATABASES/
`.env` may have changed, read `instructions/database-safety.md` FIRST —
`migrate`/`makemigrations` are not safe to run on autopilot.

1. `python manage.py check`, then `makemigrations`/`migrate` (local dev DB only, unless the user has explicitly confirmed the target).
2. Run relevant `backfill_*` command(s), sanity-check numbers manually.
3. Test through the **actual API view** (`APIRequestFactory` + `force_authenticate`), not just the service function — bugs have hidden at the view/serializer layer before.
4. Confirm 403 for non-admin on anything new.
5. Clean up test data, re-run backfill command(s) to confirm idempotency (numbers return to baseline).
6. **For any list/detail endpoint you touched (new field, new nested serializer, new `select_related`/`prefetch_related`), count the actual queries — don't eyeball it.** This is what catches the "serializer blast radius" bug in `architecture.md`. Quick pattern:

   ```python
   from django.conf import settings
   settings.DEBUG = True  # required for connection.queries to populate
   from django.db import connection, reset_queries
   from rest_framework.test import APIRequestFactory, force_authenticate

   reset_queries()
   request = APIRequestFactory().get("/the/endpoint/", {"page_size": 25})
   force_authenticate(request, user=some_staff_user)
   response = TheView.as_view()(request)
   print(len(connection.queries))  # a 25-row list should be a small fixed number, not 25+N
   ```

   A paginated list should hover around 2–4 queries regardless of page content. If it's proportional to the number of rows returned, that's an N+1 — find the missing `select_related`/`prefetch_related` before moving on, per `architecture.md`'s 200ms rule.
