# D:\project\Python\MyLibrary\app\views\__init__.py
from app.views.auth import RegisterView, LoginView, MeView
from app.views.book import BookListView, BookDetailView

__all__ = ["RegisterView", "LoginView", "MeView", "BookListView", "BookDetailView"]