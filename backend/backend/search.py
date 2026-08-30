"""
THE project-wide search implementation.

Every user-facing search/filter in every app goes through search_q() —
selectors must never spell out a text-match lookup themselves. This is the
single place the substring lookup lives, so search behavior is uniform
across the project and there is exactly one spot to evolve it.

Behavior: case-insensitive substring match across the given fields
(term "ali" matches "Ali Traders", "REALIST", ...). On PostgreSQL/Supabase
this compiles to UPPER(col) LIKE UPPER('%term%'), which is served by the
pg_trgm GIN expression indexes required for every searched column (see
instructions/architecture.md "Indexed search always") — index-backed
search, no table scans. On SQLite (dev) the same lookup just works.
"""

from django.db.models import Q


def search_q(term, *fields) -> Q:
    """
    Build a Q matching `term` as a case-insensitive substring in ANY of
    `fields` (which may be join paths, e.g. "supplier__name").

    Returns an empty Q (matches everything) for None/blank terms, so
    callers can filter unconditionally — though most guard first to skip
    the filter entirely.
    """
    if term is None:
        return Q()
    term = str(term).strip()
    if not term:
        return Q()

    q = Q()
    for field in fields:
        q |= Q(**{f"{field}__icontains": term})
    return q
