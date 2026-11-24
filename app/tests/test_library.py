# D:\project\Python\MyLibrary\app\tests\test_library.py
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from app.models.user import User
from app.models.book import Book
from app.models.library import Library

class LibraryAPITestBase(APITestCase):
    """图书馆接口测试基类：复用用户准备 + 登录态切换"""

    @classmethod
    def setUpTestData(cls):
        # create_user 触发 post_save 信号 -> 自动为 alice / bob 各建一个默认馆
        cls.user_a = User.objects.create_user(username='alice', password='test12345')
        cls.user_b = User.objects.create_user(username='bob', password='test12345')

    def setUp(self):
        super().setUp()
        self.auth_as(self.user_a)
        self.default_library_a = Library.objects.get(owner=self.user_a, is_default=True)
        self.default_library_b = Library.objects.get(owner=self.user_b, is_default=True)

    def auth_as(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def create_book(self, **overrides):
        """通过 API 建书，自动归当前用户默认馆"""
        payload = {'book_name': '三体', 'author': '刘慈欣'}
        payload.update(overrides)
        return self.client.post(reverse('book-list'), payload, format='json')

    def create_library(self, name='科幻小说', description='经典科幻'):
        return self.client.post(
            reverse('library-list'),
            {'name': name, 'description': description},
            format='json',
        )

class LibrarySignalTests(LibraryAPITestBase):
    """post_save 信号：新用户自动拥有默认馆"""

    def test_user_auto_has_default_library(self):
        # setUpTestData 中 create_user 已触发信号
        self.assertTrue(Library.objects.filter(owner=self.user_a, is_default=True).exists())
        self.assertTrue(Library.objects.filter(owner=self.user_b, is_default=True).exists())
        lib = Library.objects.get(owner=self.user_a, is_default=True)
        self.assertEqual(lib.name, Library.DEFAULT_NAME)
        self.assertEqual(lib.name, '我的图书馆')

    def test_user_has_exactly_one_default_library(self):
        defaults = Library.objects.filter(owner=self.user_a, is_default=True)
        self.assertEqual(defaults.count(), 1)

class LibraryCreateListAPITests(LibraryAPITestBase):
    """图书馆列表 + 创建"""

    def setUp(self):
        super().setUp()
        self.create_book(book_name='三体')
        self.create_book(book_name='球形闪电')
        # 造一个自定义馆，用来验证 book_count 在自定义馆和默认馆之间分布
        resp = self.create_library(name='科幻')
        self.custom_library_a_id = resp.data['library_id']

    def test_list_without_token_401(self):
        self.client.credentials()
        resp = self.client.get(reverse('library-list'))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_default_and_custom(self):
        resp = self.client.get(reverse('library-list'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item['name'] for item in resp.data]
        self.assertIn('我的图书馆', names)
        self.assertIn('科幻', names)
        self.assertEqual(len(resp.data), 2)

    def test_list_default_library_is_marked(self):
        resp = self.client.get(reverse('library-list'))
        default = next(item for item in resp.data if item['is_default'] is True)
        custom = next(item for item in resp.data if item['is_default'] is False)
        self.assertEqual(default['name'], '我的图书馆')
        self.assertEqual(custom['name'], '科幻')

    def test_list_book_count_annotated(self):
        # 两本书都在默认馆（建自定义馆时没移动书，所以默认馆 book_count=2，自定义馆=0）
        resp = self.client.get(reverse('library-list'))
        default_item = next(item for item in resp.data if item['is_default'] is True)
        custom_item = next(item for item in resp.data if item['is_default'] is False)
        self.assertEqual(default_item['book_count'], 2)
        self.assertEqual(custom_item['book_count'], 0)

    def test_create_library_duplicate_name_returns_400(self):
        resp = self.create_library(name='科幻')  # 同名已存在
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_library_success_returns_201(self):
        resp = self.create_library(name='历史')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['name'], '历史')
        self.assertFalse(resp.data['is_default'])

    def test_create_library_empty_name_returns_400(self):
        resp = self.client.post(reverse('library-list'), {'name': ''}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

class LibraryDetailUpdateAPITests(LibraryAPITestBase):
    """图书馆详情 + 更新 + IDOR"""

    def setUp(self):
        super().setUp()
        self.create_book(book_name='三体')
        # 建自定义馆并移动一本书进去
        resp = self.create_library(name='科幻')
        self.custom_library_id = resp.data['library_id']
        self.book_id = Book.objects.get(
            owner=self.user_a, library=self.default_library_a
        ).book_id
        self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': [self.book_id]}, format='json',
        )
        # 切换到 bob 造他的自定义馆（跨用户 IDOR 用）
        self.auth_as(self.user_b)
        bob_resp = self.create_library(name='bob的科幻')
        self.custom_library_bob_id = bob_resp.data['library_id']
        self.auth_as(self.user_a)

    def test_get_detail_includes_books(self):
        resp = self.client.get(reverse('library-detail', args=[self.custom_library_id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['library']['library_id'], self.custom_library_id)
        self.assertEqual(len(resp.data['books']), 1)
        self.assertEqual(resp.data['books'][0]['book_name'], '三体')

    def test_get_others_library_returns_404(self):
        """跨用户探测 bob 的自定义馆 -> 统一 404（IDOR）"""
        resp_other = self.client.get(reverse('library-detail', args=[self.custom_library_bob_id]))
        resp_missing = self.client.get(reverse('library-detail', args=[99999]))
        self.assertEqual(resp_other.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp_missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp_other.data, resp_missing.data)

    def test_patch_library_returns_200(self):
        resp = self.client.patch(
            reverse('library-detail', args=[self.custom_library_id]),
            {'description': '已更新的描述'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['description'], '已更新的描述')

    def test_update_default_library_allowed(self):
        """默认馆只能改名/改描述，不能删；改名是允许的"""
        resp = self.client.patch(
            reverse('library-detail', args=[self.default_library_a.library_id]),
            {'name': 'Alice的藏书架'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['name'], 'Alice的藏书架')
        self.assertTrue(resp.data['is_default'])

class LibraryDeleteAPITests(LibraryAPITestBase):
    """删除：默认馆保护 + 自定义馆级联删书"""

    def setUp(self):
        super().setUp()
        self.create_book(book_name='三体')
        self.create_book(book_name='球形闪电')
        resp = self.create_library(name='科幻')
        self.custom_library_id = resp.data['library_id']
        self.book_a_id = Book.objects.filter(owner=self.user_a).first().book_id
        self.book_b_id = Book.objects.filter(owner=self.user_a).last().book_id
        # 移动 book_b 到自定义馆，book_a 留在默认馆
        self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': [self.book_b_id]}, format='json',
        )

    def test_delete_default_library_returns_400(self):
        resp = self.client.delete(
            reverse('library-detail', args=[self.default_library_a.library_id])
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # 书还在
        self.assertEqual(Book.objects.filter(owner=self.user_a).count(), 2)

    def test_delete_custom_library_cascades_books(self):
        """删自定义馆 -> 馆内书一并删除，默认馆的书不受影响"""
        resp = self.client.delete(
            reverse('library-detail', args=[self.custom_library_id])
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # 自定义馆消失了
        self.assertFalse(Library.objects.filter(library_id=self.custom_library_id).exists())
        # 书 B 被级联删除（原来在自定义馆）
        self.assertFalse(Book.objects.filter(book_id=self.book_b_id).exists())
        # 书 A 还在默认馆（不受影响）
        self.assertTrue(Book.objects.filter(book_id=self.book_a_id).exists())

class LibraryBookActionAPITests(LibraryAPITestBase):
    """图书移动：批量移动（幂等、跨用户过滤）+ 移回默认馆"""

    def setUp(self):
        super().setUp()
        self.create_book(book_name='三体')
        self.create_book(book_name='球形闪电')
        self.create_book(book_name='活着')
        resp = self.create_library(name='科幻')
        self.custom_library_id = resp.data['library_id']
        self.books_in_default = list(Book.objects.filter(owner=self.user_a, library=self.default_library_a))
        self.book_ids = [b.book_id for b in self.books_in_default]
        # bob 也有书，用来测试跨用户过滤
        self.auth_as(self.user_b)
        self.create_book(book_name='bob的书')
        self.bob_book_id = Book.objects.get(owner=self.user_b).book_id
        self.auth_as(self.user_a)

    def test_move_books_to_custom_library(self):
        """把 3 本书全部移动到自定义馆"""
        resp = self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': self.book_ids}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # 验证归属变更
        for b in Book.objects.filter(owner=self.user_a):
            self.assertEqual(b.library_id, self.custom_library_id)

    def test_move_books_idempotent(self):
        """已在馆内的书再次移动 -> 静默忽略"""
        self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': self.book_ids}, format='json',
        )
        resp = self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': self.book_ids[:1]}, format='json',  # 再移一次
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # 书数量不变，每本书只在一个馆
        self.assertEqual(Book.objects.filter(owner=self.user_a).count(), 3)

    def test_move_books_ignores_others_books(self):
        """混入 bob 的 book_id -> 只移动自己的书，bob 的不受影响"""
        all_ids = self.book_ids + [self.bob_book_id]
        resp = self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': all_ids}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # alice 的 3 本都移过去了
        self.assertEqual(
            Book.objects.filter(owner=self.user_a, library_id=self.custom_library_id).count(), 3
        )
        # bob 的书还在 bob 的默认馆
        self.auth_as(self.user_b)
        bob_book = Book.objects.get(book_id=self.bob_book_id)
        self.assertEqual(bob_book.library, self.default_library_b)
        self.auth_as(self.user_a)

    def test_move_books_to_others_library_returns_404(self):
        # 跨用户探测：不存在的馆（或别人的馆）→ 统一 404
        resp = self.client.post(
            reverse('library-move-books', args=[99999]),
            {'book_ids': self.book_ids[:1]}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_remove_book_from_custom_library_back_to_default(self):
        """先移动 -> 再移回 -> 回到默认馆"""
        self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': self.book_ids[:1]}, format='json',
        )
        book = Book.objects.get(book_id=self.book_ids[0])
        self.assertEqual(book.library_id, self.custom_library_id)
        # 移回默认馆（用 library-remove-book 路由，接受 2 个参数）
        resp = self.client.delete(
            reverse('library-remove-book',
                    args=[self.custom_library_id, self.book_ids[0]]),
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        book.refresh_from_db()
        self.assertEqual(book.library_id, self.default_library_a.library_id)

    def test_remove_book_from_default_library_returns_400(self):
        """对默认馆调用"移回默认馆" -> 书已在默认馆，返回 400"""
        resp = self.client.delete(
            reverse('library-remove-book',
                    args=[self.default_library_a.library_id, self.book_ids[0]])
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_move_books_empty_list_returns_400(self):
        # 该端点只注册了 POST/DELETE；空列表由 serializer 的 allow_empty=False 拦截为 400
        resp = self.client.post(
            reverse('library-move-books', args=[self.custom_library_id]),
            {'book_ids': []}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)