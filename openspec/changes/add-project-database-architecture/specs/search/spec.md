# Spec Delta: Search（搜索功能）

## MODIFIED Requirements

### Requirement: 图片搜索
系统 SHALL 支持在指定库（永久库、项目库、全局）中进行图片搜索。

#### Scenario: 永久库搜索
- **WHEN** 用户选择永久库进行搜索（library_type='permanent'）
- **THEN** 系统仅在 `permanent.db` 中搜索
- **AND** 计算搜索文本或图片的向量
- **AND** 与永久库中所有图片的 `features` 向量计算余弦相似度
- **AND** 返回相似度最高的 N 张图片
- **AND** 结果中标注 `source='permanent'`
- **AND** 排除 `is_deleted=1` 的图片

#### Scenario: 项目库搜索
- **WHEN** 用户选择指定项目进行搜索（library_type='project', project_id='proj_xxx'）
- **THEN** 系统打开对应项目的数据库 `proj_xxx.db`
- **AND** 仅在该项目库中搜索
- **AND** 计算向量相似度并返回结果
- **AND** 结果中标注 `source='project'` 和 `project_name='xxx'`
- **AND** 排除 `is_deleted=1` 和 `archived=1` 的图片

#### Scenario: 全局搜索（可选功能）
- **WHEN** 用户选择全局搜索（library_type='all'）
- **THEN** 系统搜索永久库 + 所有项目库
- **AND** 合并所有库的搜索结果
- **AND** 按相似度统一排序
- **AND** 结果中标注每张图片的来源（permanent / project_name）
- **AND** 性能警告：可能较慢

#### Scenario: 默认搜索行为（向后兼容）
- **WHEN** 用户不指定 `library_type` 参数
- **THEN** 系统默认搜索永久库
- **AND** 保持与旧版本的兼容性

---

### Requirement: 文本搜图
系统 SHALL 支持用户通过自然语言描述搜索图片（更新：指定搜索范围）。

#### Scenario: 在永久库中文本搜图
- **WHEN** 用户输入搜索文本"现代简约风格的客厅"，选择永久库
- **THEN** 系统使用 CLIP 模型将文本编码为向量
- **AND** 与永久库中所有图片向量计算相似度
- **AND** 返回相似度高于阈值的图片
- **AND** 默认阈值为 36 分（可调）
- **AND** 按相似度降序排列

#### Scenario: 在项目库中文本搜图
- **WHEN** 用户在指定项目中输入搜索文本
- **THEN** 系统仅搜索该项目的图片
- **AND** 返回该项目内的匹配结果
- **AND** 性能优势：仅扫描约 100 张图片，响应速度 < 1 秒

#### Scenario: 搜索结果为空
- **WHEN** 没有图片的相似度高于阈值
- **THEN** 系统返回空结果列表
- **AND** 提示"未找到匹配的图片，尝试调整搜索词或降低阈值"

---

### Requirement: 以图搜图
系统 SHALL 支持用户上传图片查找相似图片（更新：指定搜索范围）。

#### Scenario: 在永久库中以图搜图
- **WHEN** 用户上传参考图片，选择永久库
- **THEN** 系统提取参考图片的 CLIP 向量
- **AND** 与永久库中所有图片向量计算相似度
- **AND** 返回相似度高于阈值（默认 85 分）的图片
- **AND** 排除参考图片本身（如果在库中）

#### Scenario: 在项目库中以图搜图
- **WHEN** 用户在指定项目中上传参考图片
- **THEN** 系统仅在该项目库中搜索相似图片
- **AND** 常见用途：查找同一场景的不同版本

#### Scenario: 使用数据库中的图片进行搜索
- **WHEN** 用户点击某张图片的"查找相似"按钮
- **THEN** 系统根据该图片的 `image_id` 获取其 `features` 向量
- **AND** 无需重新提取向量，直接使用数据库中的向量
- **AND** 在当前选择的库（永久库或项目库）中搜索

---

### Requirement: 视频搜索
系统 SHALL 支持在视频中搜索特定片段（更新：指定搜索范围）。

#### Scenario: 在永久库中视频搜索
- **WHEN** 用户输入搜索文本或上传图片，选择视频搜索，范围为永久库
- **THEN** 系统在永久库的 `video` 表中搜索
- **AND** 与每一帧的 `features` 向量计算相似度
- **AND** 返回匹配的视频片段（包含视频路径和时间范围）
- **AND** 合并相邻帧为同一片段（间隔 ≤ 2×FRAME_INTERVAL）

#### Scenario: 在项目库中视频搜索
- **WHEN** 用户在指定项目中进行视频搜索
- **THEN** 系统仅搜索该项目的 `video` 表
- **AND** 返回该项目内的匹配视频片段

---

## ADDED Requirements

### Requirement: 高级筛选条件
系统 SHALL 支持基于元数据的高级筛选条件，结合向量搜索提供精准结果。

#### Scenario: 按宽高比筛选
- **WHEN** 用户搜索时添加宽高比筛选（如 `aspect_ratio_standard='16:9'`）
- **THEN** 系统先用 SQL 筛选符合宽高比的图片
- **AND** 在筛选后的结果中进行向量相似度计算
- **AND** 提升搜索精准度和性能

