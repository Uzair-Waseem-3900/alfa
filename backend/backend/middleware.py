from django.http import JsonResponse


class ForceServerErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return JsonResponse(
            {"detail": "Internal Server Error"},
            status=500
        )