# D:\project\Python\MyLibrary\app\views\book.py
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.models.book import Book
from app.permissions import IsOwner
from app.serializers.book import (
    BookCreateSerializer,
    BookUpdateSerializer,
    BookOutSerializer,
    BookListOutSerializer,
)

class BookListView(APIView):
    """我的图书列表 + 新增图书"""

    permission_classes = [IsAuthenticated]
    serializer_class = BookCreateSerializer

    @extend_schema(
        summary="查询我的图书列表",
        description="按书名/作者模糊搜索，分页返回当前登录用户创建的图书",
        parameters=[
            OpenApiParameter(name='keyword', description='搜索关键词（匹配书名或作者）', required=False, type=str),
            OpenApiParameter(name='page', description='页码，默认1', required=False, type=int),
            OpenApiParameter(name='page_size', description='每页数量，默认10，最大50', required=False, type=int),
        ],
        responses=BookListOutSerializer,
    )
    def get(self, request):
        keyword = request.query_params.get('keyword', '').strip()
        try:
            page = max(int(request.query_params.get('page', 1)), 1)
            page_size = min(max(int(request.query_params.get('page_size', 10)), 1), 50)
        except ValueError:
            return Response({'detail': 'page 和 page_size 参数必须是正整数'}, status=status.HTTP_400_BAD_REQUEST)

        # 数据隔离：只查询当前登录用户的图书
        queryset = Book.objects.filter(owner=request.user)
        if keyword:
            queryset = queryset.filter(Q(book_name__icontains=keyword) | Q(author__icontains=keyword))

        result = {
            'total': queryset.count(),
            'page': page,
            'page_size': page_size,
            'items': BookOutSerializer(queryset[(page-1)*page_size:page*page_size], many=True).data,
        }
        return Response(BookListOutSerializer(result).data, status=status.HTTP_200_OK)

    @extend_schema(summary="新增图书", request=BookCreateSerializer, responses=BookOutSerializer)
    def post(self, request):
        serializer = BookCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        book = serializer.save(owner=request.user)
        return Response(BookOutSerializer(book).data, status=status.HTTP_201_CREATED)

class BookDetailView(APIView):
    """图书详情 / 更新 / 删除"""

    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = BookUpdateSerializer

    def get_object(self, book_id: int) -> Book:
        # 查询时直接带上 owner 条件：书不存在 / 属于他人 → 均返回 404，
        # 避免 403 泄露 book_id 是否真实存在（IDOR 信息泄露）。
        return get_object_or_404(Book, book_id=book_id, owner=self.request.user)

    @extend_schema(summary="查询图书详情", responses=BookOutSerializer)
    def get(self, request, book_id: int):
        book = self.get_object(book_id)
        return Response(BookOutSerializer(book).data, status=status.HTTP_200_OK)

    @extend_schema(summary="全量更新图书", request=BookUpdateSerializer, responses=BookOutSerializer)
    def put(self, request, book_id: int):
        return self._update(request, book_id, partial=False)

    @extend_schema(summary="部分更新图书", request=BookUpdateSerializer, responses=BookOutSerializer)
    def patch(self, request, book_id: int):
        return self._update(request, book_id, partial=True)

    @extend_schema(summary="删除图书", responses=None)
    def delete(self, request, book_id: int):
        book = self.get_object(book_id)
        book.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _update(self, request, book_id: int, partial: bool):
        book = self.get_object(book_id)
        serializer = BookUpdateSerializer(book, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BookOutSerializer(book).data, status=status.HTTP_200_OK)