# 公共原子步骤（Cross-Domain Atoms）

## 设计理念

`eval/cases/_atoms/` 存放跨业务域（F88 / 原创保护 / 千牛）共用的**原子步骤模板**。
每条用例不再复制粘贴相同的 evaluate 表达式，而是通过 `includeAtom` 步骤引用，
`StepExecutor` 会按参数模板展开为实际步骤列表并就地执行。

## 目录结构

```
eval/cases/_atoms/
├── manifest.json                  # 所有原子索引（id / 文件 / 描述 / 引用源）
├── README.md                      # 本文件
├── page_snapshot.json             # 页面快照（按钮/表格/表单/tab/select/文本）
├── antd_select_open.json          # 打开 Ant Design Select 下拉框
├── antd_select_choose_option.json # 在已打开的下拉框里按文本选选项
├── antd_table_wait_load.json      # 等待 Ant Design 表格加载完成
├── antd_drawer_state.json         # 检查 Drawer 可见性并汇总 form-item
└── antd_tab_switch.json           # 切换 Ant Design Tabs
```

## 用例引用方式

在 case JSON 的 `steps` 数组里加入 `includeAtom` 类型步骤：

```json
{
  "steps": [
    { "type": "includeAtom", "atom": "page_snapshot", "params": { "storeAs": "snap1" } },
    { "type": "includeAtom", "atom": "antd_select_open", "params": { "scopeSelector": ".ant-drawer .ant-select" } },
    { "type": "includeAtom", "atom": "antd_select_choose_option", "params": { "optionText": "详情" } }
  ]
}
```

`StepExecutor` 遇到 `includeAtom` 时：
1. 通过 `AtomLoader.load(name)` 拿到模板
2. 用 `params` 替换 `{{var}}` 占位符
3. 把模板的 `steps` 就地展开到当前位置顺序执行

## 如何新增原子

1. 在本目录下新建 `<id>.json`，结构为：
   ```json
   {
     "id": "my_atom",
     "description": "一句话说明",
     "params": [
       { "name": "scopeSelector", "type": "string", "default": "body", "desc": "作用域" },
       { "name": "storeAs",       "type": "string", "default": "myState", "desc": "Store 键名" }
     ],
     "steps": [
       { "type": "evaluate", "expression": "(() => { /* ... {{scopeSelector}} ... */ })()", "storeAs": "{{storeAs}}" }
     ]
   }
   ```
2. 在 `manifest.json` 的 `atoms` 数组里追加一项
3. 在用例里 `includeAtom` 引用即可

## 参数替换约定

- `{{varName}}` 表示占位符（字符串值直接替换，不做 JSON 转义）
- 所有参数必须声明在 `params` 字段，`default` 在缺省时生效
- 必填参数无 `default`，缺失则 `AtomLoader.load()` 抛 ValueError

## 治理原则

- 同一模式出现 ≥ 3 次 → 抽到 atoms
- 抽出来后，原 case 文件里的硬编码表达式要替换成 `includeAtom`
- `manifest.json` 的 `usage_count` 定期用脚本统计，低于 2 的考虑合并/删除
