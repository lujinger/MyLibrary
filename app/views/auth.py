from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from app.models.user import User
from app.serializers.user import (
    TokenSerializer,
    UserLoginSerializer,
    UserOutSerializer,
    UserRegisterSerializer,
)

def _get_tokens(user: User) -> dict:
    """生成 JWT access + refresh token。"""
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "token_type": "bearer",
    }

@extend_schema(request=UserRegisterSerializer, responses=UserOutSerializer)
class RegisterView(APIView):
    """用户注册"""
    permission_classes = [AllowAny]
    serializer_class = UserRegisterSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserOutSerializer(user).data, status=status.HTTP_201_CREATED)

@extend_schema(request=UserLoginSerializer, responses=TokenSerializer)
class LoginView(APIView):
    """用户登录，返回 JWT"""
    permission_classes = [AllowAny]
    serializer_class = UserLoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "用户名或密码错误"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        # ← TokenSerializer 真正参与运行时：序列化 token 数据为响应
        return Response(
            TokenSerializer(_get_tokens(user)).data,
            status=status.HTTP_200_OK,
        )

@extend_schema(responses=UserOutSerializer)
class MeView(APIView):
    """获取当前登录用户信息"""
    permission_classes = [IsAuthenticated]
    serializer_class = UserOutSerializer

    def get(self, request):
        return Response(self.serializer_class(request.user).data, status=status.HTTP_200_OK)