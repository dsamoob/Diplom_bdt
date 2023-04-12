from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.type == 'staff'


class IsCneeShpr(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.type in ['cnee', 'shpr', 'shpr/cnee']


