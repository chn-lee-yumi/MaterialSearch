# search-by-library 规范

## Purpose
待定 - 通过归档变更 integrate-library-selection 创建。归档后更新目的。
## Requirements
### Requirement: 搜索 API 库类型参数
系统 SHALL 在搜索 API 中支持库类型参数。

#### Scenario: API 接受 library_type 参数
- **GIVEN** 搜索 API 端点 `POST /api/search`
- **WHEN** 请求体包含 `library_type: "project"`
- **AND** 包含 `project_id: "proj_2025_万科_01"`
- **THEN** 参数验证通过
- **AND** 在指定项目库中搜索

#### Scenario: library_type 参数默认值
- **GIVEN** 请求体不包含 `library_type`
- **WHEN** 执行搜索
- **THEN** 使用默认值 `library_type: "permanent"`

#### Scenario: library_type=project 但缺少 project_id
- **GIVEN** 请求体 `library_type: "project"`
- **AND** 未提供 `project_id`
- **WHEN** 执行搜索
- **THEN** 返回 400 Bad Request
- **AND** 错误消息 "library_type='project' 时必须提供 project_id"

#### Scenario: library_type 无效值
- **GIVEN** 请求体 `library_type: "all"` 或其他未支持的值
- **WHEN** 执行搜索
- **THEN** 返回 400 Bad Request
- **AND** 错误消息提示 “library_type 仅支持 permanent/project”

### Requirement: 搜索结果来源标注
系统 SHALL 在搜索结果中标注图片来源。

#### Scenario: 标注永久库来源
- **GIVEN** 搜索结果包含永久库的图片
- **WHEN** 返回结果
- **THEN** 每条结果包含 `source: "永久库"`
- **AND** 前端可显示来源标签

#### Scenario: 标注项目库来源
- **GIVEN** 搜索结果包含项目库的图片
- **AND** 项目名称为 "万科广场项目"
- **WHEN** 返回结果
- **THEN** 每条结果包含 `source: "万科广场项目"`
- **AND** 可点击跳转到该项目

### Requirement: 搜索缓存分离
系统 SHALL 为不同库的搜索结果独立缓存。

#### Scenario: 永久库和项目库缓存独立
- **GIVEN** 用户在永久库搜索 "建筑"
- **AND** 结果已缓存
- **WHEN** 用户在项目库搜索 "建筑"
- **THEN** 不使用永久库的缓存
- **AND** 重新执行搜索
- **AND** 缓存项目库的结果

#### Scenario: 相同搜索词不同库命中不同缓存
- **GIVEN** 缓存键包含 `(search_term, library_type, project_id)`
- **WHEN** 搜索 `("建筑", "permanent", None)`
- **THEN** 命中永久库缓存
- **WHEN** 搜索 `("建筑", "project", "proj_xxx")`
- **THEN** 命中项目库缓存（不同缓存条目）

### Requirement: 搜索性能
系统 SHALL 确保库类型选择不降低搜索性能。

#### Scenario: 项目库搜索性能
- **GIVEN** 项目库包含 100 张图片
- **WHEN** 执行搜索
- **THEN** 响应时间 < 1 秒
- **AND** 比永久库搜索快（数据量小）

#### Scenario: 永久库搜索性能保持
- **GIVEN** 永久库包含 10000 张图片
- **WHEN** 执行搜索（library_type=permanent）
- **THEN** 响应时间 < 3 秒
- **AND** 与旧版本性能相同

