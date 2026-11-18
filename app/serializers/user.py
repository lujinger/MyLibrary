from rest_framework import serializers
from app.models.user import User

class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, max_length=128)
    # ← 显式声明 avatar_url 非必填，避免模型字段缺 blank=True 导致注册 400
    avatar_url = serializers.URLField(required=False, allow_blank=True, default="")

    class Meta:
        model = User
        fields = ["username", "password", "phone_number", "avatar_url"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(max_length=128, write_only=True)

class UserOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["user_id", "username", "phone_number", "avatar_url", "register_time"]
        read_only_fields = fields

class TokenSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField()
