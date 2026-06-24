from rest_framework.exceptions import NotFound

from .models import Organization


def get_current_org(request):
    """
    Resolve the active organization for a request.

    Scaffold behavior: read an explicit `X-Org-Id` header, else fall back to the
    first organization (single-tenant dev/seed). When Clerk auth lands, this is
    replaced by the org bound to the authenticated user's session — the tenant
    boundary is centralized here so every view inherits it.
    """
    org_id = request.headers.get("X-Org-Id")
    if org_id:
        try:
            return Organization.objects.get(pk=org_id)
        except (Organization.DoesNotExist, ValueError):
            raise NotFound("Organization not found.")
    org = Organization.objects.order_by("id").first()
    if org is None:
        raise NotFound("No organization exists yet. Seed demo data first.")
    return org
