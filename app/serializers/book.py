from rest_framework import serializers

from app.models.book import Book

class BookCreateSerializer(serializers.ModelSerializer):
    """新增图书入参"""

    class Meta:
        model = Book
        fields = [
            'book_name',
                  'author',
                  'publisher',
                  'description',
                  'cover_url',
                  'isbn',
                  'permission'
        ]

class BookUpdateSerializer(serializers.ModelSerializer):
    """更新图书入参，PUT 全量更新 / PATCH 部分更新"""

    class Meta:
        model = Book
        fields = [
            'book_name',
                  'author',
                  'publisher',
                  'description',
                  'cover_url',
                  'isbn',
                  'permission'
        ]

class BookOutSerializer(serializers.ModelSerializer):
    """图书出参"""

    class Meta:
        model = Book
        fields = [
            'book_id',
            'book_name',
            'author',
            'publisher',
            'description',
            'cover_url',
            'isbn',
            'permission',
            'borrow_status',
            'view_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

class BookListOutSerializer(serializers.Serializer):
    """图书分页列表响应结构，同时用于运行时输出和 swagger 文档"""

    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    items = BookOutSerializer(many=True)
