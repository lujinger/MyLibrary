# D:\project\Python\MyLibrary\app\serializers\library.py
from rest_framework import serializers

from app.models.book import Book
from app.models.library import Library
from app.serializers.book import BookOutSerializer

class LibraryCreateSerializer(serializers.ModelSerializer):
    """创建自定义馆入参"""

    class Meta:
        model = Library
        fields = ["name", "description"]

    def validate(self, attrs):
        # owner 不在 fields 中（由视图 save 时注入），DRF 不会自动生成
        # UniqueTogetherValidator，必须手动校验同一用户下馆名不能重复，
        # 否则重名会落到 DB 层抛 IntegrityError，接口返回 500 而非 400。
        request = self.context.get("request")
        name = attrs.get("name")
        if request and name and Library.objects.filter(owner=request.user, name=name).exists():
            raise serializers.ValidationError({"name": "该图书馆名称已存在"})
        return attrs

class LibraryUpdateSerializer(serializers.ModelSerializer):
    """更新图书馆入参（PUT/PATCH 复用）"""

    class Meta:
        model = Library
        fields = ["name", "description"]

    def validate(self, attrs):
        # 改名时也要查重，但要排除当前馆自身（self.instance）
        request = self.context.get("request")
        name = attrs.get("name")
        if request and name:
            qs = Library.objects.filter(owner=request.user, name=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"name": "该图书馆名称已存在"})
        return attrs

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