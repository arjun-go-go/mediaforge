# Contributing to MediaForge

感谢你参与 MediaForge。提交改动前，请先通过 Issue 说明问题或业务场景，避免重复实现。

## 开发流程

1. Fork 仓库并从 `main` 创建功能分支。
2. 按根目录 README 配置开发环境。
3. 保持改动聚焦；数据库结构变化必须提供 Alembic 迁移。
4. 前后端接口变化应同步更新类型和文档。
5. 提交 Pull Request，并说明动机、实现范围和验证方式。

## 提交要求

- 不得提交 API Key、访问令牌、`.env`、生产数据或用户隐私数据。
- 不得提交未获得公开授权的商品图片、品牌素材或训练数据。
- 不要把本地日志、生成结果、临时脚本和调试目录加入仓库。
- UI 改动请附新的页面截图；接口行为变化请附请求与响应示例。
- 一个 Pull Request 尽量只解决一个明确问题。

## 提交信息

建议使用简短、可读的提交信息，例如：

```text
feat: add authenticated MinIO file route
fix: preserve selected image model in batch jobs
docs: clarify Docker deployment variables
```

提交代码即表示你有权按本项目的 MIT License 提供相关内容。
