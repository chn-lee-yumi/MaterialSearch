# upload-to-library 规范

## Purpose
待定 - 通过归档变更 integrate-library-selection 创建。归档后更新目的。
## Requirements
### Requirement: 上传 API 目标参数
系统 SHALL 在上传 API 中支持目标库参数，并扩展为支持批量索引。

#### Scenario: API 接受 target 参数
- **GIVEN** 上传 API 端点 `POST /api/upload`
- **WHEN** 表单数据包含 `target=proj_2025_万科_01`
- **AND** 包含图片文件
- **THEN** 参数验证通过
- **AND** 图片上传到指定项目库

#### Scenario: target 参数默认值
- **GIVEN** 上传请求不包含 `target` 参数
- **WHEN** 执行上传
- **THEN** 使用默认值 `target='permanent'`

#### Scenario: target 参数验证
- **GIVEN** 请求包含 `target=invalid_format`
- **WHEN** 执行上传
- **THEN** 返回 400 Bad Request
- **AND** 错误消息 "无效的目标库格式"

#### Scenario: 批量索引模式（新增）
- **GIVEN** 调用批量索引 API `POST /api/batch_index`
- **WHEN** 传递 `target=proj_2025_万科_01` 和文件路径数组
- **THEN** 参数验证通过
- **AND** 创建批量索引任务

### Requirement: 上传路径策略
系统 SHALL 根据目标库和上传模式确定图片存储路径。

#### Scenario: 永久库图片存储
- **GIVEN** 上传到永久库
- **WHEN** 保存图片文件
- **THEN** 存储路径为 `/mnt/nas/permanent/<hash>.jpg`
- **AND** 数据库记录该路径

#### Scenario: 项目库图片存储
- **GIVEN** 上传到项目库 `proj_2025_万科_01`
- **WHEN** 保存图片文件
- **THEN** 存储路径为 `/mnt/nas/projects/proj_2025_万科_01/<hash>.jpg`
- **AND** 或保持用户原 NAS 路径（仅索引）

#### Scenario: 图片去重检查
- **GIVEN** 上传的图片 checksum 已存在于目标库
- **WHEN** 检测到重复
- **THEN** 返回警告 "该图片已存在于目标库"
- **AND** 询问用户是否继续

#### Scenario: 批量索引保持原路径（新增）
- **GIVEN** 使用批量索引模式
- **AND** 文件路径为 `\\Daga-nas5\...\image.jpg`
- **WHEN** 索引文件
- **THEN** 不移动文件
- **AND** 数据库记录原始 UNC 路径
- **AND** 提取特征存储到项目数据库

### Requirement: 上传后统计更新
系统 SHALL 在上传完成后更新目标库统计。

#### Scenario: 更新项目库统计
- **GIVEN** 上传 10 张图片到 `proj_2025_万科_01`
- **AND** 总大小 50 MB
- **WHEN** 上传完成
- **THEN** 项目图片数 += 10
- **AND** 项目总大小 += 50 MB
- **AND** `updated_time` 更新为当前时间

#### Scenario: 永久库统计
- **GIVEN** 上传 5 张图片到永久库
- **WHEN** 上传完成
- **THEN** 全局图片数 += 5
- **AND** 前端状态栏实时更新

#### Scenario: 批量索引统计更新（新增）
- **GIVEN** 批量索引 25 个文件到项目库
- **AND** 成功 23 个，失败 2 个
- **WHEN** 索引完成
- **THEN** 项目图片数 += 23
- **AND** 项目总大小 += 成功文件的大小之和
- **AND** 失败文件不计入统计

### Requirement: 上传队列管理
系统 SHALL 使用队列避免并发写入冲突。

#### Scenario: 队列串行化上传
- **GIVEN** 两个用户同时上传到同一项目库
- **WHEN** 上传请求到达
- **THEN** 系统将任务加入队列
- **AND** 按队列顺序逐个处理
- **AND** 避免数据库锁冲突

#### Scenario: 不同库并发上传
- **GIVEN** 用户 A 上传到永久库
- **AND** 用户 B 同时上传到项目库 `proj_xxx`
- **WHEN** 两个上传并发执行
- **THEN** 无冲突（不同数据库文件）
- **AND** 可同时进行

#### Scenario: 批量索引任务队列（新增）
- **GIVEN** 用户启动批量索引任务
- **WHEN** 任务加入队列
- **THEN** 后台线程串行处理文件
- **AND** 每处理1个文件更新进度
- **AND** 避免数据库并发写入

