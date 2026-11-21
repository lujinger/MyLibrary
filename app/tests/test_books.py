# D:\project\Python\MyLibrary\app\tests\test_books.py
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from app.models.user import User
from app.models.book import Book

class BookAPITestBase(APITestCase):
    """图书接口测试基类：准备两个用户，封装JWT登录态切换和造书操作"""

    @classmethod
    def setUpTestData(cls):
        """类级别只读数据：在 Django 事务内创建，tearDownClass 自动回滚，不污染后续测试类"""
        cls.user_a = User.objects.create_user(username='alice', password='test12345')
        cls.user_b = User.objects.create_user(username='bob', password='test12345')

    def setUp(self):
        """每个用例默认以 user_a 身份登录；需切换用户时显式调用 auth_as(user_b)"""
        super().setUp()
        self.auth_as(self.user_a)

    def auth_as(self, user):
        """将客户端切换为指定用户的 JWT 登录态"""
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def create_book(self, **overrides):
        """通过API创建一本默认图书，允许覆盖任意字段"""
        payload = {'book_name': '三体', 'author': '刘慈欣'}
        payload.update(overrides)
        return self.client.post(reverse('book-list'), payload, format='json')

class BookCreateAPITests(BookAPITestBase):
    """新增图书"""

    def test_create_without_token_401(self):
        self.client.credentials()
        resp = self.create_book()
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Book.objects.count(), 0)

    def test_create_with_minimal_fields_returns_201(self):
        resp = self.create_book()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        book = Book.objects.get()
        self.assertEqual(book.owner, self.user_a)
        self.assertEqual(book.book_name, '三体')
        self.assertEqual(book.publisher, '未知出版社')
        self.assertEqual(book.permission, 'public')
        self.assertEqual(book.borrow_status, 'available')
        self.assertEqual(book.view_count, 0)

    def test_create_missing_author_returns_400(self):
        resp = self.client.post(reverse('book-list'), {'book_name': '三体'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Book.objects.count(), 0)

    def test_create_invalid_permission_return_400(self):
        resp = self.create_book(permission='everyone')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

class BookListAPITests(BookAPITestBase):
    """图书列表：搜索 / 分页 / 数据隔离"""

    def setUp(self):
        super().setUp()
        self.create_book(book_name='三体', author='刘慈欣')
        self.create_book(book_name='球形闪电', author='刘慈欣')
        self.create_book(book_name='活着是为了快乐', author='余华')

    def test_list_without_token_returns_401(self):
        self.client.credentials()
        resp = self.client.get(reverse('book-list'))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_only_own_books(self):
        self.auth_as(self.user_b)
        self.create_book(book_name='bob的私有书')
        self.auth_as(self.user_a)
        resp = self.client.get(reverse('book-list'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total'], 3)
        names = {item['book_name'] for item in resp.data['items']}
        self.assertNotIn('bob的私有书', names)

    def test_list_search_by_book_name(self):
        resp = self.client.get(reverse('book-list'), {'keyword': '三体'})
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['items'][0]['book_name'], '三体')

    def test_list_search_by_author(self):
        resp = self.client.get(reverse('book-list'), {'keyword': '刘慈欣'})
        self.assertEqual(resp.data['total'], 2)

    def test_list_search_no_match_returns_empty(self):
        resp = self.client.get(reverse('book-list'), {'keyword': '不存在的书名'})
        self.assertEqual(resp.data['total'], 0)
        self.assertEqual(resp.data['items'], [])

    def test_list_pagination(self):
        resp = self.client.get(reverse('book-list'), {'page_size': 2})
        self.assertEqual(resp.data['total'], 3)
        self.assertEqual(len(resp.data['items']), 2)
        resp = self.client.get(reverse('book-list'), {'page': 2, 'page_size': 2})
        self.assertEqual(len(resp.data['items']), 1)

    def test_list_newest_first_ordering(self):
        resp = self.client.get(reverse('book-list'))
        self.assertEqual(resp.data['items'][0]['book_name'], '活着是为了快乐')

    def test_list_invalid_page_param_returns_400(self):
        resp = self.client.get(reverse('book-list'), {'page': 'abc'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_page_size_capped_at_50(self):
        Book.objects.bulk_create([
            Book(book_name=f'批量书{i}', author='批量作者', owner=self.user_a)
            for i in range(60)
        ])
        resp = self.client.get(reverse('book-list'), {'page': 1, 'page_size': 100})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total'], 63)
        self.assertEqual(resp.data['page_size'], 50)
        self.assertEqual(len(resp.data['items']), 50)

class BookDetailAPITests(BookAPITestBase):
    """图书详情 + IDOR 防护"""

    def setUp(self):
        super().setUp()
        self.book_a_id = self.create_book().data['book_id']
        self.auth_as(self.user_b)
        self.book_b_id = self.create_book(book_name='bob的私有书').data['book_id']
        self.auth_as(self.user_a)

    def test_get_own_book_returns_200(self):
        resp = self.client.get(reverse('book-detail', args=[self.book_a_id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['book_id'], self.book_a_id)
        self.assertEqual(resp.data['book_name'], '三体')

    def test_get_without_token_returns_401(self):
        self.client.credentials()
        resp = self.client.get(reverse('book-detail', args=[self.book_a_id]))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_nonexistent_book_returns_404(self):
        resp = self.client.get(reverse('book-detail', args=[99999]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_others_book_returns_404(self):
        resp_other = self.client.get(reverse('book-detail', args=[self.book_b_id]))
        resp_missing = self.client.get(reverse('book-detail', args=[99999]))
        self.assertEqual(resp_other.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp_missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp_other.data, resp_missing.data)

class BookUpdateAPITests(BookAPITestBase):
    """更新图书：PATCH 部分更新 / PUT 全量更新 / 越权防护"""

    def setUp(self):
        super().setUp()
        self.book_a_id = self.create_book().data['book_id']
        self.auth_as(self.user_b)
        self.book_b_id = self.create_book(book_name='bob的私有书').data['book_id']
        self.auth_as(self.user_a)

    def test_patch_partial_update_returns_200(self):
        resp = self.client.patch(
            reverse('book-detail', args=[self.book_a_id]),
            {'book_name': '三体（修订版）'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['book_name'], '三体（修订版）')
        self.assertEqual(resp.data['author'], '刘慈欣')

    def test_patch_invalid_borrow_status_returns_400(self):
        resp = self.client.patch(
            reverse('book-detail', args=[self.book_a_id]),
            {'borrow_status': 'lost'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_full_update_returns_200(self):
        resp = self.client.put(
            reverse('book-detail', args=[self.book_a_id]),
            {'book_name': '三体', 'author': '刘慈欣', 'publisher': '重庆出版社',
             'description': '地球往事三部曲之一', 'permission': 'private'},
            format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['publisher'], '重庆出版社')
        self.assertEqual(resp.data['permission'], 'private')

    def test_put_missing_required_field_returns_400(self):
        resp = self.client.put(
            reverse('book-detail', args=[self.book_a_id]),
            {'author': '刘慈欣'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_others_book_returns_404_and_unchanged(self):
        resp = self.client.put(
            reverse('book-detail', args=[self.book_b_id]),
            {'book_name': '被篡改的书'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Book.objects.get(book_id=self.book_b_id).book_name, 'bob的私有书')

class BookDeleteAPITests(BookAPITestBase):
    """删除图书 + 越权防护"""

    def setUp(self):
        super().setUp()
        self.book_a_id = self.create_book().data['book_id']
        self.auth_as(self.user_b)
        self.book_b_id = self.create_book(book_name='bob的书').data['book_id']
        self.auth_as(self.user_a)

    def test_delete_own_book_returns_204(self):
        resp = self.client.delete(reverse('book-detail', args=[self.book_a_id]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Book.objects.filter(book_id=self.book_a_id).exists())

    def test_delete_others_book_returns_404_and_kept(self):
        resp = self.client.delete(reverse('book-detail', args=[self.book_b_id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Book.objects.filter(book_id=self.book_b_id).exists())