from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

class UserManager(BaseUserManager):
    """自定义用户管理器"""

    def create_user(self, username, password=None, **extra_fields):
        if not username and not extra_fields.get("phone_number"):
            raise ValueError("必须提供用户名或手机号")
        if not username:
            username = f"{extra_fields['phone_number']}"
        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, password, **extra_fields)


class User(AbstractUser):
    user_id = models.AutoField(primary_key=True, verbose_name="用户ID")
    username = models.CharField(max_length=50, unique=True, verbose_name="用户名")
    avatar_url = models.URLField(max_length=255, default="", verbose_name="头像URL")
    phone_number = models.CharField(max_length=11, unique=True, null=True, blank=True, verbose_name="手机号")
    register_time = models.DateTimeField(default=timezone.now, verbose_name="注册时间")

    # 重写 AbstractUser 字段使其可为空
    password = models.CharField(max_length=128, null=True, blank=True, verbose_name="密码")
    first_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="名")
    last_name = models.CharField(max_length=150, null=True, blank=True, verbose_name="姓")
    email = models.EmailField(null=True, blank=True, verbose_name="邮箱")

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = verbose_name
        db_table = "user"

    def __str__(self):
        return self.username
