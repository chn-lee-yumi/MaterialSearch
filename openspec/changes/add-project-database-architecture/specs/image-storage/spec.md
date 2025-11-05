# Spec Delta: Image Storage（图片存储）

## MODIFIED Requirements

### Requirement: 图片数据库存储
系统 SHALL 支持多数据库架构，分别存储永久库和项目库图片。

#### Scenario: 图片上传到永久库
- **WHEN** 用户上传图片到永久库（target='permanent'）
- **THEN** 系统将图片记录写入 `permanent.db`
- **AND** 提取 CLIP 向量特征并存储到 `features` 字段
- **AND** 计算并存储宽度、高度、宽高比、文件大小等元数据
- **AND** 设置 `source_type='direct'`（直接上传）
- **AND** `upload_time` 设置为当前时间

#### Scenario: 图片上传到项目库
- **WHEN** 用户上传图片到指定项目（target='project_id'）
- **THEN** 系统将图片记录写入对应项目的数据库 `proj_<id>.db`
- **AND** 提取和存储相同的特征数据
- **AND** 额外记录项目特有字段（image_type、stage）
- **AND** 更新项目统计信息

#### Scenario: 上传队列机制
- **WHEN** 多个用户同时上传图片
- **THEN** 系统将上传任务加入队列
- **AND** 后台线程串行处理（避免并发写入冲突）
- **AND** 用户立即收到"已加入处理队列"响应
- **AND** 处理完成后通知用户或更新前端

#### Scenario: 图片路径存储
- **WHEN** 系统存储图片记录
- **THEN** `path` 字段存储 NAS 上的完整路径
- **AND** 路径格式为 `/mnt/nas/项目文件/2025_万科_01/效果图/客厅.jpg`
- **AND** 图片文件不移动，保持原始路径

---

## ADDED Requirements

### Requirement: 图片宽高比计算
系统 SHALL 自动计算并存储图片的宽高比信息，用于 AI 自动排版。

#### Scenario: 计算精确宽高比
- **WHEN** 系统扫描图片时
- **THEN** 计算 `aspect_ratio = width / height`
- **AND** 精确到小数点后 3 位（如 1.778）
- **AND** 存储到 `aspect_ratio` 字段

#### Scenario: 识别标准宽高比
- **WHEN** 计算出精确宽高比后
- **THEN** 系统匹配标准比例（容差 ±5%）
- **AND** 识别常见比例：
  - 1:1（正方形）
  - 4:3（传统横向）
  - 16:9（宽屏横向）
  - 21:9（超宽屏）
  - 3:4（传统竖向）
  - 9:16（宽屏竖向）
  - √2:1（A4 横向）
  - 1:√2（A4 竖向）
- **AND** 存储到 `aspect_ratio_standard` 字段
- **AND** 非标准比例存储为计算值（如"1.85:1"）

#### Scenario: 按宽高比筛选图片
- **WHEN** 用户查询特定宽高比的图片
- **THEN** 系统可按 `aspect_ratio_standard` 精确匹配（如"16:9"）
- **OR** 按 `aspect_ratio` 范围查询（如 1.7 ~ 1.8 之间）

---

### Requirement: 扩展元数据存储
系统 SHALL 为每张图片存储丰富的元数据，支持多维度筛选和管理。

#### Scenario: 文件属性记录
- **WHEN** 系统扫描图片时
- **THEN** 记录以下文件属性：
  - `width`：图片宽度（像素）
  - `height`：图片高度（像素）
  - `file_size`：文件大小（字节）
  - `file_format`：文件格式（jpg/png/heic）
  - `modify_time`：文件修改时间
  - `checksum`：SHA1 哈希值

#### Scenario: 分类和标签
- **WHEN** 用户为图片添加分类信息
- **THEN** 系统存储以下字段：
  - `category`：主分类（如"现代风格"）
  - `sub_category`：子分类（如"客厅"）
  - `tags`：标签数组（JSON 格式，如 `["极简","木饰面"]`）
  - `building_type`：建筑类型（住宅/商业/办公）
  - `design_style`：设计风格（现代/简约/工业）

#### Scenario: 来源信息追溯
- **WHEN** 图片从项目归档到永久库
- **THEN** 系统记录：
  - `source_type='project_archive'`（来源类型）
  - `source_project='proj_2025_万科_01'`（来源项目 ID）
  - `source_notes`：来源备注（可选）

#### Scenario: 质量评级
- **WHEN** 用户为图片评分或标记为精选
- **THEN** 系统存储：
  - `quality_score`：质量评分（0-5 星）
  - `is_featured`：是否精选（布尔值）
  - `last_accessed`：最后访问时间（点击查看时更新）

---

### Requirement: 软删除机制
系统 SHALL 使用软删除而非物理删除图片记录，保留向量数据便于恢复。

#### Scenario: 软删除图片
- **WHEN** 用户删除图片
- **THEN** 系统设置 `is_deleted=1`
- **AND** 记录 `deleted_time` 为当前时间
- **AND** 图片不再出现在默认搜索结果中
- **AND** 数据库记录和向量特征保留

