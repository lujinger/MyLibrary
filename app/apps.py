from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app'

    def ready(self):
        # 注册 post_save 信号：用户创建成功后自动创建默认图书馆
        from app import signals  # noqa: F401
