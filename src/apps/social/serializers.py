from rest_framework import serializers
from apps.accounts.serializers import UserSerializer


class FriendRequestCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)


class MembershipSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    role = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
