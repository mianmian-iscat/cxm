/**
 * 汇金平台账单查询脚本
 * 
 * 用法：
 * node hj-bill-query.js <订单号> <业务类型 1> <业务类型 2> ...
 * 
 * 示例：
 * node hj-bill-query.js 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS
 */

const fs = require('fs');
const path = require('path');

// 自动探测 puppeteer-core 路径
function resolvePuppeteer() {
  const paths = [
    path.join(__dirname, '..', '..', 'node_modules', 'puppeteer-core'),
    '/usr/lib/node_modules/@agent-infra/mcp-server-browser/node_modules/puppeteer-core',
    'puppeteer-core'
  ];
  for (const p of paths) {
    try {
      return require(p);
    } catch (e) {
      continue;
    }
  }
  throw new Error('Cannot find puppeteer-core');
}
const puppeteer = resolvePuppeteer();

const CDP_URL = process.env.WEB_AUTO_CDP_URL || 'http://127.0.0.1:9222';
const BASE_URL = 'https://pre-hjratingconsole.alibaba-inc.com/hjratingconsole/faq/billQuery.htm';

async function queryBill(orderId, targetBizTypes) {
  console.log(`🔍 开始查询订单：${orderId}`);
  console.log(`📋 目标业务类型：${targetBizTypes.join(', ')}`);
  
  const browser = await puppeteer.connect({ 
    browserURL: CDP_URL, 
    defaultViewport: null 
  });
  
  try {
    const pages = await browser.pages();
    let page = pages.find(p => p.url().includes('hjratingconsole'));
    
    if (!page) {
      page = await browser.newPage();
    }
    
    await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 30000 });
    
    // 等待页面加载
    await new Promise(r => setTimeout(r, 2000));
    
    // 填写外部订单号
    console.log('📝 填写订单号...');
    await page.evaluate((orderId) => {
      const inputs = document.querySelectorAll('input[type="text"]');
      for (let input of inputs) {
        if (!input.value && input.type === 'text') {
          input.value = orderId;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
          break;
        }
      }
    }, orderId);
    
    await new Promise(r => setTimeout(r, 500));
    
    // 点击一键排查按钮
    console.log('🔎 点击查询按钮...');
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('button');
      for (let btn of buttons) {
        if (btn.textContent.includes('一键排查') && !btn.textContent.includes('春风')) {
          btn.click();
          break;
        }
      }
    });
    
    // 等待查询结果加载
    console.log('⏳ 等待查询结果...');
    await new Promise(r => setTimeout(r, 5000));
    
    // 提取查询结果
    console.log('📊 提取查询结果...');
    const results = await page.evaluate((targetBizTypes) => {
      const results = {
        orderId: '',
        userId: '',
        orderStatus: '',
        messages: [],
        details: [],
        bills: []
      };
      
      const statusText = document.body.innerText;
      const orderMatch = statusText.match(/订单号：(\d+)\s+为主子合一订单\s*,\s*订单状态为\s+(\d+\s*-\s*[^,\n]+)/);
      if (orderMatch) {
        results.orderId = orderMatch[1];
        results.orderStatus = orderMatch[2].trim();
      }
      
      const userIdMatch = statusText.match(/用户 id\(商家 id\)\s*：\s*(\d+)/);
      if (userIdMatch) {
        results.userId = userIdMatch[1];
      }
      
      const tables = document.querySelectorAll('table');
      let currentTableType = '';
      
      for (let table of tables) {
        const headers = table.querySelectorAll('thead th, tr:first-child th');
        const headerText = Array.from(headers).map(h => h.textContent.trim()).join(' ');
        
        if (headerText.includes('业务类型 (bizType)') && headerText.includes('消息体')) {
          currentTableType = 'message';
        } else if (headerText.includes('业务类型 (bizType)') && headerText.includes('消息 ID')) {
          currentTableType = 'detail';
        } else if (headerText.includes('业务类型 (bizType)') && headerText.includes('账单科目')) {
          currentTableType = 'bill';
        } else {
          continue;
        }
        
        const rows = table.querySelectorAll('tbody tr, tr');
        for (let row of rows) {
          const cells = row.querySelectorAll('td');
          if (cells.length < 10) continue;
          
          const rowData = Array.from(cells).map(cell => {
            const link = cell.querySelector('a');
            return link ? link.textContent.trim() : cell.textContent.trim();
          });
          
          let bizTypeIndex = -1;
          for (let i = 0; i < headers.length; i++) {
            if (headers[i].textContent.includes('业务类型') || headers[i].textContent.includes('bizType')) {
              bizTypeIndex = i;
              break;
            }
          }
          
          if (bizTypeIndex === -1 || bizTypeIndex >= rowData.length) continue;
          
          const bizType = rowData[bizTypeIndex];
          
          if (targetBizTypes.includes(bizType)) {
            const record = { bizType: bizType, rawData: rowData };
            
            if (currentTableType === 'message') {
              record.id = rowData[0];
              record.userId = rowData[1];
              record.businessTime = rowData[2];
              record.createTime = rowData[3];
              record.modifyTime = rowData[4];
              record.status = rowData[12];
              record.env = rowData[11];
              record.processCount = rowData[9];
              record.errorCode = rowData[14];
              results.messages.push(record);
            } else if (currentTableType === 'detail') {
              record.id = rowData[0];
              record.user = rowData[1];
              record.tradeAmount = rowData[2];
              record.amount = rowData[3];
              record.businessTime = rowData[5];
              record.createTime = rowData[6];
              record.subject = rowData[12];
              record.status = rowData[16];
              results.details.push(record);
            } else if (currentTableType === 'bill') {
              record.id = rowData[0];
              record.user = rowData[1];
              record.tradeAmount = rowData[2];
              record.amount = rowData[3];
              record.unwrittenAmount = rowData[4];
              record.businessTime = rowData[5];
              record.createTime = rowData[6];
              record.modifyTime = rowData[7];
              record.subject = rowData[12];
              record.status = rowData[16];
              record.errorCode = rowData[17];
              record.alipayMerchantId = rowData[23];
              record.alipayPlatformId = rowData[24];
              results.bills.push(record);
            }
          }
        }
      }
      
      return results;
    }, targetBizTypes);
    
    browser.disconnect();
    return results;
    
  } catch (error) {
    console.error('❌ 查询失败:', error);
    browser.disconnect();
    throw error;
  }
}

