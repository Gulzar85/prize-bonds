from rest_framework import serializers

from apps.households.models import Household, Membership


class HouseholdSerializer(serializers.ModelSerializer[Household]):
    role = serializers.ChoiceField(choices=Membership.Role.choices, read_only=True)

    class Meta:
        model = Household
        fields = ["id", "name", "role", "created_at"]
        read_only_fields = fields


class HouseholdUpdateSerializer(serializers.Serializer[Household]):
    name = serializers.CharField(max_length=255, trim_whitespace=True)


class MemberSerializer(serializers.ModelSerializer[Membership]):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "email", "full_name", "role", "created_at"]
        read_only_fields = fields
