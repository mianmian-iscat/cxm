# web-automation 目录导航

> PC Web 被测页自动化：探索 → knowledge → 灵活步骤 → 截图/断言。  
> 数据构造（TPP 分桶等）请用 **browser-data-setup**，不在本 Skill 范围。

## 根目录（仅入口）

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Agent 技能说明（必读） |
| `impl.py` | **唯一正规执行入口**：`python impl.py input.json [output.json]` |
| `package.json` | puppeteer-core 依赖 |

## 核心模块

```
core/                    执行引擎
├── cdp_client.py        Python CDP 客户端
├── _node_bridge.js      Node ↔ Chrome 桥接
├── artifact_manager.py  产物目录管理
├── checkpoint_manager.py 断点续跑
├── knowledge_updater.py 执行结果反哺 knowledge
└── video_recorder.py    录屏（可选）

schema/                  input.json / output.json JSON Schema
knowledge/               页面知识库
├── index.json           URL 路由索引
├── okf/                 OKF Bundle（按消费方分层）
│   ├── INDEX.md         OKF 根索引
│   ├── GOVERNANCE.md    知识治理规则
│   ├── features/        业务规则层（测什么）
│   ├── execution/       执行知识层（怎么验）
│   ├── infra/           工程注册表层（ID/配置/DB）
│   ├── learnings/       历史教训层（踩坑记录）
│   └── regression/      回归基线层
└── synced-qoderwork/    从 qoderwork 同步的原始文档

scenes/                  场景子 Skill（千牛、品质联盟）
shared/browser-cdp/      与 browser-data-setup 共用的 CDP 规范（在上级 skills/ 目录）
```

## 智能编排（借鉴 cloth-test-memory）

```
memory/                  三层记忆架构
├── MEMORY.md            记忆入口
├── L0/                  铁律层（每次会话强制加载）
├── L1/                  上下文层（按业务域按需加载）
└── L2/                  历史层（归档检索）

agents/                  子 Agent 定义
├── rule-hunter.md       业务规则猎人（只读）
├── data-builder.md      数据构造专家（执行）
└── verifier.md          交叉验证专家（执行）

harness/
├── phase_gates.yaml     Phase 门禁配置
├── phase_definitions.yaml Phase 编排定义
├── orchestrator_config.yaml 主 Agent 控制面（含 L0/OKF/Gate 集成）
└── pipelines/           流水线定义

scripts/
├── knowledge_extractor.py  知识沉淀闭环引擎
├── gate_checker.py         门禁检查器
└── ...                     其他工具脚本
```

## 工具脚本 `scripts/`

| 脚本 | 用途 |
|------|------|
| `knowledge_extractor.py` | **知识沉淀闭环**：从失败用例提取模式 → 写入 OKF learnings/ |
| `gate_checker.py` | **门禁检查器**：执行 Phase Gate 检查 |
| `init-scene.js` | 新页面探索 → 生成 scene + knowledge |
| `nl2input.py` | 自然语言 → input.json |
| `tc2input.py` | optimize-test-case YAML → input.json |
| `run-browser-test.js` | **遗留** Node 执行器（调试用，优先用 impl.py） |
| `normalize_input.py` | input 规范化 |
| `generate-report.py` | 报告生成 |
| `score_eval.py` | eval 评分 |

## 用例与示例

```
eval/cases/              冒烟用例（smoke_*.json）
examples/                手工示例 input.json
references/              操作参考（弹窗、React 填值、截图规范等）
docs/                    设计文档、优化说明、quickstart
```

## 归档 `archive/`（勿用于生产）

| 子目录 | 内容 |
|--------|------|
| `explore/` | 一次性页面探索脚本 |
| `run-tc/` | 历史 TC 执行脚本 |
| `hj-bill-query/` | 汇金账单查询（已归档，见 docs/hj-bill-query.md） |
| `patches/` | 已合并的 bridge 补丁 |

## 产物 `artifacts/`

每次 `impl.py` 执行自动生成 `{scene}-{case}-{timestamp}/`，含 `output.json`、`screenshots/*.jpg`。  
历史调试产物在 `artifacts/_archive/`。

## 常用命令

```bash
# 环境
source ~/.qoderwork/cloth-test/scripts/browser-env.sh

# 执行用例
python impl.py eval/cases/smoke_qianniu_material.json

# 自然语言生成并执行
python scripts/nl2input.py "在品质联盟搜索买手是奕心的商品" --run

# 新页面探索
node scripts/init-scene.js --name my-scene --url "https://..."
```
