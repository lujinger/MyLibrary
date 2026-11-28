from django.db import models

from app.models.user import User

class Library(models.Model):
    """个人图书馆（书架）：每本书必须归属于一个馆，馆删除时馆内书一并删除"""

    DEFAULT_NAME = "我的图书馆"

    library_id = models.AutoField(primary_key=True, verbose_name="图书馆ID")
    name = models.CharField(max_length=50, verbose_name="图书馆名称")
    description = models.TextField(null=True, blank=True, verbose_name="图书馆描述")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="libraries", verbose_name="所有者")
    is_default = models.BooleanField(default=False, verbose_name="是否默认馆")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "图书馆"
        verbose_name_plural = verbose_name
        db_table = "library"
        # 同一用户下馆名不能重复
        unique_together = [["owner", "name"]]
        ordering = ["-created_at"]

    @classmethod
    def create_default_for_user(cls, user) -> "Library":
        """注册信号调用：为新用户创建默认馆"""
        return cls.objects.create(owner=user, name=cls.DEFAULT_NAME, is_default=True)

    def __str__(self) -> str:
        return self.name
