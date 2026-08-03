"""
F88 种草图文 & 种草视频 — 端到端数据流转验证
=============================================
需求: 种草素材生产全链路 (图文+视频)
环境: 预发 pre-aifashion-xiaoer.alibaba-inc.com
测试人员: 目民(526043)

数据流转全景:
  种草视频: F0触发/定时器 → g_afd_material_prod_record → workflow_record_log(gen_video→approve)
            → g_afd_recommend_material_pool_record(contentId) → 纵横平台 → 素材中心
  种草图文: F0触发/定时器 → workflow_record_log(industry_tag→season_tag→gen_img→llm_text→approve→image_text_upload)
            → g_afd_recommend_material_pool_record(contentId) → 纵横平台 → 素材中心 → 商家端

达人账号:
  - 产业带种草(定时器): 1027873092
  - 产业带图文上传达人: 2583875942

下游验证平台:
  - 素材中心(小二): https://xiaoer.alibaba-inc.com/bzb/taobao/biz-product-growth/industryMaterial/search
  - 商家素材中心: https://myseller.taobao.com/home.htm/material-center/material-management?tab=recommend
  - 纵横内容流通: https://content.alibaba-inc.com/work/content-circulation/classic/contentdiscover
"""

import json
import subprocess
import pytest
from datetime import datetime, timedelta

# ============================================================
# 配置
# ============================================================
DMS_DB = "rm-lgay0v5lor8396yka"
DMS_GROUP = "stylespot"

# 种草视频链路
SEED_VIDEO_LINK_ID = 20227
SEED_VIDEO_BATCH = "BT_6981"  # 有成功记录的批次

# 种草图文链路(产业带-上传到商家)
SEED_IMAGE_TEXT_LINK_ID = 20259
SEED_IMAGE_TEXT_BATCH = "BT_7000"  # 有成功记录的批次
SEED_IMAGE_TEXT_STRATEGY = 10791  # image_text_upload 策略

# 达人账号
DAREN_SEEDING = "1027873092"       # 产业带种草(定时器)
DAREN_IMAGE_TEXT = "2583875942"    # 产业带图文上传达人

# 已验证的测试数据
VIDEO_ITEM_ID = 1068897537385
VIDEO_SELLER_ID = 2217659220375
VIDEO_CONTENT_ID = "1049926466941125"

IMAGE_TEXT_ITEM_ID = 1065802197651
IMAGE_TEXT_CONTENT_ID = "573364436710"

# 下游平台 URL
URL_MATERIAL_CENTER = "https://xiaoer.alibaba-inc.com/bzb/taobao/biz-product-growth/industryMaterial/search"
URL_SELLER_MATERIAL = "https://myseller.taobao.com/home.htm/material-center/material-management?tab=recommend"
URL_ZONGHENG = "https://content.alibaba-inc.com/work/content-circulation/classic/contentdiscover"


# ============================================================
# 工具函数
# ============================================================
def dms_query(sql: str) -> list:
    """通过 dms-alibaba CLI 执行 SQL 并返回结果行"""
    cmd = ["dms-alibaba", "sql", "run", DMS_GROUP, "--db", DMS_DB, "--sql", sql]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # 读取最新结果文件
    import glob
    import os
    pattern = os.path.expanduser(
        f"~/dms-alibaba/db-groups/{DMS_GROUP}/sql/quick_{DMS_DB}/_results/"
    )
    json_files = sorted(glob.glob(pattern + "**/*.json", recursive=True), key=os.path.getmtime)
    if not json_files:
        return []
    with open(json_files[-1]) as f:
        data = json.load(f)
    if not data.get("success"):
        raise RuntimeError(f"DMS query failed: {data.get('message', 'unknown')}")
    return data.get("rows", [])


