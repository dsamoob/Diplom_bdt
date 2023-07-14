from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.type == 'staff'


class IsCneeShpr(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.type in ['cnee', 'shpr/cnee', 'shpr']


class IsShprorCnShpr(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.type in ['shpr', 'shpr/cnee']


class IsCnee(BasePermission):

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.type in ['cnee', 'shpr/cnee']

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user
