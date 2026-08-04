from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.utils import get_current_org

from . import services


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000)


class AskView(APIView):
    """Answer a natural-language question, grounded in the org's ledger data."""

    def post(self, request):
        payload = AskSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        org = get_current_org(request)
        result = services.answer_question(org, payload.validated_data["question"])
        return Response(result, status=status.HTTP_200_OK)
