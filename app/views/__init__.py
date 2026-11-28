# D:\project\Python\MyLibrary\app\views\__init__.py
from app.views.auth import RegisterView, LoginView, MeView
from app.views.book import BookListView, BookDetailView
from app.views.library import LibraryListView, LibraryDetailView, LibraryBookActionView
from app.views.borrow import BorrowListCreateView, BorrowReturnView

__all__ = ["RegisterView", "LoginView", "MeView", "BookListView", "BookDetailView",
           "LibraryListView", "LibraryDetailView", "LibraryBookActionView",
           "BorrowListCreateView", "BorrowReturnView"]
