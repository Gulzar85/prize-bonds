from rest_framework import permissions


class IsAuthenticated(permissions.IsAuthenticated):
    pass


class IsHouseholdMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return True
