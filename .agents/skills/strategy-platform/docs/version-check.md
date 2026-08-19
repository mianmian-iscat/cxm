# 版本检查流程

> 从 SKILL.md 提取。每个会话首次使用本 skill 时执行。

在每个会话中首次触发本 skill 时，自动检查是否有新版本。**静默执行，无需告知用户正在检查版本。**

```
第 1 步：读取本地版本
  → 读取 ~/.qoderwork/skills/strategy-platform/package.json
  → 取 version 字段值（如 "1.0.0"）

第 2 步：查询远程最新版本
  → curl -fsSL "https://contextlab.alibaba-inc.com/skill/strategy-platform/latest"
  → 从返回 JSON 取 version 字段（远程版本）
  → 从返回 JSON 取 dist.tarball 字段（下载地址）

第 3 步：对比版本
  → 本地 version === 远程 version → 版本已最新，静默继续，不输出任何信息
  → 本地 version !== 远程 version → 告知用户：
     "strategy-platform skill 有新版本 vX.Y.Z（当前 vA.B.C），是否更新？"

第 4 步：用户确认更新后执行
  → 从 dist.tarball 下载 tgz
  → 解压 tgz 并将 package/ 下的文件覆盖到 ~/.qoderwork/skills/strategy-platform/
  → 清理临时文件
  → 重新读取 SKILL.md 以加载新版本指令
```

注意：
- 如果 curl 查询远程版本失败（网络问题），静默跳过，继续使用当前版本
