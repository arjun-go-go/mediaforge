# Security Policy

## Supported versions

MediaForge 当前处于早期开发阶段，仅维护 `main` 分支的最新版本。旧提交和自行修改的部署版本不提供安全更新承诺。

## Reporting a vulnerability

请不要通过公开 Issue 披露可利用的安全漏洞。请在 GitHub 仓库的 **Security** 页面选择 **Report a vulnerability**，通过私密 Security Advisory 提交：

- 受影响的版本或提交；
- 复现步骤与影响范围；
- 可行的修复建议（如有）；
- 是否已经在其他地方公开。

维护者确认后会在私密渠道继续沟通，并在修复可用后协调披露。请勿提交真实 API Key、用户数据或生产数据库副本作为复现材料。

## Deployment responsibility

公开仓库中的默认配置面向本地开发。互联网部署前必须更换 JWT、PostgreSQL、MinIO 及第三方模型凭据，并使用 HTTPS、私有网络和最小权限策略。
