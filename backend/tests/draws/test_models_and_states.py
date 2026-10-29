import itertools

import pytest
from django.db import IntegrityError, transaction

from apps.draws.models import Denomination, Draw, DrawRevision, OutboxEvent, PrizeTier, WinningNumber
from apps.draws.states import (
    DRAW_TRANSITIONS,
    REVISION_TRANSITIONS,
    IllegalTransition,
    check_draw_transition,
    check_revision_transition,
)
from tests.draws.factories import DrawFactory, NumberFactory, RevisionFactory, TierFactory, denomination

pytestmark = pytest.mark.django_db


def test_seeded_denominations():
    slugs = list(Denomination.objects.values_list("slug", flat=True))
    assert slugs == ["rs-100", "rs-200", "rs-750", "rs-1500", "premium-25000", "premium-40000"]
    premium = denomination("premium-40000")
    assert (premium.value_pkr, premium.kind, premium.number_length) == (40000, "PREMIUM", 6)
    assert premium.source_page_url == "https://savings.gov.pk/premium-prize-bond-rs-40000/"
    assert str(denomination("rs-200")) == "Rs 200 Prize Bond"


def test_draw_uniqueness():
    draw = DrawFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        DrawFactory(denomination=draw.denomination, draw_number=draw.draw_number)
    with pytest.raises(IntegrityError), transaction.atomic():
        DrawFactory(denomination=draw.denomination, draw_date=draw.draw_date)
    # Unknown draw numbers (None) may coexist.
    DrawFactory(draw_number=None)
    DrawFactory(draw_number=None)


def test_revision_uniqueness_per_draw():
    revision = RevisionFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        RevisionFactory(draw=revision.draw, revision_no=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        RevisionFactory(draw=revision.draw, revision_no=2, sha256=revision.sha256)


@pytest.mark.parametrize(
    ("table", "check", "enum"),
    [
        (REVISION_TRANSITIONS, check_revision_transition, DrawRevision.Status),
        (DRAW_TRANSITIONS, check_draw_transition, Draw.Status),
    ],
    ids=["revision", "draw"],
)
def test_every_allowed_transition_passes_and_every_other_raises(table, check, enum):
    for current, target in itertools.product(enum.values, repeat=2):
        if target in table[current]:
            check(current, target)
        else:
            with pytest.raises(IllegalTransition):
                check(current, target)


def test_terminal_states_have_no_exit():
    assert REVISION_TRANSITIONS[DrawRevision.Status.REJECTED] == frozenset()
    assert REVISION_TRANSITIONS[DrawRevision.Status.SUPERSEDED] == frozenset()
    assert DRAW_TRANSITIONS[Draw.Status.PUBLISHED] == frozenset()


def test_revision_is_immutable_once_saved():
    revision = RevisionFactory()
    revision.sha256 = "0" * 64
    with pytest.raises(ValueError, match="immutable"):
        revision.save(update_fields=["sha256"])
    with pytest.raises(ValueError, match="immutable"):
        revision.save()
    revision.review_note = "ok"
    revision.save(update_fields=["review_note"])  # workflow fields may change
    assert DrawRevision.objects.get(pk=revision.pk).review_note == "ok"


def test_database_cascade_from_revision_to_tiers_and_numbers():
    number = NumberFactory()
    revision = number.revision
    assert PrizeTier.objects.filter(revision=revision).count() == 1
    DrawRevision.objects.filter(pk=revision.pk).delete()  # only the DB cascade can remove the children
    assert not PrizeTier.objects.filter(revision=revision).exists()
    assert not WinningNumber.objects.filter(pk=number.pk).exists()


def test_number_unique_per_revision_and_rank_checks():
    tier = TierFactory()
    NumberFactory(tier=tier, number="000001")
    with pytest.raises(IntegrityError), transaction.atomic():
        NumberFactory(tier=tier, number="000001")
    with pytest.raises(IntegrityError), transaction.atomic():
        TierFactory(rank=4)


def test_strs():
    revision = RevisionFactory()
    assert "r1" in str(revision)
    assert "Rs 200" in str(revision.draw)
    assert str(TierFactory()).startswith("rank 1")
    assert str(NumberFactory(number="123456")) == "123456"
    assert "draw.published" in str(OutboxEvent.objects.create(type="draw.published"))