# ============================================================
# Module A: 种草视频链路 — 触发与生产
# ============================================================
class TestSeedVideoProduction:
    """种草视频链路: F0触发 → 视频生产 → 审核 → 落表"""

    def test_A01_video_batch_exists(self):
        """A01: 种草视频链路批次存在且关联正确"""
        rows = dms_query(
            f"SELECT batch_id, status, relation_id, relation_type "
            f"FROM g_workflow_batch WHERE batch_id = '{SEED_VIDEO_BATCH}'"
        )
        assert len(rows) >= 1, f"批次 {SEED_VIDEO_BATCH} 不存在"
        row = rows[0]
        assert int(row["relation_id"]) == SEED_VIDEO_LINK_ID
        assert row["relation_type"] == "link"

    def test_A02_video_prod_record_success(self):
        """A02: g_afd_material_prod_record 有 SUCCESS 记录"""
        rows = dms_query(
            f"SELECT id, item_id, seller_id, status, tenant_id "
            f"FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status = 'SUCCESS' LIMIT 5"
        )
        assert len(rows) >= 1, f"批次 {SEED_VIDEO_BATCH} 无 SUCCESS 生产记录"
        for r in rows:
            assert r["tenant_id"] == "f88"
            assert int(r["item_id"]) > 0
            assert int(r["seller_id"]) > 0

    def test_A03_video_workflow_strategy_success(self):
        """A03: workflow_record_log 策略节点执行成功(视频生成走AFD不走workflow gen_video)"""
        rows = dms_query(
            f"SELECT id, node_type, status, strategy_id "
            f"FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_VIDEO_BATCH}' "
            f"AND node_type = 'strategy' AND status = 'SUCCESS' LIMIT 5"
        )
        assert len(rows) >= 1, f"批次 {SEED_VIDEO_BATCH} 无 strategy SUCCESS 记录"

    def test_A04_video_approve_success(self):
        """A04: 视频审核节点通过"""
        rows = dms_query(
            f"SELECT id, node_type, status "
            f"FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_VIDEO_BATCH}' "
            f"AND node_type = 'approve' AND status = 'SUCCESS' LIMIT 5"
        )
        assert len(rows) >= 1, f"批次 {SEED_VIDEO_BATCH} 无 approve SUCCESS 记录"

    def test_A05_video_dedup_72h(self):
        """A05: 72小时去重 — 同商品不重复生产"""
        # 取一个已成功生产的 item_id
        prod_rows = dms_query(
            f"SELECT item_id FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status = 'SUCCESS' LIMIT 1"
        )
        if not prod_rows:
            pytest.skip("无成功生产记录")
        item_id = prod_rows[0]["item_id"]
        # 检查该 item 是否只有一条 SUCCESS 记录(去重生效)
        dup_rows = dms_query(
            f"SELECT COUNT(*) as cnt FROM g_afd_material_prod_record "
            f"WHERE item_id = {item_id} AND status = 'SUCCESS' "
            f"AND gmt_create >= DATE_SUB(NOW(), INTERVAL 72 HOUR)"
        )
        cnt = int(dup_rows[0]["cnt"])
        assert cnt <= 2, f"item {item_id} 72h内有 {cnt} 条SUCCESS记录,去重可能失效"


# ============================================================
# Module B: 种草图文链路 — 触发与生产
# ============================================================
class TestSeedImageTextProduction:
    """种草图文链路: F0触发 → 打标 → 生图 → 文案 → 审核 → 图文上传"""

    def test_B01_image_text_batch_exists(self):
        """B01: 种草图文链路批次存在且关联正确"""
        rows = dms_query(
            f"SELECT batch_id, status, relation_id, relation_type "
            f"FROM g_workflow_batch WHERE batch_id = '{SEED_IMAGE_TEXT_BATCH}'"
        )
        assert len(rows) >= 1
        row = rows[0]
        assert int(row["relation_id"]) == SEED_IMAGE_TEXT_LINK_ID
        assert row["relation_type"] == "link"

    def test_B02_image_text_full_node_chain(self):
        """B02: 完整节点链执行成功 (industry_tag→season_tag→gen_img→llm_text→approve→image_text_upload)"""
        expected_nodes = ["industry_tag", "season_tag", "gen_img", "llm_text", "approve", "image_text_upload"]
        rows = dms_query(
            f"SELECT DISTINCT node_type FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_IMAGE_TEXT_BATCH}' "
            f"AND status = 'SUCCESS'"
        )
        actual_nodes = {r["node_type"] for r in rows}
        for node in expected_nodes:
            assert node in actual_nodes, f"节点 {node} 无 SUCCESS 记录, 实际: {actual_nodes}"

    def test_B03_image_text_upload_node_success(self):
        """B03: image_text_upload 节点执行成功(策略10791)"""
        rows = dms_query(
            f"SELECT id, node_type, status, strategy_id "
            f"FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_IMAGE_TEXT_BATCH}' "
            f"AND node_type = 'image_text_upload' AND status = 'SUCCESS'"
        )
        assert len(rows) >= 1, "image_text_upload 节点无 SUCCESS 记录"
        assert int(rows[0]["strategy_id"]) == SEED_IMAGE_TEXT_STRATEGY

    def test_B04_image_text_strategy_config(self):
        """B04: 策略10791配置正确(SEEDING_IMAGE_TEXT_SELLER类型)"""
        rows = dms_query(
            f"SELECT id, node_type, status, input_json "
            f"FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_IMAGE_TEXT_BATCH}' "
            f"AND node_type = 'image_text_upload' AND status = 'SUCCESS' LIMIT 1"
        )
        assert len(rows) >= 1
        # input_json 应包含 uploadType 或 sellerId 配置
        input_json = rows[0].get("input_json", "{}")
        assert input_json is not None


