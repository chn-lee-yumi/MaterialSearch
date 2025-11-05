# Spec Delta: Project Management（项目管理）

## ADDED Requirements

### Requirement: 项目创建
系统 SHALL 允许用户创建新项目，用于组织临时项目文件。

#### Scenario: 成功创建项目
- **WHEN** 用户提供项目名称、客户名称、项目类型等信息
- **THEN** 系统创建项目记录并生成独立的项目数据库文件
- **AND** 返回项目 ID 和项目信息
- **AND** 项目状态设置为"active"

#### Scenario: 项目名称重复
- **WHEN** 用户创建的项目 ID 已存在
- **THEN** 系统返回错误提示"项目已存在"
- **AND** 不创建重复项目

#### Scenario: 必填字段缺失
- **WHEN** 用户未提供项目名称
- **THEN** 系统返回错误提示"项目名称为必填项"
- **AND** 不创建项目

---

### Requirement: 项目列表查询
系统 SHALL 提供项目列表查询功能，支持按状态筛选。

#### Scenario: 查询所有活跃项目
- **WHEN** 用户请求项目列表，状态筛选为"active"
- **THEN** 系统返回所有未删除且状态为"active"的项目
- **AND** 每个项目包含基本信息（ID、名称、客户、图片数、创建时间）
- **AND** 按创建时间倒序排列

#### Scenario: 查询已完成项目
- **WHEN** 用户请求状态为"completed"的项目
- **THEN** 系统返回所有已完成的项目
- **AND** 包含完成时间信息

#### Scenario: 查询所有项目（包括已删除）
- **WHEN** 用户请求所有项目，包含 `include_deleted=true` 参数
- **THEN** 系统返回包括已软删除的项目
- **AND** 标注哪些是已删除状态

---

### Requirement: 项目详情查询
系统 SHALL 允许用户查询单个项目的详细信息和统计数据。

#### Scenario: 查询项目详情
- **WHEN** 用户请求指定项目 ID 的详情
- **THEN** 系统返回项目完整信息
- **AND** 包含统计数据（图片总数、视频总数、总存储大小）
- **AND** 包含最后上传时间
- **AND** 包含项目状态和时间戳（创建/完成/归档时间）

#### Scenario: 项目不存在
- **WHEN** 用户请求的项目 ID 不存在
- **THEN** 系统返回 404 错误
- **AND** 提示"项目不存在"

---

### Requirement: 项目信息更新
系统 SHALL 允许用户更新项目的元信息。

#### Scenario: 更新项目基本信息
- **WHEN** 用户更新项目名称、客户名称或描述
- **THEN** 系统更新项目元信息数据库中的对应记录
- **AND** 返回更新后的项目信息

#### Scenario: 更新项目状态
- **WHEN** 用户将项目状态从"active"更改为"completed"
- **THEN** 系统更新状态字段
- **AND** 记录完成时间（completed_at）
- **AND** 触发统计信息刷新

#### Scenario: 不允许修改项目 ID
- **WHEN** 用户尝试修改项目 ID
- **THEN** 系统拒绝操作并返回错误"项目 ID 不可修改"

---

### Requirement: 项目删除
系统 SHALL 支持项目软删除，保留数据库文件但标记为已删除。

#### Scenario: 软删除项目
- **WHEN** 用户删除一个项目
- **THEN** 系统在元信息数据库中标记 `is_deleted=1`
- **AND** 记录删除时间（deleted_time）
- **AND** 项目数据库文件保留在磁盘上
- **AND** 项目不再出现在默认列表中

#### Scenario: 删除前确认项目为空
- **WHEN** 用户删除包含未归档图片的项目
- **THEN** 系统提示"项目包含 X 张未归档图片，确认删除？"
- **AND** 需要用户二次确认

#### Scenario: 恢复已删除项目
- **WHEN** 用户请求恢复已软删除的项目
- **THEN** 系统将 `is_deleted` 设置为 0
- **AND** 清除 `deleted_time`
- **AND** 项目重新出现在列表中

---

### Requirement: 项目统计信息自动更新
系统 SHALL 在图片/视频上传、删除、归档时自动更新项目统计信息。

#### Scenario: 上传图片后更新统计
- **WHEN** 用户上传图片到项目
- **THEN** 系统增加项目的 `image_count`
- **AND** 增加 `total_size_mb`（按文件大小）
- **AND** 更新 `last_upload_time` 为当前时间

#### Scenario: 归档图片后更新统计
- **WHEN** 用户将项目中的图片归档到永久库
- **THEN** 系统减少项目的 `image_count`
- **AND** 减少 `total_size_mb`
- **AND** 不修改 `last_upload_time`

#### Scenario: 手动刷新统计信息
- **WHEN** 用户请求刷新项目统计
- **THEN** 系统重新扫描项目数据库
- **AND** 计算实际的图片数、视频数、总大小
- **AND** 更新元信息数据库

---

### Requirement: 项目数据库文件管理
系统 SHALL 为每个项目创建独立的 SQLite 数据库文件。

#### Scenario: 项目创建时生成数据库
- **WHEN** 系统创建新项目
- **THEN** 在 `projects/` 目录下创建 `proj_<id>.db` 文件
- **AND** 初始化表结构（image、video 表）
- **AND** 启用 WAL 模式提升并发性能
- **AND** 创建必要的索引

#### Scenario: 数据库文件路径存储
- **WHEN** 项目创建完成
- **THEN** 元信息数据库中记录 `db_path` 字段
- **AND** 路径格式为相对路径（如 `projects/proj_2025_万科_01.db`）

#### Scenario: 项目数据库连接管理
- **WHEN** 用户操作指定项目的数据
- **THEN** 系统根据 `db_path` 动态打开对应数据库连接
- **AND** 使用连接池管理数据库连接
- **AND** 空闲超过 5 分钟的连接自动关闭

---

### Requirement: 项目元信息数据库
系统 SHALL 维护一个独立的元信息数据库（projects_metadata.db）管理所有项目。

#### Scenario: 元信息数据库结构
- **WHEN** 系统初始化
- **THEN** 创建 `projects_metadata.db` 文件
- **AND** 包含 `project` 表，字段包括：
  - id（项目 ID，主键）
  - name（项目名称）
  - client（客户名称）
  - project_type（项目类型）
  - nas_path（NAS 路径）
  - db_path（数据库文件路径）
  - status（状态：active/completed/archived）
  - image_count、video_count、total_size_mb（统计信息）
  - created_at、completed_at、archived_at（时间戳）
  - is_deleted、deleted_time（软删除）

#### Scenario: 元信息一致性保证
- **WHEN** 项目数据库发生变更
- **THEN** 系统同步更新元信息数据库
- **AND** 使用事务保证一致性
- **AND** 更新失败时回滚操作
