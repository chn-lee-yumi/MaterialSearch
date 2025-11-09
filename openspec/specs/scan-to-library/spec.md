# scan-to-library 规范

## Purpose
待定 - 通过归档变更 integrate-library-selection 创建。归档后更新目的。
## Requirements
### Requirement: 扫描前项目验证
系统 SHALL 在扫描前验证目标项目是否存在。

#### Scenario: 验证现有项目
- **GIVEN** 请求扫描到 `proj_2025_万科_01`
- **WHEN** 系统执行项目验证
- **THEN** 查询项目元信息库
- **AND** 确认项目存在且未删除
- **AND** 继续扫描

#### Scenario: 验证不存在的项目
- **GIVEN** 请求扫描到 `proj_2025_不存在_01`
- **WHEN** 系统执行项目验证
- **THEN** 查询项目元信息库
- **AND** 发现项目不存在
- **AND** 返回错误，终止扫描

#### Scenario: 跳过永久库验证
- **GIVEN** 请求扫描到 `permanent`
- **WHEN** 系统执行验证
- **THEN** 跳过项目验证（永久库始终存在）
- **AND** 直接执行扫描

### Requirement: 扫描统计更新
系统 SHALL 在扫描完成后更新对应库的统计信息。

#### Scenario: 更新项目统计
- **GIVEN** 扫描到项目 `proj_2025_万科_01`
- **AND** 新增 50 张图片
- **WHEN** 扫描完成
- **THEN** 项目图片数量 += 50
- **AND** 项目总大小 += 新增图片大小之和
- **AND** `updated_time` 更新为当前时间

#### Scenario: 永久库统计
- **GIVEN** 扫描到永久库
- **AND** 新增 100 张图片
- **WHEN** 扫描完成
- **THEN** 全局图片数量 += 100
- **AND** 状态栏显示最新数量

