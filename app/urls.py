from django.urls import path
from app.views import RegisterView, LoginView, MeView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path("user/register", RegisterView.as_view(), name="user-register"),
    path("user/login", LoginView.as_view(), name="user-login"),
    path("user/me", MeView.as_view(), name="user-me"),
    # API 文档
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")
]
