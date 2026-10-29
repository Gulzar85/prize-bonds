from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import User
from apps.accounts.serializers import MeSerializer

ME_EXAMPLE = {
    "id": "0192f1c0-7b1e-7c3a-9d52-3f1c2a4b5d6e",
    "email": "ahmed@example.com",
    "full_name": "Ahmed Khan",
    "phone": "+923001234567",
    "preferred_language": "ur",
}


@extend_schema_view(
    get=extend_schema(
        summary="Get my profile",
        examples=[OpenApiExample("Profile", value=ME_EXAMPLE, response_only=True)],
    ),
    patch=extend_schema(
        summary="Update my profile",
        examples=[OpenApiExample("Update", value={"full_name": "Ahmed Khan"}, request_only=True)],
    ),
)
class MeView(generics.RetrieveUpdateAPIView[User]):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self) -> User:
        return self.request.user  # type: ignore[return-value]
