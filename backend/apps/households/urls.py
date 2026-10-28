from django.urls import path
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.households.models import Household, Membership
from apps.households.selectors import get_user_households, get_user_membership


class HouseholdSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Household
        fields = ["id", "name", "created_at", "role"]

    def get_role(self, obj):
        user = self.context["request"].user
        membership = get_user_membership(user, obj)
        return membership.role if membership else None


class HouseholdListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        households = get_user_households(request.user)
        serializer = HouseholdSerializer(households, many=True, context={"request": request})
        return Response(serializer.data)


class HouseholdDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        household = Household.objects.filter(id=pk, deleted_at__isnull=True).first()
        if not household or not get_user_membership(request.user, household):
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = HouseholdSerializer(household, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, pk):
        household = Household.objects.filter(id=pk, deleted_at__isnull=True).first()
        if not household:
            return Response(status=status.HTTP_404_NOT_FOUND)
        membership = get_user_membership(request.user, household)
        if not membership or membership.role != Membership.Role.OWNER:
            return Response(status=status.HTTP_403_FORBIDDEN)
        serializer = HouseholdSerializer(household, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "full_name", "role", "created_at"]


class HouseholdMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        household = Household.objects.filter(id=pk, deleted_at__isnull=True).first()
        if not household or not get_user_membership(request.user, household):
            return Response(status=status.HTTP_404_NOT_FOUND)
        memberships = Membership.objects.filter(household=household)
        serializer = MemberSerializer(memberships, many=True)
        return Response(serializer.data)


urlpatterns = [
    path("households/", HouseholdListView.as_view(), name="household-list"),
    path("households/<uuid:pk>/", HouseholdDetailView.as_view(), name="household-detail"),
    path("households/<uuid:pk>/members/", HouseholdMembersView.as_view(), name="household-members"),
]
