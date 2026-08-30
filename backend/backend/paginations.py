from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Global list pagination. Page-number based (not cursor/offset) so the
    frontend can drive it with Previous/Next buttons plus a "go to page N"
    input.

    No next/previous URL fields — the frontend tracks the current page as
    state and requests pages by number, so link fields would be dead weight.
    """
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 500

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "total_pages": self.page.paginator.num_pages,
            "current_page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "results": data,
        })
