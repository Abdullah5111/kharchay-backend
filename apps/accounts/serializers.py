from rest_framework import serializers

class RequestOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=["login", "signup"], default="login")

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    purpose = serializers.ChoiceField(choices=["login", "signup"], default="login")

class UserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.CharField()
    email_verified = serializers.BooleanField(read_only=True)
    avatar_key = serializers.CharField(read_only=True, allow_blank=True)

class DeviceSerializer(serializers.Serializer):
    expo_push_token = serializers.CharField()
    platform = serializers.CharField(required=False, allow_blank=True, default="")
