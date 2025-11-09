# batch-indexing 规范

## Purpose
待定 - 通过归档变更 improve-project-upload 创建。归档后更新目的。
## Requirements
### Requirement: 路径预览API
系统 SHALL 提供路径预览API，接收路径列表并返回文件元信息。

#### Scenario: 混合路径解析
- **GIVEN** 用户粘贴路径列表：
  ```
  \\Daga-nas5\...\1102\截图\01.jpg
  \\Daga-nas5\...\1102\渲染图
  ```
- **WHEN** 调用 `POST /api/preview_files`
- **THEN** 后端识别第一个为文件路径，第二个为文件夹路径
- **AND** 递归遍历 `渲染图` 文件夹
- **AND** 返回所有文件的元信息数组

#### Scenario: 返回文件元信息
- **GIVEN** 路径 `\\Daga-nas5\...\image.jpg` 存在
- **WHEN** 请求预览
- **THEN** 返回 JSON：
  ```json
  {
    "path": "\\\\Daga-nas5\\...\\image.jpg",
    "filename": "image.jpg",
    "size": 2457600,
    "type": "image",
    "ext": ".jpg",
    "mtime": 1640000000,
    "is_indexed": false,
    "phash": null
  }
  ```

#### Scenario: 过滤不支持的文件
- **GIVEN** 文件夹包含：`image.jpg`, `doc.docx`, `~$temp.txt`
- **WHEN** 请求预览
- **THEN** 仅返回 `image.jpg`
- **AND** 自动跳过 `.docx` 和临时文件

