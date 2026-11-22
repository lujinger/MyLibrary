# D:\project\Python\MyLibrary\app\tests\test_auth.py
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from app.models.user import User

def register(client, **overrides):
    """工具方法：调用注册接口，返回响应"""
    payload = {'username': 'alice', 'password': 'test123456'}
    payload.update(overrides)
    return client.post(reverse('user-register'), payload, format='json')

def login(client, **overrides):
    """工具方法：调用登录接口，返回响应"""
    payload = {'username': 'alice', 'password': 'test123456'}
    payload.update(overrides)
    return client.post(reverse('user-login'), payload, format='json')

# ------------------------------ 注册 ------------------------------
class RegisterAPITests(APITestCase):
    def test_register_with_minimal_fields_returns_201(self):
        resp = register(self.client)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['username'], 'alice')
        self.assertIn('user_id', resp.data)
        self.assertEqual(resp.data['avatar_url'], '')

    def test_register_password_is_not_returned(self):
        """密码是 write_only，响应体中绝对不能出现"""
        resp = register(self.client)
        self.assertNotIn('password', resp.data)

    def test_register_persists_user_in_db(self):
        resp = register(self.client)
        user = User.objects.get(username='alice')
        self.assertEqual(user.user_id, resp.data['user_id'])
        self.assertTrue(user.check_password('test123456'))

    def test_register_with_all_fields_returns_201(self):
        resp = register(self.client, phone_number='13800000000',
                        avatar_url='https://example.com/avatar.png')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['phone_number'], '13800000000')
        self.assertEqual(resp.data['avatar_url'], 'https://example.com/avatar.png')

    def test_register_missing_username_returns_400(self):
        resp = self.client.post(reverse('user-register'), {'password': 'test123456'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)

    def test_register_missing_password_returns_400(self):
        resp = self.client.post(reverse('user-register'), {'username': 'alice'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username_returns_400(self):
        register(self.client)
        resp = register(self.client)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 1)

    def test_register_duplicate_phone_number_returns_400(self):
        register(self.client, username='alice', phone_number='13800000000')
        resp = register(self.client, username='bob', phone_number='13800000000')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_avatar_url_returns_400(self):
        resp = register(self.client, avatar_url='not-a-url')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)

# ------------------------------ 登录 ------------------------------
class LoginAPITests(APITestCase):
    def setUp(self):
        super().setUp()
        register(self.client)

    def test_login_success_returns_200(self):
        resp = login(self.client)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', resp.data)
        self.assertIn('refresh_token', resp.data)
        self.assertEqual(resp.data['token_type'], 'bearer')

    def test_login_access_and_refresh_are_different(self):
        resp = login(self.client)
        self.assertNotEqual(resp.data['access_token'], resp.data['refresh_token'])

    def test_login_wrong_password_returns_401(self):
        resp = login(self.client, password='wrongpass')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data['detail'], '用户名或密码错误')

    def test_login_nonexistent_user_returns_401(self):
        resp = login(self.client, username='nobody')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_missing_password_returns_400(self):
        resp = self.client.post(reverse('user-login'), {'username': 'alice'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_missing_username_returns_400(self):
        resp = self.client.post(reverse('user-login'), {'password': 'test123456'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_access_token_can_authenticate_me(self):
        """端到端：注册 -> 登录 -> 用返回的 access token 访问 /me"""
        token = login(self.client).data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        resp = self.client.get(reverse('user-me'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['username'], 'alice')

# ------------------------------ 获取当前用户 / 鉴权 ------------------------------
class MeAPITests(APITestCase):
    def setUp(self):
        super().setUp()
        register(self.client)
        self.access_token = login(self.client).data['access_token']
        self.refresh_token = login(self.client).data['refresh_token']

    def test_me_without_token_returns_401(self):
        resp = self.client.get(reverse('user-me'))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_token_returns_own_info(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        resp = self.client.get(reverse('user-me'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['username'], 'alice')
        self.assertIn('register_time', resp.data)

    def test_me_with_invalid_token_returns_401(self):
        """篡改后的 token（签名不合法）应被拒绝"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}x')
        resp = self.client.get(reverse('user-me'))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_refresh_token_returns_401(self):
        """refresh token 不能用于访问受保护资源（只能换 access token）"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.refresh_token}')
        resp = self.client.get(reverse('user-me'))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_other_users_token_returns_other_user(self):
        """注册第二个用户 bob，用 bob 的 token 访问 /me 应返回 bob 的信息，而不是 alice"""
        register(self.client, username='bob')
        bob_token = login(self.client, username='bob').data['access_token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {bob_token}')
        resp = self.client.get(reverse('user-me'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['username'], 'bob')