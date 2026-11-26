from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from app.models import User
from app.models.book import Book
from app.models.borrow import BorrowRecord

class BorrowAPITestBase(APITestCase):
    """借阅接口测试基类：复用用户准备 + 登录态切换 + 常用动作封装"""

    @classmethod
    def setUpTestData(cls):
        # create_user 触发 post_save 信号 ->自动为 alice / bob 各建默认馆
        cls.user_a = User.objects.create_user(username="alice", password="teat12345")
        cls.user_b = User.objects.create_user(username="bob", password="teat12345")

    def setUp(self):
        super().setUp()
        self.auth_as(self.user_a)

    def auth_as(self, user):
        """切换当前测试用例的登录用户"""
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def create_book(self, book_name='三体', author='刘慈欣'):
        """通过 API 建书。返回 book——id（属默认归当前用户默认馆、状态available）"""
        resp = self.client.post(
            reverse('book-list'),
            {'book_name': book_name, 'author': author},
            format='json'
        )
        return resp.data['book_id']

    def borrow(self, book_id, borrower_name='张三', **overrides):
        """借出图书"""
        payload = {'book_id': book_id, 'borrower_name': borrower_name}
        payload.update(overrides)
        return self.client.post(reverse('borrow-list'), payload, format='json')

    def return_book(self, return_id):
        """归还图书"""
        return self.client.post(reverse('borrow-return', args=[return_id]))

class BorrowCreateAPITests(BorrowAPITestBase):
    """借出图书"""

    def setUp(self):
        super().setUp()
        self.book_id = self.create_book()

    def test_borrow_success_returns_201(self):
        resp = self.borrow(self.book_id, borrower_name='张三')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['book'], self.book_id)
        self.assertEqual(resp.data['borrower_name'], '张三')
        self.assertEqual(resp.data['status'], 'borrowing')
        self.assertIsNone(resp.data['return_date'])
        self.assertEqual(resp.data['book_name'], '三体')

    def test_borrow_updates_book_status(self):
        """借出后书状态必须变为 borrowed （真正启用 borrow_status 字段）"""
        self.borrow(self.book_id)
        book = Book.objects.get(book_id=self.book_id)
        self.assertEqual(book.borrow_status, 'borrowed')

    def test_borrow_without_token_401(self):
        self.client.credentials()
        resp = self.borrow(self.book_id)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_borrow_nonexistent_book_404(self):
        resp = self.borrow(99999)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_borrow_others_books_404(self):
        """跨用户借书 -> 统一 404（IDOR防护）"""
        self.auth_as(self.user_b)
        bob_book = self.create_book('bob的书')
        self.auth_as(self.user_a)
        resp = self.borrow(bob_book)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(BorrowRecord.objects.filter(book_id=bob_book).exists())

    def test_borrow_already_borrowed_book_400(self):
        self.borrow(self.book_id)
        resp = self.borrow(self.book_id)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # 只应有一条记录，没有产生脏数据
        self.assertEqual(BorrowRecord.objects.filter(book_id=self.book_id).count(), 1)

    def test_borrow_due_date_in_past_400(self):
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        resp = self.borrow(self.book_id, due_date=past)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(BorrowRecord.objects.filter(book_id=self.book_id).exists())

    def test_borrow_due_date_optional_201(self):
        future = (timezone.localdate() + timedelta(days=1)).isoformat()
        resp = self.borrow(self.book_id, due_date=future)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['due_date'], future)

    def test_borrow_missing_borrower_name_400(self):
        resp = self.client.post(
            reverse('borrow-list'), {'book_id': self.book_id}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

class BorrowReturnAPITests(BorrowAPITestBase):
    """归还图书"""

    def setUp(self):
        super().setUp()
        self.book_id = self.create_book()
        self.record_id = self.borrow(self.book_id).data['record_id']

    def test_return_success_200(self):
        resp = self.return_book(self.record_id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'returned')
        self.assertEqual(resp.data['return_date'], timezone.localdate().isoformat())

    def test_return_restores_book_status(self):
        """归还后书状态必须恢复为 available"""
        self.return_book(self.record_id)
        book = Book.objects.get(book_id=self.book_id)
        self.assertEqual(book.borrow_status, 'available')

    def test_return_twice_400(self):
        self.return_book(self.record_id)
        resp = self.return_book(self.record_id)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_return_others_record_404(self):
        """跨用户归还 -> 统一 404（IDOR防护）"""
        self.auth_as(self.user_b)
        resp = self.return_book(self.record_id)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # 记录未被归还，书状态仍为 borrowed
        record = BorrowRecord.objects.get(record_id=self.record_id)
        self.assertIsNone(record.return_date)

    def test_return_noneexistent_record_404(self):
        resp = self.return_book(99999)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_borrow_again_after_return_201(self):
        """归还后同一本书可以再次借出"""
        self.return_book(self.record_id)
        resp = self.borrow(self.book_id, borrower_name='李四')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'borrowing')
        # 同一本书共两条历史记录：一条已还，一条在借
        self.assertEqual(BorrowRecord.objects.filter(book_id=self.book_id).count(), 2)