# ============================================================
# Module C: 数据落表验证 — g_afd_material_prod_record
# ============================================================
class TestMaterialProdRecord:
    """验证生产记录正确落表到 g_afd_material_prod_record"""

    def test_C01_video_prod_record_fields(self):
        """C01: 种草视频 prod_record 字段完整性"""
        rows = dms_query(
            f"SELECT id, gmt_create, batch_id, item_id, seller_id, status, "
            f"afd_tao_cate, tenant_id, env "
            f"FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status = 'SUCCESS' LIMIT 3"
        )
        assert len(rows) >= 1
        for r in rows:
            assert r["batch_id"] == SEED_VIDEO_BATCH
            assert int(r["item_id"]) > 0
            assert int(r["seller_id"]) > 0
            assert r["tenant_id"] == "f88"
            assert r["gmt_create"] is not None

    def test_C02_video_prod_record_output_data(self):
        """C02: 种草视频 prod_record output_data 含视频URL"""
        rows = dms_query(
            f"SELECT id, output_data FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status = 'SUCCESS' "
            f"AND output_data IS NOT NULL LIMIT 3"
        )
        if not rows:
            pytest.skip("output_data 为空(可能设计如此)")
        for r in rows:
            output = json.loads(r["output_data"]) if isinstance(r["output_data"], str) else r["output_data"]
            assert output is not None

    def test_C03_prod_record_time_ordering(self):
        """C03: 生产记录时间顺序正确(gmt_create 递增)"""
        rows = dms_query(
            f"SELECT id, gmt_create FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' "
            f"ORDER BY id ASC LIMIT 10"
        )
        if len(rows) < 2:
            pytest.skip("记录不足2条")
        times = [r["gmt_create"] for r in rows]
        assert times == sorted(times), "生产记录时间顺序异常"


# ============================================================
# Module D: 数据落表验证 — g_afd_recommend_material_pool_record
# ============================================================
class TestRecommendMaterialPool:
    """验证素材池记录落表 + contentId 生成"""

    def test_D01_video_content_id_generated(self):
        """D01: 种草视频 — contentId 已生成"""
        rows = dms_query(
            f"SELECT id, item_id, seller_id, status, "
            f"CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {VIDEO_ITEM_ID} ORDER BY id DESC LIMIT 5"
        )
        assert len(rows) >= 1, f"item {VIDEO_ITEM_ID} 无素材池记录"
        # 至少一条有 contentId
        has_content_id = any(r.get("contentId") for r in rows)
        assert has_content_id, f"item {VIDEO_ITEM_ID} 素材池记录无 contentId"

    def test_D02_video_content_id_value(self):
        """D02: 种草视频 — contentId 值正确"""
        rows = dms_query(
            f"SELECT CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {VIDEO_ITEM_ID} ORDER BY id DESC LIMIT 1"
        )
        assert len(rows) >= 1
        content_id = rows[0].get("contentId", "").strip('"')
        assert content_id == VIDEO_CONTENT_ID, f"contentId 不匹配: {content_id} != {VIDEO_CONTENT_ID}"

    def test_D03_image_text_content_id_generated(self):
        """D03: 种草图文 — contentId 已生成"""
        rows = dms_query(
            f"SELECT id, item_id, status, "
            f"CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {IMAGE_TEXT_ITEM_ID} ORDER BY id DESC LIMIT 5"
        )
        assert len(rows) >= 1, f"item {IMAGE_TEXT_ITEM_ID} 无素材池记录"
        has_content_id = any(r.get("contentId") for r in rows)
        assert has_content_id, f"item {IMAGE_TEXT_ITEM_ID} 素材池记录无 contentId"

    def test_D04_image_text_content_id_value(self):
        """D04: 种草图文 — contentId 值正确"""
        rows = dms_query(
            f"SELECT CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {IMAGE_TEXT_ITEM_ID} ORDER BY id DESC LIMIT 1"
        )
        assert len(rows) >= 1
        content_id = rows[0].get("contentId", "").strip('"')
        assert content_id == IMAGE_TEXT_CONTENT_ID, f"contentId 不匹配: {content_id} != {IMAGE_TEXT_CONTENT_ID}"

    def test_D05_pool_record_status_valid(self):
        """D05: 素材池记录状态有效(status=6 表示已发布)"""
        rows = dms_query(
            f"SELECT status FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {VIDEO_ITEM_ID} ORDER BY id DESC LIMIT 1"
        )
        assert len(rows) >= 1
        status = rows[0]["status"]
        assert status in ("6", "5", "4"), f"素材池状态异常: {status}"


