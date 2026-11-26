from django.utils import timezone
from rest_framework import serializers

from app.models.borrow import BorrowRecord

class BorrowCreateSerializer(serializers.Serializer):
    """借出图书入参"""

    book_id = serializers.IntegerField(help_text='要出借的图书')
    borrower_name = serializers.CharField(max_length=50, help_text='借阅人姓名')
    due_date = serializers.DateField(
        required=False, allow_null=True, help_text='约定归还日期，不传表示未约定'
    )

    def validate_due_date(self, value):
        # 字段级校验：约定归还日期不能早于今天
        if value and value < timezone.localdate():
            raise serializers.ValidationError('约定归还日期不能早于今天')
        return value

class BorrowOutSerializer(serializers.ModelSerializer):
    """借阅记录出参；附带书名和派生状态，前端无需二次请求"""

    book_name = serializers.CharField(source='book.book_name', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = BorrowRecord
        fields = [
            'record_id', 'book', 'book_name', 'borrower_name',
            'borrow_date', 'due_date', 'return_date', 'status', 'created_at'
        ]
        read_only_fields = fields

    def get_status(self, obj) -> str:
        return obj.status

class BorrowListOutSerializer(serializers.Serializer):
    """借阅记录分页列表响应结构"""

    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    items = BorrowOutSerializer(many=True)