#### Scenario: 恢复已删除图片
- **WHEN** 用户请求恢复已删除的图片
- **THEN** 系统设置 `is_deleted=0`
- **AND** 清除 `deleted_time`
- **AND** 图片重新出现在搜索结果中

#### Scenario: 物理清理
- **WHEN** 管理员执行物理清理操作
- **THEN** 系统删除 `is_deleted=1` 且删除超过 30 天的记录
- **AND** 需要管理员权限确认

---

### Requirement: 去重预留字段
系统 SHALL 预留去重相关字段，为后续去重功能提供数据基础。

#### Scenario: 感知哈希计算
- **WHEN** 系统扫描图片时
- **THEN** 计算感知哈希（perceptual hash）
- **AND** 存储到 `phash` 字段（16 位十六进制字符串）
- **AND** 创建索引支持快速查询

#### Scenario: 重复组标记
- **WHEN** 后续去重功能识别出重复图片
- **THEN** 系统可使用以下字段：
  - `is_duplicate`：标记为重复图片
  - `duplicate_group`：重复组 ID（相同组的图片有相同 ID）

---

### Requirement: AI 增强预留字段
系统 SHALL 预留 AI 描述相关字段，为后续 AI Agent 功能提供支持。

#### Scenario: AI 描述生成
- **WHEN** 后续实现 AI 描述功能
- **THEN** 系统可使用以下字段：
  - `ai_description`：AI 生成的图片描述（文本）
  - `ai_description_vector`：描述的向量化（BLOB）

#### Scenario: 增强检索
- **WHEN** 用户搜索时
- **THEN** 系统可同时匹配：
  - 图片向量（`features`）
  - 描述向量（`ai_description_vector`）
- **AND** 提升检索准确性

---

### Requirement: 数据库索引优化
系统 SHALL 为高频查询字段创建索引，提升检索性能。

#### Scenario: 单列索引
- **WHEN** 系统初始化数据库时
- **THEN** 为以下字段创建索引：
  - `path`（文件路径查询）
  - `checksum`（去重检测）
  - `phash`（感知哈希检测）
  - `category`（分类筛选）
  - `aspect_ratio`（宽高比筛选）
  - `aspect_ratio_standard`（标准比例筛选）
  - `upload_time`（时间范围查询）
  - `is_deleted`（排除已删除）

#### Scenario: 复合索引
- **WHEN** 系统初始化数据库时
- **THEN** 为常见组合查询创建复合索引：
  - `(category, design_style)`：按分类和风格筛选
  - `(aspect_ratio_standard, category)`：按比例和分类筛选
  - `(is_featured, category, is_deleted)`：精选图片筛选

#### Scenario: 索引维护
- **WHEN** 数据库记录增加或删除
- **THEN** 索引自动更新
- **AND** 定期执行 `ANALYZE` 更新统计信息
- **AND** 保持索引性能

---

### Requirement: WAL 模式启用
系统 SHALL 为所有数据库启用 WAL（Write-Ahead Logging）模式，提升并发性能。

#### Scenario: 数据库初始化时启用 WAL
- **WHEN** 系统创建新数据库（永久库或项目库）
- **THEN** 执行 `PRAGMA journal_mode=WAL`
- **AND** 验证 WAL 模式已启用

#### Scenario: WAL 模式的好处
- **WHEN** 多用户同时访问数据库
- **THEN** 读操作不会被写操作阻塞
- **AND** 多个读操作可以并发执行
- **AND** 性能提升约 20-30%

#### Scenario: WAL 文件管理
- **WHEN** 数据库使用 WAL 模式
- **THEN** 系统生成 `.db-wal` 和 `.db-shm` 文件
- **AND** 备份时自动包含这些文件
- **AND** SQLite 自动执行 checkpoint（合并 WAL 到主文件）

---

## MODIFIED Requirements（更新现有需求）

### Requirement: 图片扫描和入库
系统 SHALL 扫描 NAS 上的图片文件，提取特征并入库（更新：增加元数据提取）。

#### Scenario: 扫描新图片
- **WHEN** 系统扫描指定目录
- **THEN** 对每张图片执行：
  - 读取图片并提取 CLIP 向量（512 维）
  - 计算宽度、高度、宽高比、标准比例
  - 计算文件大小、获取文件格式
  - 计算 SHA1 校验和
  - 计算感知哈希（phash）
  - 获取文件修改时间
- **AND** 将所有数据写入数据库（永久库或项目库）
- **AND** 创建缩略图（用于前端展示）

#### Scenario: 增量扫描（检测文件变化）
- **WHEN** 系统重新扫描已入库的图片
- **THEN** 对比 `checksum` 或 `modify_time` 判断文件是否变化
- **AND** 文件未变化则跳过处理
- **AND** 文件已变化则删除旧记录，重新入库

#### Scenario: 扫描失败处理
- **WHEN** 图片文件无法读取（损坏、权限不足、格式不支持）
- **THEN** 系统记录警告日志
- **AND** 跳过该文件继续扫描其他文件
- **AND** 不中断整个扫描流程