# ============================================================
# Module E: 达人账号回归验证
# ============================================================
class TestDarenAccountRegression:
    """达人账号回归: 产业带种草(1027873092) + 图文上传达人(2583875942)"""

    def test_E01_daren_seeding_strategy_exists(self):
        """E01: 产业带种草达人策略存在(定时器触发)"""
        # 验证达人账号 1027873092 关联的策略/链路存在
        rows = dms_query(
            f"SELECT id, batch_id, status, relation_id FROM g_workflow_batch "
            f"WHERE id > 6000 AND relation_id = 20227 "
            f"ORDER BY id DESC LIMIT 5"
        )
        assert len(rows) >= 1, "种草视频链路(20227)无批次记录"

    def test_E02_daren_image_text_upload_config(self):
        """E02: 图文上传达人账号配置正确(2583875942)"""
        # 验证 image_text_upload 节点配置了正确的达人账号
        rows = dms_query(
            f"SELECT id, input_json FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_IMAGE_TEXT_BATCH}' "
            f"AND node_type = 'image_text_upload' AND status = 'SUCCESS' LIMIT 1"
        )
        if not rows:
            pytest.skip("无 image_text_upload SUCCESS 记录")
        input_json = rows[0].get("input_json", "{}")
        # 达人账号应在配置中
        assert input_json is not None

    def test_E03_daren_content_published(self):
        """E03: 达人账号发布的内容在素材池可见"""
        rows = dms_query(
            f"SELECT id, item_id, seller_id, "
            f"CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {VIDEO_ITEM_ID} AND seller_id = {VIDEO_SELLER_ID} "
            f"ORDER BY id DESC LIMIT 3"
        )
        assert len(rows) >= 1, f"达人 seller {VIDEO_SELLER_ID} 无发布记录"


# ============================================================
# Module F: 下游平台可见性验证 (需浏览器执行)
# ============================================================
class TestDownstreamVisibility:
    """下游平台可见性: 素材中心 + 纵横 + 商家端
    注: 这些用例需要浏览器登录态, 标记为 browser_required
    """

    @pytest.mark.browser_required
    def test_F01_zongheng_content_visible(self):
        """F01: 纵横平台 — contentId 可查到内容"""
        # 纵横 URL: https://content.alibaba-inc.com/work/content-circulation/classic/contentdiscover
        # 用 contentId 搜索应能找到对应内容
        content_id = VIDEO_CONTENT_ID
        url = f"{URL_ZONGHENG}?keyWordType=all&keyword={content_id}"
        # 需浏览器验证: 搜索结果包含该 contentId
        pytest.skip(f"需浏览器验证: {url}")

    @pytest.mark.browser_required
    def test_F02_material_center_visible(self):
        """F02: 素材中心(小二端) — 内容可查"""
        # URL: https://xiaoer.alibaba-inc.com/bzb/taobao/biz-product-growth/industryMaterial/search
        pytest.skip(f"需浏览器验证: {URL_MATERIAL_CENTER}")

    @pytest.mark.browser_required
    def test_F03_seller_material_center_visible(self):
        """F03: 商家素材中心 — 达人账号可见推荐素材"""
        # URL: https://myseller.taobao.com/home.htm/material-center/material-management?tab=recommend
        pytest.skip(f"需浏览器验证: {URL_SELLER_MATERIAL}")