class BorrowListAPITests(BorrowAPITestBase):
    """借阅记录列表 + 状态过滤 + 分页"""

    def setUp(self):
        super().setUp()
        self.book1 = self.create_book('三体')
        self.book2 = self.create_book('球形闪电')
        self.record1 = self.borrow(self.book1).data['record_id']
        self.record2 = self.borrow(self.book2).data['record_id']
        # 把 record2 归还，制造 borrowing / returned 两种状态
        self.return_book(self.record2)

    def test_list_withon_token_401(self):
        self.client.credentials()
        resp = self.client.get(reverse('borrow-list'))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_only_own_records(self):
        """bob 的借阅记录不应出现在 alice 的列表里"""
        self.auth_as(self.user_b)
        bob_book = self.create_book('bob的书')
        self.borrow(bob_book)
        self.auth_as(self.user_a)

        resp = self.client.get(reverse('borrow-list'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total'], 2)
        books = [item['book'] for item in resp.data['items']]
        self.assertNotIn(bob_book, books)

    def test_list_filter_borrowing(self):
        resp = self.client.get(reverse('borrow-list'), {'status': 'borrowing'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['items'][0]['record_id'], self.record1)
        self.assertEqual(resp.data['items'][0]['status'], 'borrowing')

    def test_list_filter_returned(self):
        resp = self.client.get(reverse('borrow-list'), {'status': 'returned'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total'], 1)
        self.assertEqual(resp.data['items'][0]['record_id'], self.record2)
        self.assertEqual(resp.data['items'][0]['status'], 'returned')

    def test_list_invalid_status_400(self):
        resp = self.client.get(reverse('borrow-list'), {'status': 'abc'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_pagination(self):
        # 再借一本书，共3条记录（book1 在借、book2 已还、book3 在借）
        book3 = self.create_book('活着')
        self.borrow(book3)
        resp = self.client.get(reverse('borrow-list'), {'page': 1, 'page_size': 2})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total'], 3)
        self.assertEqual(resp.data['page'], 1)
        self.assertEqual(resp.data['page_size'], 2)
        self.assertEqual(len(resp.data['items']), 2)

class BorrowCascadeTests(BorrowAPITestBase):
    """级联删除：删书 -> 借阅记录一并删除"""

    def test_delete_book_cascades_records(self):
        book_id = self.create_book()
        record_id = self.borrow(book_id).data['record_id']
        self.assertTrue(BorrowRecord.objects.filter(record_id=record_id).exists())

        resp = self.client.delete(reverse('book-detail', args=[book_id]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # 借阅记录随书级联删除（Book.borrow_records 的 on_delete=CASCADE）
        self.assertFalse(BorrowRecord.objects.filter(record_id=record_id).exists())
