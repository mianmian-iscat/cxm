#!/usr/bin/env python3
"""
汇金平台账单查询 - 简化版
通过 browser 工具获取页面快照后，使用本脚本提取指定业务类型的结果

用法:
python hj-bill-query-simple.py <订单号> <业务类型 1> [业务类型 2] ...
"""

import sys
import json
import re

def parse_snapshot(snapshot_text, target_biz_types):
    """从 browser snapshot 文本中提取目标业务类型的记录"""
    results = {
        'orderId': '',
        'userId': '',
        'orderStatus': '',
        'messages': [],
        'details': [],
        'bills': []
    }
    
    # 提取订单信息
    order_match = re.search(r'订单号：(\d+)\s+为主子合一订单\s*,\s*订单状态为\s+(\d+\s*-\s*[^,\n]+)', snapshot_text)
    if order_match:
        results['orderId'] = order_match.group(1)
        results['orderStatus'] = order_match.group(2).strip()
    
    user_match = re.search(r'用户 id\(商家 id\)\s*：\s*(\d+)', snapshot_text)
    if user_match:
        results['userId'] = user_match.group(1)
    
    # 按表格类型分割
    sections = {
        'message': None,
        'detail': None,
        'bill': None
    }
    
    if '消息查询结果' in snapshot_text and '详单查询结果' in snapshot_text:
        msg_start = snapshot_text.index('消息查询结果')
        detail_start = snapshot_text.index('详单查询结果')
        bill_start = snapshot_text.index('账单查询结果') if '账单查询结果' in snapshot_text else len(snapshot_text)
        
        sections['message'] = snapshot_text[msg_start:detail_start]
        sections['detail'] = snapshot_text[detail_start:bill_start]
        sections['bill'] = snapshot_text[bill_start:bill_start + 50000]  # 限制长度
    
    # 提取每个 section 中的数据
    for section_name, section_text in sections.items():
        if not section_text:
            continue
            
        # 查找包含目标业务类型的行
        for biz_type in target_biz_types:
            # 使用正则查找包含业务类型的行
            pattern = rf'row.*?{re.escape(biz_type)}.*?"'
            matches = re.finditer(pattern, section_text, re.DOTALL)
            
            for match in matches:
                row_text = match.group(0)
                
                # 提取 cell 数据
                cells = re.findall(r'cell\s+"([^"]*)"', row_text)
                
                if len(cells) < 10:
                    continue
                
                record = {'bizType': biz_type, 'rawCells': cells}
                
                if section_name == 'message':
                    # 消息查询结果：id, 用户 ID, 业务时间，创建时间，修改时间，业务唯一号，外部订单号，业务类型，...
                    record['id'] = cells[0] if len(cells) > 0 else ''
                    record['userId'] = cells[1] if len(cells) > 1 else ''
                    record['businessTime'] = cells[2] if len(cells) > 2 else ''
                    record['createTime'] = cells[3] if len(cells) > 3 else ''
                    record['modifyTime'] = cells[4] if len(cells) > 4 else ''
                    record['status'] = cells[12] if len(cells) > 12 else ''
                    record['env'] = cells[11] if len(cells) > 11 else ''
                    record['processCount'] = cells[9] if len(cells) > 9 else ''
                    record['errorCode'] = cells[14] if len(cells) > 14 else ''
                    results['messages'].append(record)
                    
                elif section_name == 'detail':
                    # 详单查询结果：id, 用户，交易额，金额，比例，业务时间，消息时间，...
                    record['id'] = cells[0] if len(cells) > 0 else ''
                    record['user'] = cells[1] if len(cells) > 1 else ''
                    record['tradeAmount'] = cells[2] if len(cells) > 2 else ''
                    record['amount'] = cells[3] if len(cells) > 3 else ''
                    record['businessTime'] = cells[5] if len(cells) > 5 else ''
                    record['createTime'] = cells[13] if len(cells) > 13 else ''
                    record['subject'] = cells[11] if len(cells) > 11 else ''
                    record['status'] = cells[12] if len(cells) > 12 else ''
                    results['details'].append(record)
                    
                elif section_name == 'bill':
                    # 账单查询结果：id, 用户，交易额，金额，未销金额，创建时间，修改时间，销账时间，...
                    record['id'] = cells[0] if len(cells) > 0 else ''
                    record['user'] = cells[1] if len(cells) > 1 else ''
                    record['tradeAmount'] = cells[2] if len(cells) > 2 else ''
                    record['amount'] = cells[3] if len(cells) > 3 else ''
                    record['unwrittenAmount'] = cells[4] if len(cells) > 4 else ''
                    record['businessTime'] = cells[5] if len(cells) > 5 else ''
                    record['createTime'] = cells[6] if len(cells) > 6 else ''
                    record['modifyTime'] = cells[7] if len(cells) > 7 else ''
                    record['subject'] = cells[12] if len(cells) > 12 else ''
                    record['status'] = cells[13] if len(cells) > 13 else ''
                    record['errorCode'] = cells[14] if len(cells) > 14 else ''
                    record['alipayMerchantId'] = cells[17] if len(cells) > 17 else ''
                    record['alipayPlatformId'] = cells[18] if len(cells) > 18 else ''
                    results['bills'].append(record)
    
    # 去重
    for key in ['messages', 'details', 'bills']:
        seen = set()
        unique_records = []
        for record in results[key]:
            record_id = record.get('id', '')
            if record_id and record_id not in seen:
                seen.add(record_id)
                unique_records.append(record)
        results[key] = unique_records
    
    return results

