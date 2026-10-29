"""Meta-test: every view that serves household-owned data must use HouseholdScopedViewMixin."""

from django.db import models
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import generics

from apps.core.household_scoped import HouseholdScopedModel
from apps.core.mixins import HouseholdScopedViewMixin


def _iter_patterns(patterns, prefix=""):  # type: ignore[no-untyped-def]
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _iter_patterns(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p


def _model_of(view_cls):  # type: ignore[no-untyped-def]
    qs = getattr(view_cls, "queryset", None)
    if qs is not None:
        return qs.model
    meta = getattr(getattr(view_cls, "serializer_class", None), "Meta", None)
    return getattr(meta, "model", None)


def _is_scoped_model(model) -> bool:  # type: ignore[no-untyped-def]
    return isinstance(model, type) and issubclass(model, HouseholdScopedModel)


def test_household_scoped_views_use_the_mixin():
    offenders = []
    for route, pattern in _iter_patterns(get_resolver().url_patterns):
        view = getattr(pattern.callback, "cls", None)
        if view is None:
            continue
        needs_mixin = _is_scoped_model(_model_of(view)) or "<uuid:household_id>" in route
        if needs_mixin and not issubclass(view, HouseholdScopedViewMixin):
            offenders.append(route)
    assert not offenders, f"Views missing HouseholdScopedViewMixin: {offenders}"


def test_meta_test_flags_a_violating_view():
    """Guard the guard: a scoped-model view without the mixin must be detectable."""

    class Dummy(HouseholdScopedModel):
        class Meta:
            app_label = "households"

    class Bad(generics.ListAPIView):
        queryset = models.QuerySet(model=Dummy)

    assert _is_scoped_model(_model_of(Bad))
    assert not issubclass(Bad, HouseholdScopedViewMixin)
