from django.http import JsonResponse


def health(request):
    """Liveness probe used by Render's health check and CI smoke tests."""
    return JsonResponse({"status": "ok", "service": "mizan-api"})
