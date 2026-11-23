from django.urls import path
from app.views import (
    RegisterView, LoginView, MeView,
    BookListView, BookDetailView,
    LibraryListView, LibraryDetailView, LibraryBookActionView,
)
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("user/register", RegisterView.as_view(), name="user-register"),
    path("user/login", LoginView.as_view(), name="user-login"),
    path("user/me", MeView.as_view(), name="user-me"),
    # 图书管理
    path("book", BookListView.as_view(), name="book-list"),
    path("book/<int:book_id>", BookDetailView.as_view(), name="book-detail"),
    # 个人图书馆
    path("library", LibraryListView.as_view(), name="library-list"),
    path("library/<int:library_id>", LibraryDetailView.as_view(), name="library-detail"),
    path("library/<int:library_id>/books", LibraryBookActionView.as_view(), name="library-move-books"),
    path("library/<int:library_id>/books/<int:book_id>", LibraryBookActionView.as_view(), name="library-remove-book"),
    # API 文档
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")
]