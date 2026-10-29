from typing import Any

from rest_framework import serializers

from apps.draws.models import Denomination, Draw, PrizeTier, WinningNumber

MAX_NUMBERS = 50
MAX_RANGES = 5
MAX_RANGE_SIZE = 1000


class DenominationSerializer(serializers.ModelSerializer[Denomination]):
    class Meta:
        model = Denomination
        fields = ["slug", "value_pkr", "kind", "name_en", "name_ur", "number_length"]
        read_only_fields = fields


class DrawSummarySerializer(serializers.ModelSerializer[Draw]):
    denomination = serializers.SlugRelatedField(slug_field="slug", read_only=True)  # type: ignore[var-annotated]
    denomination_value = serializers.IntegerField(source="denomination.value_pkr", read_only=True)
    revised = serializers.SerializerMethodField(help_text="True when the published result replaced an earlier revision")

    class Meta:
        model = Draw
        fields = ["id", "denomination", "denomination_value", "draw_number", "draw_date", "city", "revised"]
        read_only_fields = fields

    def get_revised(self, obj: Draw) -> bool:
        revision = obj.published_revision
        return bool(revision and revision.revision_no > 1)


class TierSerializer(serializers.ModelSerializer[PrizeTier]):
    count = serializers.IntegerField(source="parsed_count", read_only=True)
    numbers = serializers.SerializerMethodField(help_text="Listed for the first and second prize only; see /numbers/")

    class Meta:
        model = PrizeTier
        fields = ["rank", "amount_pkr", "count", "numbers"]
        read_only_fields = fields

    def get_numbers(self, obj: PrizeTier) -> list[str] | None:
        if obj.rank == 3:
            return None
        return sorted(n.number for n in obj.numbers.all())


class DrawDetailSerializer(DrawSummarySerializer):
    published_at = serializers.DateTimeField(read_only=True, help_text="When the result was first published here")
    revised_at = serializers.DateTimeField(read_only=True, allow_null=True)
    source_url = serializers.CharField(read_only=True, allow_null=True)
    tiers = TierSerializer(many=True, read_only=True, source="published_tiers")

    class Meta(DrawSummarySerializer.Meta):
        fields = [*DrawSummarySerializer.Meta.fields, "published_at", "revised_at", "source_url", "tiers"]
        read_only_fields = fields


class PublicNumberSerializer(serializers.ModelSerializer[WinningNumber]):
    tier = serializers.IntegerField(source="tier.rank", read_only=True)

    class Meta:
        model = WinningNumber
        fields = ["number", "tier"]
        read_only_fields = fields


class CheckRequestSerializer(serializers.Serializer[Any]):
    denomination = serializers.SlugRelatedField(slug_field="slug", queryset=Denomination.objects.filter(is_active=True))
    numbers = serializers.ListField(
        child=serializers.RegexField(r"^\d+$", max_length=10),
        required=False,
        max_length=MAX_NUMBERS,
        help_text=f"Up to {MAX_NUMBERS} bond numbers, digits only, zero padded to the denomination's length",
    )
    ranges = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(max_length=10), allow_empty=False),
        required=False,
        max_length=MAX_RANGES,
        help_text=(
            f"Up to {MAX_RANGES} inclusive ranges of at most {MAX_RANGE_SIZE} numbers each, "
            "e.g. {'from': '123400', 'to': '123499'}"
        ),
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        denomination: Denomination = attrs["denomination"]
        length = denomination.number_length
        numbers: list[str] = attrs.get("numbers", [])
        raw_ranges: list[dict[str, str]] = attrs.get("ranges", [])
        if not numbers and not raw_ranges:
            raise serializers.ValidationError("Provide at least one number or one range.")

        for number in numbers:
            if len(number) != length:
                raise serializers.ValidationError({"numbers": f"{number!r} must be exactly {length} digits."})

        ranges: list[tuple[str, str]] = []
        for index, item in enumerate(raw_ranges):
            if set(item) != {"from", "to"}:
                raise serializers.ValidationError({"ranges": f"Range {index + 1} needs exactly 'from' and 'to'."})
            start, end = item["from"], item["to"]
            if not (start.isdigit() and end.isdigit() and len(start) == length and len(end) == length):
                raise serializers.ValidationError({"ranges": f"Range {index + 1} must use {length}-digit numbers."})
            if int(end) < int(start):
                raise serializers.ValidationError({"ranges": f"Range {index + 1}: 'to' is before 'from'."})
            if int(end) - int(start) + 1 > MAX_RANGE_SIZE:
                raise serializers.ValidationError(
                    {"ranges": f"Range {index + 1} is larger than {MAX_RANGE_SIZE} numbers."}
                )
            ranges.append((start, end))
        attrs["numbers"] = list(dict.fromkeys(numbers))
        attrs["ranges"] = ranges
        return attrs


class WinSerializer(serializers.Serializer[Any]):
    number = serializers.CharField()
    draw_id = serializers.UUIDField()
    draw_number = serializers.IntegerField(allow_null=True)
    draw_date = serializers.DateField()
    tier = serializers.IntegerField()
    amount_pkr = serializers.IntegerField()
