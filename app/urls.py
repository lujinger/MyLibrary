from django.urls import path
from app.views import RegisterView, LoginView, MeView, BookListView, BookDetailView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path("user/register", RegisterView.as_view(), name="user-register"),
    path("user/login", LoginView.as_view(), name="user-login"),
    path("user/me", MeView.as_view(), name="user-me"),
    # 图书管理
    path("book", BookListView.as_view(), name="book-list"),
    path("book/<int:book_id>", BookDetailView.as_view(), name="book-detail"),
    # API 文档
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")
]
