import inspect
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.utils import get_current_org

from . import services, exporters


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"Invalid date '{raw}'; use YYYY-MM-DD.")


def _jsonable(report):
    """Convert Decimal cells / meta to strings for the JSON response."""
    def conv(v):
        return str(v) if isinstance(v, Decimal) else v

    return {
        **report,
        "rows": [{**r, "cells": [conv(c) for c in r["cells"]]} for r in report["rows"]],
    }


class ReportListView(APIView):
    def get(self, request):
        return Response({"reports": sorted(services.REPORTS.keys())})


class ReportView(APIView):
    """Generate a report as JSON (default), Excel (?format=xlsx), or PDF (?format=pdf)."""

    def get(self, request, key):
        fn = services.REPORTS.get(key)
        if fn is None:
            raise NotFound(f"Unknown report '{key}'.")
        org = get_current_org(request)

        start = _parse_date(request.query_params.get("start"))
        end = _parse_date(request.query_params.get("end"))
        candidate = {"start": start, "end": end, "as_of": end or date.today()}
        accepted = set(inspect.signature(fn).parameters)
        kwargs = {k: v for k, v in candidate.items() if k in accepted}

        report = fn(org, **kwargs)

        # NB: `?export=` (not `?format=`) — DRF reserves `format` for content
        # negotiation, so using it here would 404 before reaching this code.
        fmt = request.query_params.get("export", "json").lower()
        if fmt == "json":
            return Response(_jsonable(report))
        if fmt not in exporters.EXTENSIONS:
            raise ValidationError("export must be one of: json, xlsx, pdf.")

        ext, content_type, builder = exporters.EXTENSIONS[fmt]
        payload = builder(report)
        response = HttpResponse(payload, content_type=content_type)
        filename = f"{org.name.replace(' ', '_')}_{key}.{ext}"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
