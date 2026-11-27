# 03 · API 契约（v0.1.0）

> 本文与 `app/urls.py` + `app/views/` + `app/serializers/` 逐字段对齐，是接口的权威契约。
> 交互式文档：启动服务后访问 `/docs`（drf-spectacular 生成），原始 schema 见 `/schema`。
> 关联文档：[01_需求与范围](./01_需求与范围.md) · [02_数据库设计](./02_数据库设计.md) · [04_安全与设计决策](./04_安全与设计决策.md)

## 1. 通用约定

**Base URL**：`/`（一期无版本前缀，如需版本化二期加 `/api/v1`）

**认证**：除注册、登录外，所有业务接口要求请求头携带 JWT：

Authorization: Bearer <access_token>

未携带或过期 → `401`。

**内容类型**：请求体均为 `application/json`。

**统一错误格式**（DRF 默认）：
- 字段级校验错误：`{"<字段名>": ["错误信息"]}`，状态码 `400`
- 业务错误：`{"detail": "错误信息"}`，状态码 `400/401/404`
- 未认证：`{"detail": "认证信息未提供或已失效"}`，`401`
- 不存在或越权：统一 `404`（不返回 `403`，见 04 设计决策）

**分页**（图书、借阅列表）：`page` 默认 1，`page_size` 默认 10、最大 50；传非整数 → `400 {"detail": "page 和 page_size 参数必须是正整数"}`。响应结构：
```json
{ "total": 24, "page": 1, "page_size": 10, "items": [ ... ] }
```

## 2. 认证模块（/user）

### 2.1 注册 `POST /user/register`
- 权限：`AllowAny`
- 请求体：
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| username | string(≤50) | 是 | 用户名，全局唯一 |
| password | string(≤128) | 是 | write_only |
| phone_number | string(≤11) | 否 | 手机号，唯一（可空 unique 允许多个 NULL） |
| avatar_url | string(url) | 否 | 不传默认空串 |
- 成功：`201`，返回 `UserOut`（`user_id, username, phone_number, avatar_url, register_time`）
- 副作用：`post_save` 信号自动创建默认馆"我的图书馆"
- 错误：用户名/手机号重复 → `400` 字段级错误

> 注：注册返回用户信息，**不返回 token**；登录后才签发 JWT。

### 2.2 登录 `POST /user/login`
- 权限：`AllowAny`
- 请求体：`{ "username": "...", "password": "..." }`（均 ≤128）
- 成功：`200`
```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```
- 错误：用户名或密码错误 → `401 {"detail": "用户名或密码错误"}`
- Token 有效期：access 30 分钟 / refresh 7 天（见 settings）

### 2.3 当前用户 `GET /user/me`
- 权限：`IsAuthenticated`
- 成功：`200`，返回 `UserOut`

## 3. 图书模块（/book）

**BookOut 结构**：
```json
{
  "book_id": 1, "book_name": "...", "author": "...", "publisher": "...",
  "description": "...", "cover_url": "...", "isbn": "...",
  "permission": "public", "borrow_status": "available", "view_count": 0,
  "library_id": 1, "created_at": "...", "updated_at": "..."
}
```
（`permission` 一期预留，接口可读写但不参与可见性过滤）

### 3.1 列表 `GET /book`
- 权限：`IsAuthenticated`；只返回当前用户的书
- 查询参数：
| 参数 | 类型 | 说明 |
|---|---|---|
| keyword | string | 模糊匹配 `book_name` 或 `author`（`icontains`） |
| library_id | int | 按馆过滤；非整数 → `400 {"detail": "library_id 必须是整数"}` |
| page / page_size | int | 分页（见通用约定） |
- 成功：`200`，分页结构，`items` 为 `BookOut[]`

### 3.2 新增 `POST /book`
- 权限：`IsAuthenticated`
- 请求体：`book_name*, author*, publisher(默认"未知出版社"), description, cover_url, isbn, permission(默认public)`
- 额外参数（不在序列化器白名单，从原始请求读取）：`library_id`
  - 传：必须是自己的馆，否则 `404`（IDOR 防护）
  - 不传：自动放入默认馆
- 成功：`201`，返回 `BookOut`
- 错误：`library_id` 非整数 → `400 {"detail": "library_id 必须是整数"}`

### 3.3 详情 `GET /book/<book_id>`
- 成功：`200` `BookOut`；不存在或不属于本人 → `404`

### 3.4 更新 `PUT /book/<book_id>` / `PATCH /book/<book_id>`
- 入参 `BookUpdateSerializer`：比新增多一个可写字段 `borrow_status`
- 成功：`200` `BookOut`；不存在/越权 → `404`

### 3.5 删除 `DELETE /book/<book_id>`
- 成功：`204`（无响应体）；不存在/越权 → `404`

## 4. 图书馆模块（/library）

**LibraryOut 结构**：
```json
{
  "library_id": 1, "name": "我的图书馆", "description": "...",
  "is_default": true, "book_count": 3, "created_at": "...", "updated_at": "..."
}
```
`book_count` 由视图 `annotate(Count("books"))` 一次查询得到，未命中时默认 0。

### 4.1 列表 `GET /library`
- 成功：`200`，`LibraryOut[]`（含默认馆）

### 4.2 新建 `POST /library`
- 请求体：`{ "name": "...", "description": "..." }`（name ≤50 必填）
- 成功：`201` `LibraryOut`（`is_default=False`）
- 错误：与本人已有馆重名 → `400 {"name": ["该图书馆名称已存在"]}`

