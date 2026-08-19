#!/usr/bin/env python3
"""F88 失败数据两级聚类分析 — Devix 定时服务

架构: Flask(健康检查+手动触发) + APScheduler(定时执行)
数据源: dms-alibaba CLI 查询 workflow_record_log (env=staging)
输出: HTML 报告文件 + 钉钉群摘要推送
调度: 每日 09:00 / 14:00 / 19:00 执行

环境隔离红线: 仅查询 env=staging 数据，生产数据只读不动。
"""
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urlencode

import jieba
import numpy as np
import requests
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, jsonify
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

# ============================================================
# Config
# ============================================================

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw = f.read()
    # 展开 ${VAR} 环境变量占位符
    expanded = os.path.expandvars(raw)
    return yaml.safe_load(expanded)

CFG = load_config()

DMS_GROUP = CFG["dms"]["group"]
DMS_DB_ID = CFG["dms"]["db_id"]
DMS_QUERY_HOURS = CFG["dms"]["query_hours"]  # 查询最近 N 小时
DMS_ENV = CFG["dms"]["env"]  # 固定 staging

OUTPUT_DIR = Path(CFG["output"]["dir"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 钉钉：优先 config（已展开环境变量），fallback 直接读环境变量
DINGTALK_WEBHOOK = CFG.get("dingtalk", {}).get("webhook", "") or os.environ.get("DINGTALK_WEBHOOK", "")
DINGTALK_SECRET = CFG.get("dingtalk", {}).get("secret", "") or os.environ.get("DINGTALK_SECRET", "")
DINGTALK_ENABLED = bool(DINGTALK_WEBHOOK and DINGTALK_WEBHOOK.startswith("https://"))

TOP_K = CFG["clustering"]["top_k"]
SUB_MIN_SIZE = CFG["clustering"]["sub_min_size"]
TFIDF_MAX_FEATURES = CFG["clustering"]["tfidf_max_features"]

STOP_WORDS = set([
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "为", "中", "与", "及", "等",
    "存在", "执行", "失败", "节点", "图片", "结果",
])

COLORS = ['#1565c0', '#f9a825', '#2e7d32', '#7b1fa2', '#c62828',
          '#00838f', '#ef6c00', '#4527a0', '#ad1457', '#00695c']
SUB_COLORS = ['#42a5f5', '#ffca28', '#66bb6a', '#ab47bc', '#ef5350',
              '#26c6da', '#ffa726', '#7e57c2', '#ec407a', '#26a69a']

# ============================================================
# 1. Data loader — dms-alibaba CLI
# ============================================================

def fetch_failures_from_dms() -> list[dict]:
    """通过 dms-alibaba CLI 查询最近 N 小时失败记录 (env=staging)"""
    since = (datetime.now() - timedelta(hours=DMS_QUERY_HOURS)).strftime("%Y-%m-%d %H:%M:%S")

    sql = (
        "SELECT id, batch_id, node_type, status, "
        "LEFT(info, 800) AS info_trunc, gmt_create, gmt_modified "
        "FROM workflow_record_log "
        f"WHERE id > 4000000 AND env = '{DMS_ENV}' "
        f"AND status = 'FAIL' "
        f"AND gmt_create >= '{since}' "
        "ORDER BY id DESC LIMIT 2000"
    )

    cmd = [
        "dms-alibaba", "sql", "run", DMS_GROUP,
        "--db", DMS_DB_ID,
        "--sql", sql,
    ]

    print(f"[DMS] 查询最近 {DMS_QUERY_HOURS}h 失败数据 (env={DMS_ENV})...")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            print(f"[DMS] CLI 返回非零: {proc.stderr[:500]}")
            return []
    except FileNotFoundError:
        print("[DMS] dms-alibaba CLI 未安装，回退到本地文件")
        return _load_local_fallback()
    except subprocess.TimeoutExpired:
        print("[DMS] CLI 超时 (120s)")
        return []

    # 解析结果 JSON
    results_dir = Path.home() / "dms-alibaba" / "db-groups" / DMS_GROUP / "sql" / f"quick_{DMS_DB_ID}" / "_results"
    if not results_dir.exists():
        print(f"[DMS] 结果目录不存在: {results_dir}")
        return []

    # 找最新的结果文件
    latest = sorted(results_dir.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not latest:
        print("[DMS] 无结果文件")
        return []

    try:
        with open(latest[0], encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", [])
        # 从 info_trunc 中提取 error_msg
        for r in rows:
            r["error_msg"] = _extract_error_msg(r.get("info_trunc", ""))
        print(f"[DMS] 获取 {len(rows)} 条失败记录")
        return rows
    except Exception as e:
        print(f"[DMS] 解析失败: {e}")
        return []


def _extract_error_msg(info_trunc: str) -> str:
    """从 LEFT(info, 800) 中提取 errorMsg"""
    if not info_trunc:
        return ""
    try:
        info = json.loads(info_trunc) if info_trunc.startswith("{") else {}
        return info.get("errorMsg", "")
    except json.JSONDecodeError:
        # info 被截断，尝试正则提取
        m = re.search(r'"errorMsg"\s*:\s*"([^"]{1,200})', info_trunc)
        return m.group(1) if m else info_trunc[:200]


def _load_local_fallback() -> list[dict]:
    """本地开发回退：读取 _results 目录下最新 JSON"""
    results_dir = Path.home() / "dms-alibaba" / "db-groups" / DMS_GROUP / "sql" / f"quick_{DMS_DB_ID}" / "_results"
    if not results_dir.exists():
        return []
    latest = sorted(results_dir.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not latest:
        return []
    with open(latest[0], encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("rows", [])
    for r in rows:
        if "error_msg" not in r:
            r["error_msg"] = _extract_error_msg(r.get("info_trunc", r.get("info", "")))
    return rows


# ============================================================
# 2. Text preprocessing
# ============================================================

def clean_error_msg(msg: str) -> str:
    if not msg:
        return ""
    m = re.match(r'审核不通过,\s*原因:(.+)', msg)
    if m:
        reasons = list(dict.fromkeys([r.strip() for r in m.group(1).split(';') if r.strip()]))
        return "审核不通过: " + ";".join(reasons)
    if msg.strip() == "审核不通过, 原因未知":
        return "审核不通过: 原因未知"
    return msg.strip()


def tokenize(msg: str) -> str:
    words = jieba.lcut(msg)
    return " ".join(w for w in words if len(w) > 1 and w not in STOP_WORDS)


# ============================================================
# 3. Clustering engine
# ============================================================

def do_clustering(tfidf_matrix, n_clusters):
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(tfidf_matrix)
    return labels, km


def get_cluster_keywords(km, feature_names, top_n=8):
    keywords = {}
    for i in range(km.n_clusters):
        center = km.cluster_centers_[i]
        top_indices = center.argsort()[-top_n:][::-1]
        keywords[i] = [feature_names[idx] for idx in top_indices]
    return keywords


def find_optimal_k(tfidf_matrix, k_range=range(2, 6)):
    n_samples = tfidf_matrix.shape[0]
    max_k = min(max(k_range) + 1, n_samples // 3)
    if max_k < 2:
        return 2
    scores = []
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
        labels = km.fit_predict(tfidf_matrix)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(tfidf_matrix, labels, sample_size=min(200, n_samples))
        scores.append((k, score))
    if not scores:
        return 2
    return max(scores, key=lambda x: x[1])[0]


def make_label(keywords, samples):
    kw_set = set(keywords)
    sample_text = " ".join(samples[:5])

    # v1.2 已知治理签名（来源：生产链路稳定性提升方案 20260730）
    # 确定性签名优先匹配，命中直接返回治理标签，日报可对标治理进度
    _sig = sample_text.lower()
    KNOWN_SIGNATURES = [
        ("f88_4", "治理-1: ideaLAB额度耗尽 (F88_4/5)"),
        ("f88_5", "治理-1: ideaLAB额度耗尽 (F88_4/5)"),
        ("额度已消耗完", "治理-1: ideaLAB额度耗尽 (F88_4/5)"),
        ("was not found or your project does not have access", "治理-2: 模型不可用 (下线/无权限)"),
        ("resource_exhausted", "治理-3: 模型资源限流 (RESOURCE_EXHAUSTED)"),
        ("pl-002", "治理-4: 平台限流 (PL-002)"),
        ("video generation任务已达到", "治理-4: 平台限流 (PL-002)"),
        ("url_error-error_not_found", "治理-5: 模板URL失效 (URL_ERROR)"),
        ("url_error", "治理-5: 模板URL失效 (URL_ERROR)"),
    ]
    for pat, label in KNOWN_SIGNATURES:
        if pat in _sig:
            return label

    # v1.1 新增 4 类错误模式（与 f88-failure-analysis v0.5+ 错误目录对齐）
    V11_SIGNATURES = [
        ("sharedarraybuffer", "SharedArrayBuffer/COOP缺失 (BT_6149)"),
        ("cross-origin isolated", "SharedArrayBuffer/COOP缺失 (BT_6149)"),
        ("cross-origin-opener-policy", "SharedArrayBuffer/COOP缺失 (BT_6149)"),
        ("ffmpeg 引擎加载失败", "SharedArrayBuffer/COOP缺失 (BT_6149)"),
        ("subjobid", "subJobId 未传递 (BT_5976)"),
        ("sub_job_id", "subJobId 未传递 (BT_5976)"),
        ("trace lost", "subJobId 未传递 (BT_5976)"),
        ("stale url", "replaceImage 跨表不一致 (BT_6148)"),
        ("旧 url", "replaceImage 跨表不一致 (BT_6148)"),
        ("review_job.info 未更新", "replaceImage 跨表不一致 (BT_6148)"),
        ("mode mismatch", "BATCH/STREAM 模式差异"),
        ("模式不一致", "BATCH/STREAM 模式差异"),
    ]
    for pat, label in V11_SIGNATURES:
        if pat in _sig:
            return label
    if "batch" in _sig and "stream" in _sig:
        return "BATCH/STREAM 模式差异"
    if "execmode" in _sig:
        return "BATCH/STREAM 模式差异"

    # v1.3 新增签名（与 error-signatures.md v1.1.0 对齐，20260805）
    # 审核平台类 + LLM JSON 解析类，唯一归属见 F88测试知识库/references/patterns/error-signatures.md
    V13_SIGNATURES = [
        ("构建子任务失败", "审核任务分配校验不一致 (BT_7495)"),
        ("期望分配数量", "审核任务分配校验不一致 (BT_7495)"),
        ("与实际分配数量", "审核任务分配校验不一致 (BT_7495)"),
        ("docompletemaintaskifallpersonaldone", "审核回调三条件缺失 (BT_7485)"),
        ("审核完成不流转", "审核回调三条件缺失 (BT_7485)"),
        ("fastjson", "LLM JSON 解析异常 (BT_7417)"),
        ("error, offset", "LLM JSON 解析异常 (BT_7417)"),
    ]
    for pat, label in V13_SIGNATURES:
        if pat in _sig:
            return label

    if "未知" in kw_set or "原因未知" in sample_text:
        return "审核不通过: 原因未知"
    if "模特" in kw_set and "身材" in kw_set:
        return "审核: 模特身材问题"
    if "模特" in kw_set and ("畸形" in kw_set or "不合理" in kw_set):
        return "审核: 模特质量不达标"
    if "服装" in kw_set and ("一致" in kw_set or "细节" in kw_set):
        return "审核: 服装细节不一致"
    if "主品" in kw_set and ("模糊" in kw_set or "展示" in kw_set or "不全" in kw_set):
        return "审核: 主品展示问题"
    if "搭配" in kw_set and "美感" in kw_set:
        return "审核: 搭配美感差"
    if "水印" in kw_set:
        return "审核: 水印/质量标记"
    if "童装" in kw_set:
        return "审核: 童装不合规"
    if "算法" in kw_set and ("空" in kw_set or "返回" in kw_set):
        return "算法返回结果为空"
    if "生成" in kw_set:
        return "生成失败: 图片生成异常"
    kw_lower = " ".join(kw_set).lower()
    if "fastjson" in kw_lower or "json" in kw_lower:
        return "JSON 解析错误"
    if "模板" in kw_set or "模版" in kw_set or "匹配" in kw_set:
        return "模板匹配失败"
    if "tryon" in kw_set:
        return "Try-on 合成失败"
    if "accessory" in kw_set or "配饰" in kw_set:
        return "审核: 配饰不合理"
    if "claude" in kw_set:
        return "LLM (Claude) 返回空"
    if "参考图" in kw_set:
        return "审核: 参考图质量差"
    return " / ".join(keywords[:3])


def two_level_cluster(rows, cleaned_msgs, tokenized_texts, vectorizer):
    tfidf_all = vectorizer.fit_transform(tokenized_texts)
    feature_names = vectorizer.get_feature_names_out()

    print(f"  顶层聚类 k={TOP_K} ...")
    top_labels, top_km = do_clustering(tfidf_all, TOP_K)
    top_keywords = get_cluster_keywords(top_km, feature_names)
    top_dist = Counter(top_labels)

    result = {
        "top_labels": top_labels,
        "top_km": top_km,
        "top_keywords": top_keywords,
        "top_dist": top_dist,
        "clusters": {},
    }

    for cid in range(TOP_K):
        indices = [i for i, l in enumerate(top_labels) if l == cid]
        n = len(indices)

        cluster_data = {
            "indices": indices,
            "count": n,
            "keywords": top_keywords[cid],
            "samples": [cleaned_msgs[i] for i in indices[:8]],
            "node_dist": Counter(rows[i]["node_type"] for i in indices),
            "batch_dist": Counter(rows[i].get("batch_id", "unknown") for i in indices),
            "label": make_label(top_keywords[cid], [cleaned_msgs[i] for i in indices[:5]]),
            "sub_clusters": None,
            "sub_dist": None,
            "sub_keywords": None,
        }

        if n >= SUB_MIN_SIZE:
            sub_tfidf = tfidf_all[indices]
            sub_k = find_optimal_k(sub_tfidf, range(2, 5))
            print(f"    Cluster {cid} ({n} 条): 子聚类 k={sub_k} ...")
            sub_labels, sub_km = do_clustering(sub_tfidf, sub_k)
            sub_keywords = get_cluster_keywords(sub_km, feature_names, top_n=6)
            sub_dist = Counter(sub_labels)

            sub_clusters = {}
            for scid in range(sub_k):
                sub_indices = [indices[i] for i, sl in enumerate(sub_labels) if sl == scid]
                sub_samples = [cleaned_msgs[i] for i in sub_indices[:5]]
                sub_clusters[scid] = {
                    "indices": sub_indices,
                    "count": len(sub_indices),
                    "keywords": sub_keywords[scid],
                    "samples": sub_samples,
                    "node_dist": Counter(rows[i]["node_type"] for i in sub_indices),
                    "batch_dist": Counter(rows[i].get("batch_id", "unknown") for i in sub_indices),
                    "label": make_label(sub_keywords[scid], sub_samples),
                }

            cluster_data["sub_clusters"] = sub_clusters
            cluster_data["sub_dist"] = sub_dist
            cluster_data["sub_keywords"] = sub_keywords
        else:
            print(f"    Cluster {cid} ({n} 条): 样本不足，跳过子聚类")

        result["clusters"][cid] = cluster_data

    return result


# ============================================================
# 4. HTML report generator (same as v2, simplified for service)
# ============================================================

def generate_html(rows, cleaned_msgs, result, run_ts):
    total = len(rows)
    n_unique = len(set(cleaned_msgs))
    n_batches = len(set(r.get("batch_id", "") for r in rows if r.get("batch_id")))
    date_str = run_ts.strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>F88 聚类报告 {date_str}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background: #f5f7fa; color: #333; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 22px; font-weight: 600; margin-bottom: 6px; }}
  .subtitle {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }}
  .stat {{ background: white; border-radius: 10px; padding: 16px; border: 1px solid #e8ecf1; }}
  .stat .label {{ font-size: 11px; color: #888; text-transform: uppercase; }}
  .stat .value {{ font-size: 26px; font-weight: 700; color: #1565c0; margin-top: 2px; }}
  .section {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 16px; border: 1px solid #e8ecf1; }}
  .section h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; }}
  .bar-row {{ display: flex; align-items: center; margin-bottom: 6px; }}
  .bar-label {{ width: 220px; font-size: 12px; color: #444; text-align: right; padding-right: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .bar-track {{ flex: 1; height: 22px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 3px; display: flex; align-items: center; padding-left: 6px; font-size: 10px; color: white; font-weight: 600; }}
  .bar-count {{ width: 60px; font-size: 11px; color: #888; text-align: right; padding-left: 6px; }}
  .top-card {{ background: #f8fafc; border-radius: 8px; margin-bottom: 12px; border: 1px solid #e8ecf1; overflow: hidden; }}
  .top-header {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; cursor: pointer; }}
  .top-header:hover {{ background: #f0f4f8; }}
  .top-left {{ display: flex; align-items: center; gap: 10px; }}
  .top-icon {{ width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 14px; }}
  .top-name {{ font-weight: 600; font-size: 14px; }}
  .top-badge {{ background: #e3f2fd; color: #1565c0; padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }}
  .top-body {{ padding: 0 16px 12px; }}
  .sub-card {{ background: white; border-radius: 6px; padding: 10px 14px; margin-bottom: 6px; border: 1px solid #e8ecf1; margin-left: 42px; }}
  .sub-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }}
  .sub-name {{ font-weight: 600; font-size: 13px; }}
  .sub-badge {{ font-size: 10px; padding: 1px 7px; border-radius: 8px; font-weight: 600; }}
  .keyword {{ background: #e8ecf1; color: #555; padding: 1px 6px; border-radius: 3px; font-size: 10px; margin-right: 3px; }}
  .samples {{ font-size: 11px; color: #888; line-height: 1.5; margin-top: 3px; }}
  .node-tag {{ font-size: 9px; padding: 1px 5px; border-radius: 2px; background: #fff3e0; color: #e65100; margin-right: 3px; }}
  .batch-tag {{ font-size: 9px; padding: 1px 5px; border-radius: 2px; background: #f3e5f5; color: #6a1b9a; margin-right: 3px; }}
  .env-banner {{ background: #fce4ec; border-radius: 6px; padding: 12px 16px; border: 1px solid #ef9a9a; margin-bottom: 16px; font-size: 12px; color: #b71c1c; }}
</style>
</head>
<body>
<div class="container">
  <h1>F88 失败聚类分析报告</h1>
  <p class="subtitle">两级聚类 (顶层 k={TOP_K} + 二级子聚类) | {date_str} | env={DMS_ENV}</p>
  <div class="env-banner">
    <strong>环境隔离:</strong> 本报告仅基于 env={DMS_ENV} (预发) 数据。生产数据只读不动，禁止自愈操作。
  </div>
  <div class="stats">
    <div class="stat"><div class="label">总失败记录</div><div class="value">{total}</div></div>
    <div class="stat"><div class="label">唯一错误</div><div class="value">{n_unique}</div></div>
    <div class="stat"><div class="label">涉及批次</div><div class="value">{n_batches}</div></div>
  </div>
  <div class="section">
    <h2>顶层分布 (k={TOP_K})</h2>
"""

    top_dist = result["top_dist"]
    max_count = max(top_dist.values()) if top_dist else 1
    for cid in sorted(top_dist.keys(), key=lambda x: top_dist[x], reverse=True):
        cnt = top_dist[cid]
        pct = cnt / total * 100 if total else 0
        w = cnt / max_count * 100
        label = result["clusters"][cid]["label"]
        color = COLORS[cid % len(COLORS)]
        html += f'    <div class="bar-row"><div class="bar-label">{label}</div><div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{color}">{cnt}</div></div><div class="bar-count">{pct:.1f}%</div></div>\n'

    html += '  </div>\n  <div class="section"><h2>两级聚类详情</h2>\n'

    for cid in sorted(top_dist.keys(), key=lambda x: top_dist[x], reverse=True):
        cl = result["clusters"][cid]
        color = COLORS[cid % len(COLORS)]
        pct = cl["count"] / total * 100 if total else 0

        html += f'    <div class="top-card"><div class="top-header" onclick="let b=this.parentElement.querySelector(\'.top-body\');b.style.display=b.style.display===\'none\'?\'block\':\'none\'"><div class="top-left"><div class="top-icon" style="background:{color}">T{cid}</div><span class="top-name">{cl["label"]}</span></div><span class="top-badge">{cl["count"]} 条 ({pct:.1f}%)</span></div><div class="top-body">\n'

        for nt, nc in cl["node_dist"].most_common(3):
            html += f'      <span class="node-tag">{nt}: {nc}</span>\n'
        for bt, bc in cl["batch_dist"].most_common(3):
            html += f'      <span class="batch-tag">{bt}: {bc}</span>\n'

        if cl["sub_clusters"]:
            for scid in sorted(cl["sub_dist"].keys(), key=lambda x: cl["sub_dist"][x], reverse=True):
                sc = cl["sub_clusters"][scid]
                sub_color = SUB_COLORS[scid % len(SUB_COLORS)]
                sub_pct = sc["count"] / cl["count"] * 100 if cl["count"] else 0
                html += f'      <div class="sub-card" style="border-left:3px solid {sub_color}"><div class="sub-header"><span class="sub-name">{sc["label"]}</span><span class="sub-badge" style="background:{sub_color}20;color:{sub_color}">{sc["count"]} 条 ({sub_pct:.0f}%)</span></div><div>'
                for w in sc["keywords"][:5]:
                    html += f'<span class="keyword">{w}</span>'
                html += '</div><ul class="samples">'
                for s in sc["samples"][:2]:
                    html += f'<li>{s[:80]}</li>'
                html += '</ul></div>\n'
        else:
            html += '      <ul class="samples">'
            for s in cl["samples"][:3]:
                html += f'<li>{s[:100]}</li>'
            html += '</ul>\n'

        html += '    </div></div>\n'

    html += '  </div>\n</div>\n</body>\n</html>'
    return html


# ============================================================
# 5. DingTalk notification
# ============================================================

def send_dingtalk(run_ts, total, result):
    if not DINGTALK_ENABLED:
        print("[DingTalk] webhook 未配置，跳过推送")
        return

    date_str = run_ts.strftime("%Y-%m-%d %H:%M")
    top_dist = result["top_dist"]

    lines = [f"## F88 失败聚类分析 ({date_str})", ""]
    lines.append(f"**总失败记录:** {total} 条 | **env:** {DMS_ENV}")
    lines.append(f"**查询窗口:** 最近 {DMS_QUERY_HOURS} 小时")
    lines.append("")
    lines.append("### 顶层分类 (k=5)")
    lines.append("")

    for cid in sorted(top_dist.keys(), key=lambda x: top_dist[x], reverse=True):
        cl = result["clusters"][cid]
        pct = cl["count"] / total * 100 if total else 0
        lines.append(f"- **{cl['label']}** — {cl['count']} 条 ({pct:.1f}%)")
        if cl["sub_clusters"]:
            for scid in sorted(cl["sub_dist"].keys(), key=lambda x: cl["sub_dist"][x], reverse=True):
                sc = cl["sub_clusters"][scid]
                lines.append(f"  - {sc['label']}: {sc['count']} 条")

    lines.append("")
    lines.append("> 环境隔离: 仅分析 env=staging 数据，生产数据只读不动。")

    text = "\n".join(lines)

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"F88 聚类报告 {date_str}",
            "text": text,
        },
    }

    try:
        url = DINGTALK_WEBHOOK
        if DINGTALK_SECRET:
            ts = str(int(time.time() * 1000))
            string_to_sign = f"{ts}\n{DINGTALK_SECRET}"
            hmac_code = hmac.new(
                DINGTALK_SECRET.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            sign = quote_plus(base64.b64encode(hmac_code))
            url = f"{DINGTALK_WEBHOOK}&timestamp={ts}&sign={sign}"

        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print(f"[DingTalk] 推送成功 ({total} 条)")
        else:
            print(f"[DingTalk] 推送失败: {resp.text[:200]}")
    except Exception as e:
        print(f"[DingTalk] 推送异常: {e}")


# ============================================================
# 6. Main job runner
# ============================================================

_last_run = {"ts": None, "total": 0, "status": "never_run"}


def run_clustering_job():
    """定时任务入口"""
    global _last_run
    run_ts = datetime.now()
    print(f"\n{'='*60}")
    print(f"F88 聚类分析 — {run_ts.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # 1. 拉数据
    rows = fetch_failures_from_dms()
    if not rows:
        print("[Job] 无失败数据，跳过本次聚类")
        _last_run = {"ts": run_ts.isoformat(), "total": 0, "status": "no_data"}
        return

    # 2. 预处理
    cleaned_msgs = [clean_error_msg(r.get("error_msg", "")) for r in rows]
    valid_indices = [i for i, m in enumerate(cleaned_msgs) if m and len(m) > 2]
    filtered_rows = [rows[i] for i in valid_indices]
    filtered_msgs = [cleaned_msgs[i] for i in valid_indices]
    print(f"  有效记录: {len(filtered_msgs)} / {len(rows)}")

    if len(filtered_msgs) < TOP_K * 3:
        print(f"[Job] 有效记录不足 ({len(filtered_msgs)})，跳过聚类")
        _last_run = {"ts": run_ts.isoformat(), "total": len(filtered_msgs), "status": "too_few"}
        return

    tokenized = [tokenize(m) for m in filtered_msgs]

    # 3. 聚类
    vectorizer = TfidfVectorizer(max_features=TFIDF_MAX_FEATURES, token_pattern=r'(?u)\b\w+\b')
    result = two_level_cluster(filtered_rows, filtered_msgs, tokenized, vectorizer)

    # 4. 生成 HTML 报告
    html = generate_html(filtered_rows, filtered_msgs, result, run_ts)
    ts_str = run_ts.strftime("%Y%m%d_%H%M%S")
    report_name = f"f88-clustering-{ts_str}.html"
    report_path = OUTPUT_DIR / report_name
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  报告已保存: {report_path}")

    # 同时写一个 latest 软链接
    latest_link = OUTPUT_DIR / "f88-clustering-latest.html"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(report_path)

    # 5. 钉钉推送
    send_dingtalk(run_ts, len(filtered_msgs), result)

    # 6. 摘要日志
    print(f"\n  摘要: {len(filtered_msgs)} 条 / {TOP_K} 顶层分类")
    for cid in sorted(result["top_dist"].keys(), key=lambda x: result["top_dist"][x], reverse=True):
        cl = result["clusters"][cid]
        print(f"    T{cid} [{cl['label']}] {cl['count']} 条 ({cl['count']/len(filtered_msgs)*100:.1f}%)")

    _last_run = {
        "ts": run_ts.isoformat(),
        "total": len(filtered_msgs),
        "status": "success",
        "report": report_name,
        "clusters": {str(cid): result["clusters"][cid]["label"] for cid in result["clusters"]},
    }


# ============================================================
# 7. Flask app
# ============================================================

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({
        "service": "f88-clustering",
        "status": "ok",
        "last_run": _last_run,
        "env": DMS_ENV,
        "dingtalk_enabled": DINGTALK_ENABLED,
    })


@app.route("/run", methods=["POST"])
def trigger_run():
    """手动触发一次聚类分析"""
    import threading
    threading.Thread(target=run_clustering_job, daemon=True).start()
    return jsonify({"message": "clustering job started in background", "env": DMS_ENV})


@app.route("/config")
def show_config():
    return jsonify({
        "dms_group": DMS_GROUP,
        "dms_db_id": DMS_DB_ID,
        "query_hours": DMS_QUERY_HOURS,
        "env": DMS_ENV,
        "top_k": TOP_K,
        "sub_min_size": SUB_MIN_SIZE,
        "output_dir": str(OUTPUT_DIR),
        "dingtalk_enabled": DINGTALK_ENABLED,
    })


# ============================================================
# 8. Scheduler + entry point
# ============================================================

SCHEDULE_HOURS = CFG.get("schedule", {}).get("hours", [9, 14, 19])
SERVER_PORT = int(CFG.get("server", {}).get("port", 5100))

def create_scheduler():
    scheduler = BackgroundScheduler(timezone=CFG.get("schedule", {}).get("timezone", "Asia/Shanghai"))
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            run_clustering_job,
            CronTrigger(hour=hour, minute=0),
            id=f"clustering_{hour:02d}00",
            name=f"F88 聚类分析 {hour:02d}:00",
        )
    return scheduler


if __name__ == "__main__":
    hours_str = " / ".join(f"{h:02d}:00" for h in SCHEDULE_HOURS)
    print("F88 失败聚类分析服务启动")
    print(f"  调度: 每日 {hours_str}")
    print(f"  数据源: DMS {DMS_GROUP}/{DMS_DB_ID} (env={DMS_ENV})")
    print(f"  输出: {OUTPUT_DIR}")
    print(f"  钉钉: {'已配置' if DINGTALK_ENABLED else '未配置'}")

    scheduler = create_scheduler()
    scheduler.start()

    # 启动 Flask（优先读环境变量 PORT，其次 config.yaml server.port）
    port = int(os.environ.get("PORT", SERVER_PORT))
    print(f"  Flask: http://0.0.0.0:{port}")
    print(f"  端点: /health | /run (POST) | /config")

    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("\n服务已停止")