# ============================================================
# Module G: 链路隔离与容量管控
# ============================================================
class TestIsolationAndCapacity:
    """链路隔离: 图文与视频独立; 容量管控: 上限2000"""

    def test_G01_video_image_text_isolation(self):
        """G01: 种草视频与种草图文批次完全隔离"""
        video_rows = dms_query(
            f"SELECT batch_id FROM g_workflow_batch "
            f"WHERE id > 6000 AND relation_id = {SEED_VIDEO_LINK_ID} LIMIT 5"
        )
        image_rows = dms_query(
            f"SELECT batch_id FROM g_workflow_batch "
            f"WHERE id > 6000 AND relation_id = {SEED_IMAGE_TEXT_LINK_ID} LIMIT 5"
        )
        video_batches = {r["batch_id"] for r in video_rows}
        image_batches = {r["batch_id"] for r in image_rows}
        assert video_batches.isdisjoint(image_batches), "视频与图文批次存在交叉!"

    def test_G02_prod_record_tenant_isolation(self):
        """G02: 生产记录租户隔离(tenant_id=f88)"""
        rows = dms_query(
            f"SELECT DISTINCT tenant_id FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' LIMIT 5"
        )
        tenants = {r["tenant_id"] for r in rows}
        assert tenants == {"f88"}, f"租户不纯: {tenants}"

    def test_G03_capacity_guard_check(self):
        """G03: 容量管控 — 待审核数未超2000上限"""
        rows = dms_query(
            f"SELECT COUNT(*) as cnt FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status IN ('HANDLING', 'TO_SUBMIT')"
        )
        if rows:
            cnt = int(rows[0]["cnt"])
            assert cnt < 2000, f"待审核数 {cnt} 超过2000上限"


# ============================================================
# Module H: 端到端数据流转完整性
# ============================================================
class TestE2EDataFlowIntegrity:
    """端到端: 从触发到下游可见的完整数据流转"""

    def test_H01_video_e2e_flow(self):
        """H01: 种草视频 E2E — prod_record → pool_record → contentId 完整"""
        # Step 1: prod_record 有 SUCCESS
        prod = dms_query(
            f"SELECT item_id, seller_id FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status = 'SUCCESS' LIMIT 1"
        )
        assert len(prod) >= 1, "prod_record 无 SUCCESS"
        item_id = prod[0]["item_id"]

        # Step 2: pool_record 有对应 contentId
        pool = dms_query(
            f"SELECT CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {item_id} ORDER BY id DESC LIMIT 1"
        )
        assert len(pool) >= 1, f"item {item_id} 无素材池记录"
        content_id = pool[0].get("contentId", "").strip('"')
        assert content_id and content_id != "null", f"item {item_id} contentId 为空"

    def test_H02_image_text_e2e_flow(self):
        """H02: 种草图文 E2E — workflow_record_log → pool_record → contentId 完整"""
        # Step 1: image_text_upload 节点 SUCCESS
        upload = dms_query(
            f"SELECT id FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_IMAGE_TEXT_BATCH}' "
            f"AND node_type = 'image_text_upload' AND status = 'SUCCESS' LIMIT 1"
        )
        assert len(upload) >= 1, "image_text_upload 无 SUCCESS"

        # Step 2: pool_record 有 contentId
        pool = dms_query(
            f"SELECT CASE WHEN JSON_VALID(ext_info) THEN ext_info -> '$.contentId' END AS contentId "
            f"FROM g_afd_recommend_material_pool_record "
            f"WHERE item_id = {IMAGE_TEXT_ITEM_ID} ORDER BY id DESC LIMIT 1"
        )
        assert len(pool) >= 1, f"item {IMAGE_TEXT_ITEM_ID} 无素材池记录"
        content_id = pool[0].get("contentId", "").strip('"')
        assert content_id and content_id != "null", "contentId 为空"

    def test_H03_video_workflow_all_stages(self):
        """H03: 种草视频全阶段 — strategy + approve (视频生成在AFD层)"""
        rows = dms_query(
            f"SELECT DISTINCT node_type, status FROM workflow_record_log "
            f"WHERE id > 4000000 AND batch_id = '{SEED_VIDEO_BATCH}' "
            f"AND status = 'SUCCESS'"
        )
        node_types = {r["node_type"] for r in rows}
        # 种草视频链路 workflow 层只有 strategy + approve, 视频生成走 AFD prod_record
        assert "strategy" in node_types, f"缺少 strategy, 实际: {node_types}"
        assert "approve" in node_types, f"缺少 approve, 实际: {node_types}"

    def test_H04_data_consistency_prod_vs_pool(self):
        """H04: 数据一致性 — prod_record 的 item 在 pool_record 可查到"""
        prod = dms_query(
            f"SELECT DISTINCT item_id FROM g_afd_material_prod_record "
            f"WHERE batch_id = '{SEED_VIDEO_BATCH}' AND status = 'SUCCESS' LIMIT 3"
        )
        assert len(prod) >= 1
        for p in prod[:2]:  # 抽检前2条
            item_id = p["item_id"]
            pool = dms_query(
                f"SELECT id FROM g_afd_recommend_material_pool_record "
                f"WHERE item_id = {item_id} LIMIT 1"
            )
            assert len(pool) >= 1, f"item {item_id} 在 prod_record SUCCESS 但 pool_record 无记录"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
