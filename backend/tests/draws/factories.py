import datetime
import hashlib

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.draws.models import Denomination, Draw, DrawRevision, PrizeTier, WinningNumber


def denomination(slug: str = "rs-200") -> Denomination:
    """The seeded denominations (data migration) are the canonical ones."""
    return Denomination.objects.get(slug=slug)


class DrawFactory(DjangoModelFactory):
    class Meta:
        model = Draw

    denomination = factory.LazyFunction(denomination)
    draw_number = factory.Sequence(lambda n: n + 1)
    draw_date = factory.Sequence(lambda n: datetime.date(2020, 1, 1) + datetime.timedelta(days=n))
    city = "Karachi"


class RevisionFactory(DjangoModelFactory):
    class Meta:
        model = DrawRevision

    draw = factory.SubFactory(DrawFactory)
    revision_no = 1
    source_url = "https://savings.gov.pk/wp-content/uploads/2026/09/x.txt"
    file_ext = "txt"
    sha256 = factory.Sequence(lambda n: hashlib.sha256(str(n).encode()).hexdigest())
    size_bytes = 100
    storage_key = factory.Sequence(lambda n: f"draws/raw/{n}.txt")
    fetched_at = factory.LazyFunction(timezone.now)
    extraction_method = DrawRevision.Extraction.TXT


class TierFactory(DjangoModelFactory):
    class Meta:
        model = PrizeTier

    revision = factory.SubFactory(RevisionFactory)
    rank = 1
    amount_pkr = 750000
    announced_count = 1
    parsed_count = 1


class NumberFactory(DjangoModelFactory):
    class Meta:
        model = WinningNumber

    tier = factory.SubFactory(TierFactory)
    revision = factory.SelfAttribute("tier.revision")
    draw = factory.SelfAttribute("tier.revision.draw")
    denomination = factory.SelfAttribute("tier.revision.draw.denomination")
    number = factory.Sequence(lambda n: f"{n:06d}")
