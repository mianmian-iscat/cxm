# 示例 input.json

手工调试用的用例输入，按场景分组。正式冒烟用例见 `eval/cases/`。

| 文件 | 说明 |
|------|------|
| `taobao-homepage-screenshot.json` | 淘宝首页截图 |
| `product-mgmt/tc01-search-platformid.json` | 品质联盟按平台商品 ID 搜索 |
| `product-mgmt/tc02-search-title.json` | 品质联盟按标题搜索 |
| `adplacement/verify.json` | 广告位报名验证 |
| `clearout/item-*.json` | 商品清退 |

执行：`python impl.py examples/product-mgmt/tc01-search-platformid.json`
