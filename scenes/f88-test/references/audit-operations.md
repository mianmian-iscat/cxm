# F88 素材审核 - 操作说明

> ⚠️ 完整操作逻辑见 `scenes/f88-test/knowledge/f88-material-audit.json`。
> 本文件提供操作动线细节和接口实测数据备查。

## 审核列表筛选

| 筛选条件 | 操作方式 | 说明 |
|---------|---------|------|
| 审核状态 | `selectOption`，ant-select | 待审核/审核通过/审核驳回/已撤回 |
| 素材类型 | `selectOption`，ant-select | 主图/详情页/白底图/场景图/标题/描述 |
| 提交时间 | `dateRange`，tbd-picker | 范围选择器，同天起止等于无筛选 |
| 商家ID | `fill`，react: true | React 受控组件，必须 native setter |
| 商品ID | `fill`，react: true | 同上 |

## 审核详情抽屉

审核详情使用 Ant Design Drawer 组件（`.ant-drawer`），从右侧滑出：

```
点击「审核」按钮
  → 等待 .ant-drawer 出现（约 300ms 动画）
  → 抽屉内包含：
     - 素材大图预览（图片类：支持放大）
     - 标题 / 描述文本
     - 商品信息（关联商品ID、标题）
     - 审核历史（时间线组件）
     - 底部操作按钮：通过 / 驳回
```

⚠️ 抽屉动画完成前不要操作内部元素，建议 `wait 500ms` 后再操作。

## 审核通过操作

```
在审核详情抽屉中：
  → 确认素材内容无误
  → 点击「通过」按钮
  → 可能出现确认弹窗（.ant-modal）
  → 如有弹窗，点击弹窗中的「确认」
  → waitForAPI approveMaterial
  → 验证响应 data.success=true
  → 抽屉自动关闭，列表刷新
```

## 审核驳回操作

```
在审核详情抽屉中：
  → 点击「驳回」按钮
  → 弹出驳回表单（.ant-modal 或内嵌表单）
  → 填写驳回原因（⚠️ 必填 textarea）
  → 选择驳回类型（下拉选择器）
  → 点击「确认驳回」
  → waitForAPI rejectMaterial
  → 验证响应 data.success=true
  → 抽屉自动关闭，列表刷新
```

⚠️ 驳回原因不填时「确认」按钮始终 disabled，不会触发接口请求。

## 批量审核操作

```
在审核列表页：
  → 逐行勾选 checkbox（仅「待审核」状态的行可勾选）
  → 点击表格上方「批量审核」按钮
  → 弹窗显示：
     - 已选素材数量
     - 操作选择：全部通过 / 全部驳回（radio）
     - 如选驳回：驳回原因输入框
  → 点击「确认」
  → waitForAPI batchAuditMaterial
  → 验证 data.data.failCount=0
  → 弹窗关闭，列表刷新
```

⚠️ 批量操作时 checkbox 可能因滚动不可见，需先滚动行到可视区域。

## 接口示例（预发环境）

### queryMaterialAuditList

```
POST /cobweb/api/bzb.api.fsyx_quality_guard.f88.queryMaterialAuditList
请求体示例：
{
  "auditStatus": "PENDING",
  "materialType": "主图",
  "currentPage": 1,
  "pageSize": 20
}
响应：{ "data": { "data": { "totalCount": 42, "items": [...] } } }
```

### approveMaterial

```
POST /cobweb/api/bzb.api.fsyx_quality_guard.f88.approveMaterial
请求体示例：
{
  "materialId": 12345678,
  "comment": "素材质量合格"
}
响应：{ "data": { "success": true, "data": { "auditStatus": "APPROVED" } } }
```

### rejectMaterial

```
POST /cobweb/api/bzb.api.fsyx_quality_guard.f88.rejectMaterial
请求体示例：
{
  "materialId": 12345678,
  "rejectReason": "图片模糊/质量不达标",
  "rejectType": "QUALITY",
  "comment": "分辨率不满足 750×1000px 要求"
}
响应：{ "data": { "success": true, "data": { "auditStatus": "REJECTED" } } }
```

### batchAuditMaterial

```
POST /cobweb/api/bzb.api.fsyx_quality_guard.f88.batchAuditMaterial
请求体示例：
{
  "materialIds": [12345678, 12345679, 12345680],
  "auditAction": "approve"
}
响应：{ "data": { "data": { "successCount": 3, "failCount": 0, "details": [] } } }
```

## HSF 接口集成参考

### pom.xml 依赖

```xml
<dependency>
  <groupId>com.alibaba.f88</groupId>
  <artifactId>f88-material-client</artifactId>
  <version>1.0.0</version>
</dependency>
```

### @HSFConsumer 声明

```java
@Configuration
public class HsfConsumerConfig {

    @HSFConsumer(serviceInterface = "com.alibaba.f88.material.MaterialAuditService",
                 serviceVersion = "1.0.0",
                 serviceGroup = "HSF")
    private MaterialAuditService materialAuditService;
}
```

### HTTP Controller 透出

```java
@RestController
@RequestMapping("/api/f88/audit")
public class F88AuditController {

    @Autowired
    private MaterialAuditService materialAuditService;

    @PostMapping("/list")
    public Result<AuditListResponse> queryList(@RequestBody AuditListRequest request) {
        return materialAuditService.queryAuditList(request);
    }

    @PostMapping("/approve")
    public Result<AuditResult> approve(@RequestBody ApproveRequest request) {
        return materialAuditService.approveMaterial(request);
    }

    @PostMapping("/reject")
    public Result<AuditResult> reject(@RequestBody RejectRequest request) {
        return materialAuditService.rejectMaterial(request);
    }

    @PostMapping("/batch")
    public Result<BatchAuditResult> batchAudit(@RequestBody BatchAuditRequest request) {
        return materialAuditService.batchAudit(request);
    }

    @PostMapping("/detail")
    public Result<AuditDetailResponse> detail(@RequestParam Long materialId) {
        return materialAuditService.queryAuditDetail(materialId);
    }
}
```