### Requirement: 批量索引错误处理
系统 SHALL 在批量索引时跳过失败文件并继续处理。

#### Scenario: 文件损坏跳过
- **GIVEN** 批量索引包含损坏文件 `broken.jpg`
- **WHEN** 索引到该文件
- **THEN** 记录错误信息
- **AND** 跳过该文件
- **AND** 继续处理下一个文件
- **AND** 最终报告中显示失败原因

#### Scenario: 路径不存在跳过
- **GIVEN** 文件路径 `\\Daga-nas5\...\missing.jpg` 不存在
- **WHEN** 索引到该文件
- **THEN** 记录错误 "文件不存在"
- **AND** 跳过并继续

#### Scenario: 特征提取失败跳过
- **GIVEN** 文件 `large.jpg` 过大导致 CLIP 模型超时
- **WHEN** 索引该文件
- **THEN** 捕获超时异常
- **AND** 记录错误 "特征提取超时"
- **AND** 跳过并继续

### Requirement: 重复文件智能检测
系统 SHALL 使用 phash 检测重复文件并提供用户决策。

#### Scenario: phash 相同视为重复
- **GIVEN** 新文件 phash 为 `a1b2c3d4e5f6g7h8`
- **AND** 项目库中存在相同 phash
- **WHEN** 索引该文件
- **THEN** 标记为重复
- **AND** 根据策略处理

#### Scenario: 询问模式返回重复信息
- **GIVEN** 重复策略为 `"ask"`
- **WHEN** 检测到重复
- **THEN** 暂停索引
- **AND** 返回重复文件信息给前端：
  ```json
  {
    "duplicate": true,
    "new_file": {...},
    "existing_file": {...}
  }
  ```

#### Scenario: 自动跳过模式
- **GIVEN** 重复策略为 `"skip"`
- **WHEN** 检测到重复
- **THEN** 自动跳过
- **AND** 记录到跳过列表
- **AND** 继续下一个文件

#### Scenario: 自动覆盖模式
- **GIVEN** 重复策略为 `"overwrite"`
- **WHEN** 检测到重复
- **THEN** 删除旧记录
- **AND** 索引新文件
- **AND** 更新数据库

### Requirement: 批量索引性能优化
系统 SHALL 优化批量索引性能以提升用户体验。

#### Scenario: GPU批处理
- **GIVEN** 使用 GPU 进行特征提取
- **AND** 批量索引 12 个文件
- **WHEN** 提取特征
- **THEN** 将 12 个图片组成一个 batch
- **AND** 单次调用 CLIP 模型
- **AND** 处理速度提升 3-5 倍

#### Scenario: 进度实时反馈
- **GIVEN** 批量索引 50 个文件
- **WHEN** 处理每个文件
- **THEN** 更新任务进度
- **AND** 前端每 500ms 轮询一次
- **AND** 显示当前文件和进度百分比

#### Scenario: 预计剩余时间
- **GIVEN** 已处理 10/50 个文件
- **AND** 平均每个文件耗时 2 秒
- **WHEN** 计算剩余时间
- **THEN** 显示 "预计剩余: 80 秒"
- **AND** 动态更新估算时间

### Requirement: 索引任务管理
系统 SHALL 提供索引任务的生命周期管理。

#### Scenario: 创建任务并返回ID
- **GIVEN** 用户启动批量索引
- **WHEN** 调用 `POST /api/batch_index`
- **THEN** 生成唯一任务 ID（UUID）
- **AND** 返回给前端
- **AND** 任务状态初始化

#### Scenario: 查询任务状态
- **GIVEN** 任务 ID 存在
- **WHEN** 调用 `GET /api/batch_index/<task_id>/status`
- **THEN** 返回任务当前状态
- **AND** 包括进度、成功数、失败列表

#### Scenario: 取消运行中的任务
- **GIVEN** 任务正在运行（processed=10/50）
- **WHEN** 调用 `DELETE /api/batch_index/<task_id>`
- **THEN** 设置取消标志
- **AND** 当前文件完成后停止
- **AND** 已处理文件保留
- **AND** 返回部分完成报告

#### Scenario: 任务过期清理
- **GIVEN** 任务完成超过 24 小时
- **WHEN** 系统定时清理
- **THEN** 删除任务记录
- **AND** 释放内存

