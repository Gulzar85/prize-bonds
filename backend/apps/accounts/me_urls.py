from django.urls import path
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = None  # Will be set dynamically
        fields = ["id", "email", "full_name", "phone", "preferred_language"]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        serializer = UserSerializer(request.user)
        serializer.Meta.model = User
        return Response(serializer.data)

    def patch(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.Meta.model = User
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


urlpatterns = [
    path("", MeView.as_view(), name="me"),
]