#### Scenario: 路径不存在
- **GIVEN** 路径 `\\Daga-nas5\...\notfound\` 不存在
- **WHEN** 请求预览
- **THEN** 返回 400 错误
- **AND** 错误消息 "路径不存在: \\\\Daga-nas5\\...\\notfound\\"

#### Scenario: 检测已索引文件
- **GIVEN** 文件 `image.jpg` 已在项目库中索引
- **AND** phash 为 `a1b2c3d4e5f6g7h8`
- **WHEN** 请求预览
- **THEN** `is_indexed` 为 `true`
- **AND** 返回 phash 值

### Requirement: 缩略图生成API
系统 SHALL 按需生成缩略图。

#### Scenario: 生成图片缩略图
- **GIVEN** 文件 `\\Daga-nas5\...\image.jpg`
- **WHEN** 调用 `GET /api/thumbnail?path=<encoded_path>`
- **THEN** 生成 128x128 缩略图
- **AND** 缓存到 `/tmp/thumbnails/<md5>.jpg`
- **AND** 返回图片二进制数据

#### Scenario: 缩略图缓存命中
- **GIVEN** 缩略图已生成并缓存
- **WHEN** 再次请求同一文件
- **THEN** 直接返回缓存文件
- **AND** 响应时间 < 10ms

#### Scenario: 视频首帧缩略图
- **GIVEN** 文件 `\\Daga-nas5\...\video.mp4`
- **WHEN** 请求缩略图
- **THEN** 提取视频首帧（0秒位置）
- **AND** 生成 128x128 缩略图
- **AND** 缓存并返回

#### Scenario: PDF首页缩略图
- **GIVEN** 文件 `\\Daga-nas5\...\doc.pdf`
- **WHEN** 请求缩略图
- **THEN** 渲染PDF第一页
- **AND** 生成 128x128 缩略图

#### Scenario: 大文件超时保护
- **GIVEN** 文件大小超过 100MB
- **WHEN** 请求缩略图
- **THEN** 设置超时 5秒
- **AND** 超时后返回默认图标
- **AND** 日志记录警告

### Requirement: 批量索引API
系统 SHALL 提供批量索引API。

#### Scenario: 启动批量索引任务
- **GIVEN** 用户选中 25 个文件
- **WHEN** 调用 `POST /api/batch_index`
  ```json
  {
    "files": ["path1", "path2", ...],
    "target": "proj_2025_万科_01",
    "duplicate_strategy": "ask"
  }
  ```
- **THEN** 创建任务ID
- **AND** 返回 `{"task_id": "uuid"}`
- **AND** 启动后台线程处理

#### Scenario: 查询索引进度
- **GIVEN** 任务正在执行
- **WHEN** 调用 `GET /api/batch_index/<task_id>/status`
- **THEN** 返回进度信息：
  ```json
  {
    "total": 25,
    "processed": 10,
    "success": 9,
    "current_file": "image_10.jpg",
    "failed": [{"path": "...", "error": "损坏的文件"}],
    "duplicates": [{"path": "...", "existing_path": "..."}]
  }
  ```

#### Scenario: 索引完成
- **GIVEN** 所有文件处理完成
- **WHEN** 查询状态
- **THEN** `processed == total`
- **AND** 返回最终报告：
  ```json
  {
    "total": 25,
    "processed": 25,
    "success": 23,
    "failed": [
      {"path": "broken.jpg", "error": "无法读取"}
    ],
    "duplicates": [
      {"path": "dup.jpg", "action": "skipped"}
    ]
  }
  ```

#### Scenario: 串行处理避免冲突
- **GIVEN** 批量索引任务包含 50 个文件
- **WHEN** 执行索引
- **THEN** 逐个文件串行处理
- **AND** 每处理1个文件更新进度
- **AND** 避免数据库并发写入

#### Scenario: 中途取消任务
- **GIVEN** 任务正在执行（processed=10/50）
- **WHEN** 调用 `DELETE /api/batch_index/<task_id>`
- **THEN** 设置取消标志
- **AND** 当前文件完成后停止
- **AND** 返回状态 `"cancelled"`
- **AND** 已处理的10个文件保留

### Requirement: 重复文件检测
系统 SHALL 在索引时检测重复文件。

#### Scenario: 检测phash重复
- **GIVEN** 新文件 phash 为 `a1b2c3d4`
- **AND** 数据库中存在相同 phash
- **WHEN** 索引该文件
- **THEN** 标记为重复
- **AND** 添加到 `duplicates` 数组
- **AND** 等待用户决策

#### Scenario: 用户选择跳过重复
- **GIVEN** 检测到重复文件
- **WHEN** `duplicate_strategy` 为 `"skip"`
- **THEN** 跳过该文件
- **AND** `success` 计数不增加
- **AND** 记录到 `duplicates` 数组

#### Scenario: 用户选择覆盖重复
- **GIVEN** 检测到重复文件
- **WHEN** `duplicate_strategy` 为 `"overwrite"`
- **THEN** 删除旧记录
- **AND** 插入新记录
- **AND** `success` 计数增加

#### Scenario: 用户选择询问模式
- **GIVEN** `duplicate_strategy` 为 `"ask"`
- **WHEN** 检测到重复
- **THEN** 暂停处理
- **AND** 将重复信息返回给前端
- **AND** 等待前端传递决策

### Requirement: 错误处理和报告
系统 SHALL 处理索引错误并提供详细报告。

#### Scenario: 文件损坏跳过
- **GIVEN** 文件 `broken.jpg` 无法读取
- **WHEN** 索引该文件
- **THEN** 捕获异常
- **AND** 记录到 `failed` 数组
- **AND** 继续处理下一个文件

#### Scenario: 路径访问权限错误
- **GIVEN** 文件路径无访问权限
- **WHEN** 索引该文件
- **THEN** 返回错误 "权限不足"
- **AND** 记录到失败列表

#### Scenario: 生成最终报告
- **GIVEN** 索引完成
- **WHEN** 前端请求状态
- **THEN** 返回详细报告：
  - 成功数量
  - 失败文件列表（路径+错误信息）
  - 重复文件列表（路径+处理方式）
  - 总耗时

### Requirement: 索引性能优化
系统 SHALL 优化批量索引性能。

#### Scenario: 批量特征提取
- **GIVEN** 使用 GPU 进行特征提取
- **WHEN** 索引 12 个文件
- **THEN** 使用 batch_size=12 批量处理
- **AND** 单次调用 CLIP 模型
- **AND** 提升处理速度 3-5 倍

#### Scenario: 进度更新节流
- **GIVEN** 索引 100 个文件
- **WHEN** 前端轮询进度
- **THEN** 每 500ms 返回最新进度
- **AND** 中间状态缓存，避免重复计算

#### Scenario: 缩略图并发限制
- **GIVEN** 需要生成 50 个缩略图
- **WHEN** 懒加载缩略图
- **THEN** 最多 5 个并发请求
- **AND** 避免服务器过载

### Requirement: 路径格式规范化
系统 SHALL 规范化不同格式的文件路径。

#### Scenario: UNC路径规范化
- **GIVEN** 路径 `\\\\Daga-nas5\\path\\to\\file.jpg`（双反斜杠）
- **WHEN** 解析路径
- **THEN** 统一为系统路径格式
- **AND** 确保后端可访问

#### Scenario: 映射盘符转换
- **GIVEN** 路径 `Z:\\project\\image.jpg`
- **AND** Z: 映射到 `\\\\Daga-nas5\\shared`
- **WHEN** 解析路径
- **THEN** 转换为 UNC 路径
- **AND** 存储规范化路径

#### Scenario: 相对路径拒绝
- **GIVEN** 路径 `../../../image.jpg`
- **WHEN** 解析路径
- **THEN** 返回 400 错误
- **AND** 错误消息 "不支持相对路径，请使用绝对路径"

### Requirement: 临时文件智能过滤
系统 SHALL 自动过滤临时文件。

#### Scenario: 过滤办公软件临时文件
- **GIVEN** 文件列表包含 `~$document.docx`
- **WHEN** 预览文件
- **THEN** 自动排除该文件
- **AND** 不在预览列表中显示

#### Scenario: 过滤系统缓存文件
- **GIVEN** 文件列表包含 `.DS_Store`, `Thumbs.db`
- **WHEN** 预览文件
- **THEN** 自动排除这些文件

#### Scenario: 用户可选显示临时文件
- **GIVEN** 请求参数 `include_temp=true`
- **WHEN** 预览文件
- **THEN** 包含临时文件
- **AND** 标记为 `is_temp=true`
- **AND** 前端默认取消勾选

