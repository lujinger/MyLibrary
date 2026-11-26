from django.db import models

from app.models.book import Book

class BorrowRecord(models.Model):
    """借阅记录：一次借出 = 一条记录，归还只更新 return_date"""

    record_id = models.AutoField(primary_key=True, verbose_name="借阅记录ID")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="borrow_records", verbose_name="借阅图书")
    borrower_name = models.CharField(max_length=50, verbose_name="借阅人")
    borrow_date = models.DateField(auto_now_add=True, verbose_name="借出日期")
    due_date = models.DateField(null=True, blank=True, verbose_name="约定归还日期")
    return_date = models.DateField(null=True, blank=True, verbose_name="实际归还日期")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "借阅记录"
        verbose_name_plural = verbose_name
        db_table = "borrow_record"
        ordering = ["-created_at"]
        constraints = [
            # 数据库级兜底：一本书同一时刻最多只有一条“未归还”记录（部分唯一约束）
            models.UniqueConstraint(
                fields=["book"],
                condition=models.Q(return_date__isnull=True),
                name="unique_active_borrow_per_book"
            ),
        ]

    @property
    def status(self) -> str:
        """状态由 return_date 派生：单一数据源，杜绝状态字段与日期不一致"""
        return "returned" if self.return_date else "borrowing"

    def __str__(self) -> str:
        return f"{self.book.book_name}借给{self.borrower_name}"
