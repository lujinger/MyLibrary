from django.db.models.signals import post_save
from django.dispatch import receiver

from app.models.user import User
from app.models.library import Library

@receiver(post_save, sender=User)
def create_default_library(sender, instance, created, raw, **kwargs):
    # raw=True 表示数据来自 fixtures / 迁移脚本加载，跳过
    if created and not raw:
        Library.create_default_for_user(instance)
