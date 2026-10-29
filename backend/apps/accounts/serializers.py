from rest_framework import serializers

from apps.accounts.models import E164_VALIDATOR, User


class MeSerializer(serializers.ModelSerializer[User]):
    phone = serializers.CharField(max_length=16, required=False, allow_blank=True, validators=[E164_VALIDATOR])

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "preferred_language"]
        read_only_fields = ["id", "email"]
