from django import template

register = template.Library()


@register.filter
def get_item(row, key):
    """Dynamic dict lookup for the generic report PDF template — row[key],
    where key is itself a template variable (column.key), not a literal."""
    if row is None:
        return ""
    value = row.get(key, "")
    return "" if value is None else value
