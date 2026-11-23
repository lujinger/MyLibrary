from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.models.book import Book
from app.models.library import Library
from app.serializers.book import BookOutSerializer
from app.serializers.library import (
    LibraryCreateSerializer,
    LibraryUpdateSerializer,
    LibraryOutSerializer,
    LibraryDetailOutSerializer,
    LibraryAddBooksSerializer,
)

class LibraryListView(APIView):
    """我的图书馆列表 + 创建自定义馆"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="查询我的图书馆列表",
        description="获取当前用户的所有图书馆，包括默认馆和自定义馆",
        responses=LibraryOutSerializer(many=True)
    )
    def get(self, request):
        # annotate 一次 SQL 拿到每馆 book_count，避免逐馆 count（N+1）
        qs = Library.objects.filter(owner=request.user).annotate(book_count=Count("books"))
        return Response(LibraryOutSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="创建自定义图书馆",
        description="创建一个自定义馆，馆名和描述由用户填写",
        request=LibraryCreateSerializer,
        responses=LibraryOutSerializer,
    )
    def post(self, request):
        serializer = LibraryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        library = serializer.save(owner=request.user, is_default=False)
        return Response(LibraryOutSerializer(library).data, status=status.HTTP_201_CREATED)

class LibraryDetailView(APIView):
    """图书馆详情 + 更新 + 删除"""

    permission_classes = [IsAuthenticated]

    def get_object(self, library_id: int) -> Library:
        # 查询带 owner 条件：不存在 / 不属于我 -> 统一 404（IDOR防护）
        # annotate 让详情响应也带 book_count
        return get_object_or_404(
            Library.objects.annotate(book_count=Count("books")),
            library_id=library_id, owner=self.request.user,
        )

    @extend_schema(
        summary="查询图书馆详情",
        description="查询指定图书馆的详情，包括馆内所有图书",
        responses=LibraryDetailOutSerializer
    )
    def get(self, request, library_id: int):
        library = self.get_object(library_id)
        books = Book.objects.filter(owner=request.user, library=library)
        result = {
            "library": LibraryOutSerializer(library).data,
            "books": BookOutSerializer(books, many=True).data,
        }
        return Response(LibraryDetailOutSerializer(result).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="全量更新图书馆信息",
        request=LibraryUpdateSerializer,
        responses=LibraryOutSerializer
    )
    def put(self, request, library_id: int):
        return self._update(request, library_id, partial=False)

    @extend_schema(
        summary="部分更新图书馆信息",
        request=LibraryUpdateSerializer,
        responses=LibraryOutSerializer
    )
    def patch(self, request, library_id: int):
        return self._update(request, library_id, partial=True)

    @extend_schema(
        summary="删除自定义图书馆（馆内书一并删除，默认馆不可删）",
        responses=None
    )
    def delete(self, request, library_id: int):
        library = self.get_object(library_id)
        if library.is_default:
            return Response({"detail": "默认图书馆不能删除"}, status=status.HTTP_400_BAD_REQUEST)
        # Book.library 的 on_delete = CASCADE：删馆连带删掉馆内所有书
        library.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _update(self, request, library_id: int, partial: bool):
        library = self.get_object(library_id)
        serializer = LibraryUpdateSerializer(library, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(LibraryOutSerializer(library).data, status=status.HTTP_200_OK)

class LibraryBookActionView(APIView):
    """把书移动到指定图书馆 / 把书移回默认馆"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="把一批书移动到该馆",
        description='请求体：{"book_ids": [1, 2, 3]}。书必须属于当前用户；已在馆内的书保持不变（幂等）。',
        request=LibraryAddBooksSerializer,
        responses={200: None}
    )
    def post(self, request, library_id: int):
        library = get_object_or_404(Library, library_id=library_id, owner=request.user)
        serializer = LibraryAddBooksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 只圈定当前用户拥有的书，update(library=library) 即"移动"语义
        Book.objects.filter(
            owner=request.user, book_id__in=serializer.validated_data["book_ids"]
        ).update(library=library)
        return Response(status=status.HTTP_200_OK)

    @extend_schema(
        summary="把一本书移回默认馆",
        responses=None
    )
    def delete(self, request, library_id: int, book_id: int):
        library = get_object_or_404(Library, library_id=library_id, owner=request.user)
        if library.is_default:
            return Response({"detail": "书已在默认图书馆"}, status=status.HTTP_400_BAD_REQUEST)
        book = get_object_or_404(Book, book_id=book_id, owner=request.user, library=library)
        default_library = get_object_or_404(Library, owner=request.user, is_default=True)
        book.library = default_library
        book.save(update_fields=["library"])
        return Response(status=status.HTTP_204_NO_CONTENT)