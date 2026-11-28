# 05 · 二期 API 契约（v0.2.0）

> **文档驱动流程**：本文评审通过后才进入 model 层开发；契约即需求，开发全程以本文为依据。
> 本文只写**增量**：一期契约见 [03_API契约](./03_API契约.md)，数据结构见 [02_数据库设计](./02_数据库设计.md)。

## 1. 二期范围回顾

| 能力 | 内容 |
|---|---|
| 借阅审批流 | 系统用户可申请借他人的书，馆主批准/拒绝；批准后自动生成借阅记录 |
| 图书可见性 | `permission` 字段从"预留"转为生效：public 书可被他人浏览与申请 |
| 明确不做 | 好友体系（`friends_only` 三期启用）、借阅排队（书在借即拒申请）、消息通知 |

## 2. 数据结构增量

### 2.1 新表：BorrowRequest（借阅申请）

语义：**申请 = 意图**（谁想借、馆主答不答应），与 `BorrowRecord`（事实：书确实借出）分离。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| request_id | AutoField | PK | |
| book | FK → book | CASCADE | 申请借阅的书 |
| requester | FK → user | CASCADE | 申请发起人（必须是系统用户） |
| due_date | date | 可空 | 希望的归还日期，不得早于今天 |
| message | varchar(200) | 可空 | 申请留言 |
| status | varchar(10) | 默认 pending | `pending / approved / rejected`；**落库**（审批结果无法从任何底层数据派生，与一期"可派生状态用 property"的规范不冲突） |
| decided_at | datetime | 可空 | 批准/拒绝的时间 |
| created_at / updated_at | datetime | auto | ordering: -created_at |

**约束**（部分唯一）：

```python
models.UniqueConstraint(
    fields=["book", "requester"],
    condition=models.Q(status="pending"),
    name="unique_pending_request_per_book_requester",
)
```

含义：同一用户对同一本书最多一条待处理申请（防刷申请）；不同用户可同时 pending 同一本书（馆主择一批准）。DB 层兜底并发，应用层先查重返回友好 400。

### 2.2 增量修改：BorrowRecord 加可空关联

```python
request = models.OneToOneField(
    BorrowRequest, null=True, blank=True,
    on_delete=models.SET_NULL, related_name="borrow_record",
    verbose_name="来源申请",
)
```

- 用途：支撑 `GET /borrow?scope=incoming`（"我借入的"），用外键替代按 `borrower_name` 文本反查（自由文本不可靠，这正是要用外键的原因）。
- **纯增量迁移**：可空列 + 无约束变更 + 无存量回填，一期数据 `request=NULL`（手工登记的记录本来就没有申请）。
- `on_delete=SET_NULL`：申请行被清理时借阅事实保留（事实不随意图消失）。

## 3. 新增接口

**BorrowRequestOut 结构**：

```json
{
  "request_id": 3, "book": 5, "book_name": "三体",
  "requester": 2, "requester_name": "bob",
  "due_date": "2026-12-10", "message": "想借两周",
  "status": "pending", "decided_at": null, "created_at": "..."
}
```

**路由总览**：

| 方法 | 路径 | name | 调用方 | 说明 |
|---|---|---|---|---|
| POST | /borrow-request | borrow-request-create | 申请者 | 发起借阅申请 |
| GET | /borrow-request/sent | borrow-request-sent | 申请者 | 我发出的申请（分页） |
| GET | /borrow-request/received | borrow-request-received | 馆主 | 收到的针对我书的申请（分页） |
| POST | /borrow-request/\<request_id\>/approve | borrow-request-approve | 馆主 | 批准 → 事务内生成借阅记录 |
| POST | /borrow-request/\<request_id\>/reject | borrow-request-reject | 馆主 | 拒绝申请 |

### 3.1 发起申请 `POST /borrow-request`

- 请求体：`{ "book_id": 5, "due_date": "2026-12-10", "message": "想借两周" }`（`due_date`/`message` 可空）
- 校验顺序（顺序即语义，先不可见后业务）：
  1. 书对申请者**可见**（自己的书 或 他人的 public 书）：`get_object_or_404(Book, Q(owner=request.user) | Q(permission="public"), book_id=...)`，否则 `404`
  2. 自己的书 → `400 {"detail": "不能申请借阅自己的图书"}`
  3. 书在借（`borrow_status != available`）→ `400 {"detail": "该书当前已借出，暂不接受申请"}`（不做排队）
  4. 已有同书 pending 申请 → `400 {"detail": "你已有一条待处理的申请，请等待处理"}`
  5. 字段校验：`due_date` 早于今天 → 400 字段级；`message` 超 200 → 400 字段级
- 成功：`201` 返回 `BorrowRequestOut`（status=pending）

### 3.2 我发出的 `GET /borrow-request/sent`

- 过滤：`requester=request.user`；查询参数：`status`（可选，pending/approved/rejected，非法值 400）、`page`/`page_size`
- 成功：`200` 分页结构 `{total, page, page_size, items: BorrowRequestOut[]}`（items 传 queryset 切片，禁止双重序列化）

### 3.3 我收到的 `GET /borrow-request/received`

- 过滤：`book__owner=request.user`（跨表 IDOR 防护：只看得到发给"我的书"的申请）
- 其余同 3.2

