from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "type", "title", "body", "data", "read", "created_at"]

    def get_read(self, obj):
        return obj.read_at is not None