### 4.3 详情 `GET /library/<library_id>`
- 成功：`200`
```json
{ "library": { ...LibraryOut }, "books": [ ...BookOut ] }
```
- 不存在/越权 → `404`

### 4.4 更新 `PUT/PATCH /library/<library_id>`
- 请求体同新建；改名时重名校验排除自身
- 成功：`200` `LibraryOut`；重名 → `400`；不存在/越权 → `404`

### 4.5 删除 `DELETE /library/<library_id>`
- 默认馆 → `400 {"detail": "默认图书馆不能删除"}`
- 普通馆 → `204`，**馆内所有书级联删除**（容器语义，CASCADE）
- 不存在/越权 → `404`

### 4.6 批量移书入馆 `POST /library/<library_id>/books`
- 请求体：`{ "book_ids": [1, 2, 3] }`（`allow_empty=False`，空列表 → `400`）
- 只移动当前用户拥有的书；已在馆内的书保持不变（幂等）
- 成功：`200`（无响应体）；馆不存在/越权 → `404`

### 4.7 移书回默认馆 `DELETE /library/<library_id>/books/<book_id>`
- 若目标馆是默认馆 → `400 {"detail": "书已在默认图书馆"}`
- 书必须属于本人且位于该馆，否则 `404`
- 成功：`204`，书的 `library` 改为默认馆

## 5. 借阅模块（/borrow）

**BorrowOut 结构**：
```json
{
  "record_id": 1, "book": 5, "book_name": "...", "borrower_name": "张三",
  "borrow_date": "2026-11-27", "due_date": null, "return_date": null,
  "status": "borrowing", "created_at": "..."
}
```
- `status` 为派生字段：`return_date` 非空 → `returned`，否则 `borrowing`
- `book` 是 book_id（外键序列化默认输出 PK），`book_name` 冗余以便前端无需二次请求

### 5.1 列表 `GET /borrow`
- 权限：`IsAuthenticated`；通过 `book__owner` 跨表反查，只返回本人图书的借阅记录
- 查询参数：
| 参数 | 类型 | 说明 |
|---|---|---|
| status | string | `borrowing`（`return_date IS NULL`）/ `returned`（非空）；非法值 → `400` |
| page / page_size | int | 分页 |
- 成功：`200`，分页结构，`items` 为 `BorrowOut[]`（列表已 `select_related("book")` 防 N+1）

### 5.2 登记借出 `POST /borrow`
- 请求体：
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| book_id | int | 是 | 要出借的书 |
| borrower_name | string(≤50) | 是 | 借阅人姓名（自由文本，非系统用户） |
| due_date | date | 否 | 约定归还日；不得早于今天，否则 `400` 字段级错误 |
- 校验顺序：序列化器校验 → 书必须属于本人（否则 `404`）→ `borrow_status` 必须 `available`（否则 `400`）
- 成功：`201` `BorrowOut`；事务内同时建记录 + 置 `book.borrow_status=borrowed`
- 并发兜底：若应用层校验被并发穿透，DB 部分唯一约束抛 `IntegrityError` → 捕获返回同样的 `400 {"detail": "该书已借出，不能重复借出"}`

### 5.3 归还 `POST /borrow/<record_id>/return`
- 记录必须属于本人（`book__owner` 跨表校验），否则 `404`
- 已归还过（`return_date` 非空）→ `400 {"detail": "该书已归还，不能重复归还"}`
- 成功：`200` `BorrowOut`；事务内写 `return_date=今天` + 恢复 `book.borrow_status=available`

## 6. 接口总览

| 方法 | 路径 | name | 权限 | 说明 |
|---|---|---|---|---|
| POST | /user/register | user-register | 公开 | 注册（返回用户信息） |
| POST | /user/login | user-login | 公开 | 登录（返回 JWT） |
| GET | /user/me | user-me | 登录 | 当前用户 |
| GET | /book | book-list | 登录 | 图书列表（分页/搜索/过滤） |
| POST | /book | book-list | 登录 | 新增图书 |
| GET | /book/\<book_id\> | book-detail | 登录+属主 | 图书详情 |
| PUT/PATCH | /book/\<book_id\> | book-detail | 登录+属主 | 更新图书 |
| DELETE | /book/\<book_id\> | book-detail | 登录+属主 | 删除图书 |
| GET | /library | library-list | 登录 | 图书馆列表 |
| POST | /library | library-list | 登录 | 新建图书馆 |
| GET | /library/\<id\> | library-detail | 登录 | 馆详情（含馆内书） |
| PUT/PATCH | /library/\<id\> | library-detail | 登录 | 更新馆 |
| DELETE | /library/\<id\> | library-detail | 登录 | 删除馆（级联删书） |
| POST | /library/\<id\>/books | library-move-books | 登录 | 批量移书入馆 |
| DELETE | /library/\<id\>/books/\<book_id\> | library-remove-book | 登录 | 移书回默认馆 |
| GET | /borrow | borrow-list | 登录 | 借阅记录列表 |
| POST | /borrow | borrow-list | 登录 | 登记借出 |
| POST | /borrow/\<record_id\>/return | borrow-return | 登录 | 归还 |
| GET | /schema | schema | — | OpenAPI schema 源 |
| GET | /docs | swagger-ui | — | Swagger UI |