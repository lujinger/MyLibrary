from django.db import models

from app.models.user import User

class Book(models.Model):
    """图书表"""

    PERMISSION_CHOICES = (
        ('public', '公开'),
        ('private', '私密'),
        ('friends_only', '仅好友可见'),
    )

    BORROW_STATUS_CHOICES = (
        ('available', '可借'),
        ('borrowed', '已借出'),
    )

    book_id = models.AutoField(primary_key=True, verbose_name="图书ID")
    book_name = models.CharField(max_length=100, db_index=True, verbose_name="图书名称")
    author = models.CharField(max_length=100, db_index=True, verbose_name="作者")
    publisher = models.CharField(max_length=100, default="未知出版社", verbose_name="出版社")
    description = models.TextField(null=True, blank=True, verbose_name="书籍简介")
    cover_url = models.URLField(null=True, blank=True, verbose_name="封面图片URL")
    isbn = models.CharField(max_length=20, null=True, blank=True, verbose_name="ISBN编号")
    permission = models.CharField(max_length=12, choices=PERMISSION_CHOICES, default='public', verbose_name="可见权限")
    borrow_status = models.CharField(max_length=10, choices=BORROW_STATUS_CHOICES, default='available', verbose_name="借阅状态")
    view_count = models.IntegerField(default=0, verbose_name="浏览次数")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='books', verbose_name="书主")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "图书"
        verbose_name_plural = verbose_name
        db_table = 'book'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['book_name']),
            models.Index(fields=['author']),
        ]

    def __str__(self):
        return self.book_name
