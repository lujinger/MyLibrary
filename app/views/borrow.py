from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.models.book import Book
from app.models.borrow import BorrowRecord
from app.serializers.borrow import (
    BorrowCreateSerializer,
    BorrowOutSerializer,
    BorrowListOutSerializer,
)

class BorrowListCreateView(APIView):
    """借阅记录列表 + 借出图书"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='查询借阅记录列表',
        description='返回当前用户所有图书的借阅记录，可按状态过滤',
        parameters=[
            OpenApiParameter(name='status', description='borrowing=借出中 / returned=已归还，不传返回全部', required=False, type=str),
            OpenApiParameter(name='page', description='页码，默认1', required=False, type=int),
            OpenApiParameter(name='page_size', description='每页数量，默认10，最大50', required=False, type=int),
        ],
        responses=BorrowListOutSerializer,
    )
    def get(self, request):
        try:
            page = max(int(request.query_params.get('page', 1)), 1)
            page_size = min(max(int(request.query_params.get('page_size', 10)), 1), 50)
        except ValueError:
            return Response({'detail': 'page 和 page_size 参数必须是正整数'}, status=status.HTTP_400_BAD_REQUEST)

        # 借阅记录通过 book 外键跨表反查 owner（book__owner 跨表归属校验）
        queryset = BorrowRecord.objects.filter(book__owner=request.user)
        status_filter = request.query_params.get('status')
        if status_filter:
            if status_filter == 'borrowing':
                queryset = queryset.filter(return_date__isnull=True)
            elif status_filter == 'returned':
                queryset = queryset.filter(return_date__isnull=False)
            else:
                return Response({'detail': 'status 参数只支持 borrowing 或 returned'}, status=status.HTTP_400_BAD_REQUEST)

        result = {
            'total': queryset.count(),
            'page': page,
            'page_size': page_size,
            'items': BorrowOutSerializer(queryset[(page-1)*page_size:page*page_size], many=True).data
        }
        return Response(BorrowListOutSerializer(result).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='借出图书',
        description='登记借阅记录并把图书状态置为已借出；书不存在/不属于你返回的404，书已借出返回400',
        request=BorrowCreateSerializer,
        responses=BorrowOutSerializer,
    )
    def post(self, request):
        serializer = BorrowCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # 带 owner 条件查询：别人的书 -> 统一 404（IDOR防护）
        book = get_object_or_404(Book, book_id=data['book_id'], owner=request.user)
        if book.borrow_status != 'available':
            return Response({'detail': '该书已借出，不能重复借出'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                record = BorrowRecord.objects.create(
                    book=book,
                    borrower_name=data['borrower_name'],
                    due_date=data.get('due_date'),
                )
                book.borrow_status = 'borrowed'
                book.save(update_fields=['borrow_status'])
        except IntegrityError:
            # 数据库唯一约束兜底：并发场景下试图校验可能同时通过，约束保证数据不脏
            return Response({'detail': '该书已借出，不能重复借出'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BorrowOutSerializer(record).data, status=status.HTTP_201_CREATED)

class BorrowReturnView(APIView):
    """归还图书"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='归还图书',
        description='登记归还日期并把图书状态恢复为可借；记录不存在/不属于你返回的404，归还已归还的书返回400',
        request=None,
        responses=BorrowOutSerializer,
    )
    def post(self, request, record_id: int):
        # book__owner 跨表条件：记录不存在 / 是不是我的 -> 统一 404（IDOR防护）
        record = get_object_or_404(BorrowRecord, record_id=record_id, book__owner=request.user)
        if record.return_date:
            return Response({'detail': '该书已归还，不能重复归还'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            record.return_date = timezone.localdate()
            record.save(update_fields=['return_date'])
            book = record.book
            book.borrow_status = 'available'
            book.save(update_fields=['borrow_status'])
        return Response(BorrowOutSerializer(record).data, status=status.HTTP_200_OK)