#### Scenario: 按分类筛选
- **WHEN** 用户搜索时指定分类（如 `category='现代风格'`）
- **THEN** 系统先筛选该分类的图片
- **AND** 在筛选结果中计算向量相似度

#### Scenario: 按上传时间范围筛选
- **WHEN** 用户搜索时指定时间范围（如"最近一周"）
- **THEN** 系统添加 SQL 条件 `WHERE upload_time >= <start_date>`
- **AND** 在时间范围内的图片中搜索

#### Scenario: 组合多个筛选条件
- **WHEN** 用户同时指定多个筛选条件
  - 例如：`category='效果图'` AND `aspect_ratio_standard='16:9'` AND `building_type='住宅'`
- **THEN** 系统用 SQL 的 AND 条件组合筛选
- **AND** 在满足所有条件的图片中进行向量搜索
- **AND** 大幅减少需要计算相似度的图片数量

---

### Requirement: 搜索结果来源标注
系统 SHALL 在搜索结果中清晰标注每张图片的来源。

#### Scenario: 标注永久库图片
- **WHEN** 搜索结果包含永久库的图片
- **THEN** 结果中包含字段：
  - `source_type='permanent'`
  - `source_label='永久库'`
- **AND** 如果图片是从项目归档来的，额外标注 `source_project`

#### Scenario: 标注项目库图片
- **WHEN** 搜索结果包含项目库的图片
- **THEN** 结果中包含字段：
  - `source_type='project'`
  - `project_id='proj_2025_万科_01'`
  - `project_name='2025万科城市之光项目'`
  - `source_label='项目: 2025万科城市之光'`

#### Scenario: 全局搜索结果混合展示
- **WHEN** 用户进行全局搜索
- **THEN** 结果中混合永久库和多个项目的图片
- **AND** 每张图片清晰标注来源
- **AND** 前端可按来源分组展示

---

### Requirement: 搜索性能优化
系统 SHALL 针对不同搜索范围优化性能。

#### Scenario: 项目内搜索性能
- **WHEN** 用户在项目内搜索（约 100 张图片）
- **THEN** 系统直接暴力搜索（遍历所有向量）
- **AND** 响应时间 < 1 秒
- **AND** 不使用向量索引（数据量小，索引开销大于收益）

#### Scenario: 永久库搜索性能
- **WHEN** 用户在永久库搜索（约 1 万张图片）
- **THEN** 系统暴力搜索（SQLite + FAISS 可选）
- **AND** 响应时间 < 3 秒（J3455 CPU 基准）
- **AND** 未来数据量增长可引入 FAISS 索引

#### Scenario: 全局搜索性能警告
- **WHEN** 用户尝试全局搜索（50+ 项目，约 6 万张图片）
- **THEN** 系统提示"全局搜索可能较慢，建议指定项目"
- **AND** 可选：限制全局搜索的项目数量（如最近 10 个活跃项目）
- **AND** 响应时间约 10-30 秒（取决于项目数量）

---

### Requirement: 搜索缓存管理
系统 SHALL 维护搜索结果缓存，提升重复查询性能（更新：按库分别缓存）。

#### Scenario: 永久库搜索缓存
- **WHEN** 用户在永久库搜索
- **THEN** 系统缓存搜索文本/图片 ID 和结果
- **AND** 相同搜索在缓存有效期内直接返回缓存结果
- **AND** 缓存容量：64 条（可配置）
- **AND** 使用 LRU 策略淘汰旧缓存

#### Scenario: 项目库搜索缓存
- **WHEN** 用户在项目库搜索
- **THEN** 系统为每个项目独立维护缓存
- **AND** 项目切换时缓存不混淆

#### Scenario: 缓存失效
- **WHEN** 有新图片上传到数据库
- **THEN** 系统清空对应库的搜索缓存
- **OR** 标记缓存为过期，下次搜索重新计算

---

### Requirement: 排除已归档图片
系统 SHALL 在项目库搜索时默认排除已归档的图片。

#### Scenario: 项目库搜索排除已归档
- **WHEN** 用户在项目中搜索
- **THEN** 系统添加 SQL 条件 `WHERE archived=0`
- **AND** 已归档到永久库的图片不出现在结果中
- **AND** 用户可通过参数 `include_archived=true` 显示已归档图片

#### Scenario: 永久库搜索不受影响
- **WHEN** 用户在永久库搜索
- **THEN** `archived` 字段不存在或忽略
- **AND** 搜索所有永久库图片（包括归档来的）

---

### Requirement: 搜索结果分页
系统 SHALL 支持搜索结果分页，避免一次性返回大量数据。

#### Scenario: 分页查询
- **WHEN** 用户搜索返回大量结果（如 500 张图片）
- **THEN** 系统默认返回前 N 张（如 20 张）
- **AND** 提供 `limit` 和 `offset` 参数
- **AND** 返回总结果数量

#### Scenario: 向量搜索的分页优化
- **WHEN** 进行向量相似度搜索
- **THEN** 系统计算所有图片的相似度（无法避免）
- **AND** 按相似度排序后返回前 N 条
- **AND** 用户请求下一页时，从已排序结果中取下一批
- **AND** 缓存排序结果避免重复计算