function formatResults(results) {
  let output = '## 📊 汇金平台账单查询结果\n\n';
  output += `**订单号**: \`${results.orderId}\`\n`;
  output += `**用户 ID**: \`${results.userId}\`\n`;
  output += `**订单状态**: ${results.orderStatus}\n\n`;
  
  output += '### 📨 消息查询结果\n\n';
  if (results.messages.length === 0) {
    output += '⚠️ 未找到匹配的消息记录\n\n';
  } else {
    for (const msg of results.messages) {
      output += `**业务类型**: \`${msg.bizType}\`\n`;
      output += `- ID: ${msg.id} | 状态：${msg.status} | 环境：${msg.env}\n`;
      output += `- 业务时间：${msg.businessTime} | 创建时间：${msg.createTime}\n`;
      if (msg.errorCode) output += `- 错误码：${msg.errorCode}\n`;
      output += '\n';
    }
  }
  
  output += '### 📋 详单查询结果\n\n';
  if (results.details.length === 0) {
    output += '⚠️ 未找到匹配的详单记录\n\n';
  } else {
    for (const detail of results.details) {
      output += `**业务类型**: \`${detail.bizType}\`\n`;
      output += `- ID: ${detail.id} | 状态：${detail.status}\n`;
      output += `- 交易额：${detail.tradeAmount} | 金额：${detail.amount}\n`;
      output += `- 业务时间：${detail.businessTime} | 科目：${detail.subject}\n`;
      output += '\n';
    }
  }
  
  output += '### 💰 账单查询结果\n\n';
  if (results.bills.length === 0) {
    output += '⚠️ 未找到匹配的账单记录\n\n';
  } else {
    for (const bill of results.bills) {
      output += `**业务类型**: \`${bill.bizType}\`\n`;
      output += `- ID: ${bill.id} | 状态：${bill.status}\n`;
      output += `- 交易额：${bill.tradeAmount} | 金额：${bill.amount} | 未销金额：${bill.unwrittenAmount}\n`;
      output += `- 业务时间：${bill.businessTime} | 创建时间：${bill.createTime} | 修改时间：${bill.modifyTime}\n`;
      output += `- 科目：${bill.subject}\n`;
      if (bill.errorCode) output += `- 错误码：${bill.errorCode}\n`;
      if (bill.alipayMerchantId) output += `- 商家支付宝 ID: ${bill.alipayMerchantId}\n`;
      if (bill.alipayPlatformId) output += `- 平台支付宝 ID: ${bill.alipayPlatformId}\n`;
      output += '\n';
    }
  }
  
  return output;
}

async function main() {
  const args = process.argv.slice(2);
  
  if (args.length < 2) {
    console.log('用法：node hj-bill-query.js <订单号> <业务类型 1> [业务类型 2] ...');
    console.log('示例：node hj-bill-query.js 5115769992032011830 TB_FUSHI_CD_LIVE_YJ_REFUND_STD_PROCESS TB_FUSHI_CD_LIVE_YJ_STD_PROCESS');
    process.exit(1);
  }
  
  const orderId = args[0];
  const targetBizTypes = args.slice(1);
  
  const results = await queryBill(orderId, targetBizTypes);
  const formattedOutput = formatResults(results);
  
  console.log(formattedOutput);
  
  const artifactsDir = path.join(__dirname, '..', '..', 'artifacts');
  if (!fs.existsSync(artifactsDir)) {
    fs.mkdirSync(artifactsDir, { recursive: true });
  }
  const outputPath = path.join(artifactsDir, `hj-bill-query-${orderId}-${Date.now()}.md`);
  fs.writeFileSync(outputPath, formattedOutput);
  console.log(`\n💾 结果已保存到：${outputPath}`);
}

main().catch(console.error);