def format_results(results):
    """格式化输出结果"""
    output = '## 📊 汇金平台账单查询结果\n\n'
    output += f'**订单号**: `{results["orderId"]}`\n'
    output += f'**用户 ID**: `{results["userId"]}`\n'
    output += f'**订单状态**: {results["orderStatus"]}\n\n'
    
    # 消息查询结果
    output += '### 📨 消息查询结果\n\n'
    if not results['messages']:
        output += '⚠️ 未找到匹配的消息记录\n\n'
    else:
        for msg in results['messages']:
            output += f"**业务类型**: `{msg['bizType']}`\n"
            output += f"- ID: {msg['id']} | 状态：{msg['status']} | 环境：{msg['env']}\n"
            output += f"- 业务时间：{msg['businessTime']} | 创建时间：{msg['createTime']}\n"
            if msg.get('errorCode'):
                output += f"- 错误码：{msg['errorCode']}\n"
            output += '\n'
    
    # 详单查询结果
    output += '### 📋 详单查询结果\n\n'
    if not results['details']:
        output += '⚠️ 未找到匹配的详单记录\n\n'
    else:
        for detail in results['details']:
            output += f"**业务类型**: `{detail['bizType']}`\n"
            output += f"- ID: {detail['id']} | 状态：{detail['status']}\n"
            output += f"- 交易额：{detail['tradeAmount']} | 金额：{detail['amount']}\n"
            output += f"- 业务时间：{detail['businessTime']} | 科目：{detail['subject']}\n"
            output += '\n'
    
    # 账单查询结果
    output += '### 💰 账单查询结果\n\n'
    if not results['bills']:
        output += '⚠️ 未找到匹配的账单记录\n\n'
    else:
        for bill in results['bills']:
            output += f"**业务类型**: `{bill['bizType']}`\n"
            output += f"- ID: {bill['id']} | 状态：{bill['status']}\n"
            output += f"- 交易额：{bill['tradeAmount']} | 金额：{bill['amount']} | 未销金额：{bill['unwrittenAmount']}\n"
            output += f"- 业务时间：{bill['businessTime']} | 创建时间：{bill['createTime']} | 修改时间：{bill['modifyTime']}\n"
            output += f"- 科目：{bill['subject']}\n"
            if bill.get('errorCode'):
                output += f"- 错误码：{bill['errorCode']}\n"
            if bill.get('alipayMerchantId'):
                output += f"- 商家支付宝 ID: {bill['alipayMerchantId']}\n"
            if bill.get('alipayPlatformId'):
                output += f"- 平台支付宝 ID: {bill['alipayPlatformId']}\n"
            output += '\n'
    
    return output

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('用法：python hj-bill-query-simple.py <订单号> <业务类型 1> [业务类型 2] ...')
        print('示例：python hj-bill-query-simple.py 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS')
        sys.exit(1)
    
    order_id = sys.argv[1]
    target_biz_types = sys.argv[2:]
    
    print(f'🔍 查询订单：{order_id}')
    print(f'📋 目标业务类型：{", ".join(target_biz_types)}')
    print('\n请粘贴 browser snapshot 输出，然后按 Ctrl+D (Unix) 或 Ctrl+Z (Windows) 结束输入...\n')
    
    snapshot_text = sys.stdin.read()
    results = parse_snapshot(snapshot_text, target_biz_types)
    output = format_results(results)
    
    print(output)
