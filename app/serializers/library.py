from rest_framework import serializers

from app.models.book import Book
from app.models.library import Library
from app.serializers.book import BookOutSerializer


class LibraryCreateSerializer(serializers.ModelSerializer):
    """创建自定义馆入参"""

    class Meta:
        model = Library
        fields = ["name", "description"]

class LibraryUpdateSerializer(serializers.ModelSerializer):
    """更新图书馆入参（PUT/PATCH 复用）"""

    class Meta:
        model = Library
        fields = ["name", "description"]

class LibraryOutSerializer(serializers.ModelSerializer):
    """图书馆出参；book_count 来自视图 annotate，未标注时默认 0"""

    book_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Library
        fields = [
            "library_id", "name", "description", "is_default",
            "book_count", "created_at", "updated_at",
        ]
        read_only_fields = fields

class LibraryDetailOutSerializer(serializers.Serializer):
    """图书馆详情：基本信息 + 馆内图书"""

    library = LibraryOutSerializer()
    books = BookOutSerializer(many=True)

class LibraryAddBooksSerializer(serializers.Serializer):
    """移动书入参：请求体里是 book_id 数组"""

    book_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="要移入本馆的 book_id 列表",
    )