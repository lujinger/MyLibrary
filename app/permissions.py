from rest_framework import permissions

class IsOwner(permissions.BasePermission):
    """允许对象的所有者进行操作"""

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.pk