### 3.4 批准 `POST /borrow-request/<request_id>/approve`

- 成功：`200` 返回 `BorrowRequestOut`（status=approved）；完整事务时序见第 5 节
- 错误：
  - 申请不存在 / 不是我的书 → `404`（`get_object_or_404(BorrowRequest, request_id=..., book__owner=request.user)`）
  - 已处理过（重复批准/拒绝已 approved 或 rejected 的申请）→ `400 {"detail": "该申请已处理，不能重复操作"}`
  - 书已被借出（含并发穿透，`IntegrityError` 兜底转译）→ `400 {"detail": "该书已被借出，无法批准"}`

### 3.5 拒绝 `POST /borrow-request/<request_id>/reject`

- 成功：`200` 返回 `BorrowRequestOut`（status=rejected, decided_at=now）；单行更新，无书状态变更、无事务包裹需求
- 错误：同 3.4 的 404 与"已处理"400

## 4. 既有接口变更

### 4.1 `GET /borrow`：新增 `scope` 参数

| scope | 过滤条件 | 说明 |
|---|---|---|
| `outgoing`（默认） | `book__owner=request.user` | 我的书被借出的记录——**一期默认行为，零破坏** |
| `incoming` | `request__requester=request.user` | 我通过审批流借入的记录 |

- 非法值 → `400 {"detail": "scope 参数只支持 outgoing / incoming"}`
- 注：`incoming` 只含审批流产生的记录；一期手工登记的记录没有关联申请，不出现（其 `borrower_name` 是自由文本，无法可靠反查）

### 4.2 `GET /book`：新增 `scope=public` 与详情可见性

| 调用 | 行为 |
|---|---|
| `GET /book`（无 scope） | 只返回我的书——一期行为不变 |
| `GET /book?scope=public` | 返回**他人的** public 书：`Q(permission="public") & ~Q(owner=request.user)`，支持 keyword/分页（自己的书走默认列表，避免重复） |
| `GET /book/<book_id>` 自己的书 | `200` 完整信息（一期不变） |
| `GET /book/<book_id>` 他人的 public 书 | `200`（只读浏览；对其的一切**写操作仍 404**） |
| `GET /book/<book_id>` 他人的 private / friends_only 书 | `404`（统一不泄露存在性，沿用一期 IDOR 原则） |

- `permission` 的写入（创建/更新书）一期已支持，无需接口变更；`friends_only` 二期按 private 处理（不可见），三期好友上线后启用。

## 5. 批准事务时序（关键设计）

```text
馆主 POST /borrow-request/<id>/approve
 │
 ├─ 1. get_object_or_404(BorrowRequest, request_id=…, book__owner=me)   → 不是我的书 404
 ├─ 2. request.status != pending                                        → 400 已处理
 ├─ 3. book.borrow_status != available                                  → 400 已被借出
 │
 ├─ 4. transaction.atomic: ──────────────────────────────────────────
 │     4.1  request.status = approved, decided_at = now
 │     4.2  建 BorrowRecord(book, borrower_name=requester.username,
 │                          due_date=request.due_date, request=request)
 │     4.3  book.borrow_status = borrowed
 │     4.4  同书其余 pending 申请 → 批量 update 为 rejected, decided_at = now
 │
 └─ 5. except IntegrityError → 400 "该书已被借出，无法批准"（并发兜底，与一期一致）
```

**为什么批准后要自动拒绝其他 pending**：部分唯一约束保证一书同时仅一条在借——批准 A 之后，其余 pending 永远不可能再被批准。主动拒绝给每个申请者**确定的终态**，避免申请永久挂起；与约束在同一事务内，保证"批准 + 借出 + 其余拒绝"原子生效。

**due_date 不在批准时复检**：申请挂了几天后日期可能已过期，馆主在明示日期的情况下仍批准，视为接受该日期（批准动作本身就是人工复核）。

## 6. 错误码速查

| 场景 | 状态码 | 响应 |
|---|---|---|
| 申请/批准/拒绝目标不存在或非本人资源 | 404 | `{"detail": ...}` |
| 申请自己的书 | 400 | `{"detail": "不能申请借阅自己的图书"}` |
| 书在借时申请 | 400 | `{"detail": "该书当前已借出，暂不接受申请"}` |
| 重复 pending 申请 | 400 | `{"detail": "你已有一条待处理的申请，请等待处理"}` |
| 重复处理已决申请 | 400 | `{"detail": "该申请已处理，不能重复操作"}` |
| 批准时书已被借出（含并发） | 400 | `{"detail": "该书已被借出，无法批准"}` |
| scope/status 参数非法 | 400 | `{"detail": "..."}` |
| due_date 早于今天 / message 超长 | 400 | 字段级 `{"<字段>": ["..."]}` |

## 7. 兼容性承诺（对一期的零破坏）

1. 不带 `scope` 的所有既有请求，行为与 v0.1.0 完全一致。
2. `POST /borrow` 手工登记路径**保留**（借给现实中的朋友、非系统用户的场景）。
3. `BorrowRecord` 仅新增可空关联列：无约束变更、无存量回填，纯增量迁移。
4. 一期 89 个测试**零修改**应全绿——任何失败即回归，修复实现而不是改测试。