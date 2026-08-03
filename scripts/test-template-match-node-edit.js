/**
 * F88 模板匹配节点编辑页面 - 全面自动化测试脚本
 * 
 * 覆盖范围：
 * 1. 所有表单字段（硬匹配字段、应用环节、应用场景、排序维度、目标匹配数量、疲劳度）
 * 2. 排序维度的增删改、拖拽排序
 * 3. 输出结果区域（匹配到的图组 1~4）
 * 4. 运行测试按钮功能
 * 5. 字段联动和验证逻辑
 * 
 * @author Web 自动化测试团队
 * @date 2026-07-07
 */

const puppeteer = require('puppeteer-core');

class NodeEditTemplateMatchPage {
  constructor(page) {
    this.page = page;
    this.selectors = {
      drawer: '.ant-drawer-open',
      hardMatchField: 'div.ant-form-item:has(label:has-text("硬匹配字段")) .ant-select',
      appStage: 'div.ant-form-item:has(label:has-text("应用环节")) .ant-select',
      appScene: 'div.ant-form-item:has(label:has-text("应用场景")) .ant-select',
      sortDimensions: '.ant-list-item',
      sortDimensionUp: '.ant-list-item-action button:has-text("↑")',
      sortDimensionDown: '.ant-list-item-action button:has-text("↓")',
      sortDimensionDelete: '.ant-list-item-action button:has-text("🗑")',
      targetCount: 'input[placeholder*="目标匹配数量"]',
      fatigue: 'input[placeholder*="疲劳度"]',
      runTestBtn: 'button:has-text("运行测试")',
      outputGroup: 'div:has-text("匹配到的图组")',
      outputGroupItem: '.ant-tag',
      saveBtn: 'button:has-text("保存")',
      closeBtn: '.ant-drawer-close'
    };
  }

  /**
   * 等待页面加载完成
   */
  async waitForLoad() {
    console.log('等待节点编辑抽屉加载...');
    await this.page.waitForSelector(this.selectors.drawer, { timeout: 10000 });
    await this.page.waitForTimeout(2000);
    console.log('✅ 抽屉已加载');
  }

  /**
   * 获取所有表单字段的当前值
   */
  async getAllFieldValues() {
    console.log('\n获取所有表单字段值...');
    const values = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return null;

      const result = {};
      
      // 硬匹配字段
      const hardMatchSelect = drawer.querySelector('div.ant-form-item label:has-text("硬匹配字段") + div .ant-select-selection-item');
      result.hardMatchField = hardMatchSelect?.textContent || '';

      // 应用环节
      const appStageSelect = drawer.querySelector('div.ant-form-item label:has-text("应用环节") + div .ant-select-selection-item');
      result.appStage = appStageSelect?.textContent || '';

      // 应用场景
      const appSceneSelect = drawer.querySelector('div.ant-form-item label:has-text("应用场景") + div .ant-select-selection-item');
      result.appScene = appSceneSelect?.textContent || '';

      // 排序维度
      const sortItems = drawer.querySelectorAll('.ant-list-item');
      result.sortDimensions = Array.from(sortItems).map(item => {
        const text = item.querySelector('.ant-list-item-meta-title')?.textContent || '';
        return text.trim();
      });

      // 目标匹配数量
      const targetCountInput = drawer.querySelector('input[placeholder*="目标匹配数量"]');
      result.targetCount = targetCountInput?.value || '';

      // 疲劳度
      const fatigueInput = drawer.querySelector('input[placeholder*="疲劳度"]');
      result.fatigue = fatigueInput?.value || '';

      return result;
    });

    console.log('表单字段值:', values);
    return values;
  }

  /**
   * 设置硬匹配字段
   */
  async setHardMatchField(fieldName) {
    console.log(`\n设置硬匹配字段: ${fieldName}`);
    
    const selectPos = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return null;
      
      const label = Array.from(drawer.querySelectorAll('label')).find(l => l.textContent.includes('硬匹配字段'));
      if (!label) return null;
      
      const formItem = label.closest('.ant-form-item');
      const select = formItem?.querySelector('.ant-select .ant-select-selector');
      if (!select) return null;
      
      const r = select.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    });

    if (!selectPos) {
      console.log('❌ 硬匹配字段下拉框未找到');
      return false;
    }

    await this.page.mouse.click(selectPos.x, selectPos.y);
    await this.page.waitForTimeout(1000);

    const optionPos = await this.page.evaluate((fieldName) => {
      const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      for (const dd of dropdowns) {
        const options = dd.querySelectorAll('.ant-select-item-option');
        for (const option of options) {
          if (option.textContent.trim() === fieldName) {
            const r = option.getBoundingClientRect();
            return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
          }
        }
      }
      return null;
    }, fieldName);

    if (optionPos) {
      await this.page.mouse.click(optionPos.x, optionPos.y);
      await this.page.waitForTimeout(500);
      console.log(`✅ 硬匹配字段已设置为: ${fieldName}`);
      return true;
    }

    console.log(`❌ 未找到选项: ${fieldName}`);
    return false;
  }

  /**
   * 设置应用环节
   */
  async setAppStage(stage) {
    console.log(`\n设置应用环节: ${stage}`);
    
    const selectPos = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return null;
      
      const label = Array.from(drawer.querySelectorAll('label')).find(l => l.textContent.includes('应用环节'));
      if (!label) return null;
      
      const formItem = label.closest('.ant-form-item');
      const select = formItem?.querySelector('.ant-select .ant-select-selector');
      if (!select) return null;
      
      const r = select.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    });

    if (!selectPos) {
      console.log('❌ 应用环节下拉框未找到');
      return false;
    }

    await this.page.mouse.click(selectPos.x, selectPos.y);
    await this.page.waitForTimeout(1000);

    const optionPos = await this.page.evaluate((stage) => {
      const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      for (const dd of dropdowns) {
        const options = dd.querySelectorAll('.ant-select-item-option');
        for (const option of options) {
          if (option.textContent.trim() === stage) {
            const r = option.getBoundingClientRect();
            return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
          }
        }
      }
      return null;
    }, stage);

    if (optionPos) {
      await this.page.mouse.click(optionPos.x, optionPos.y);
      await this.page.waitForTimeout(500);
      console.log(`✅ 应用环节已设置为: ${stage}`);
      return true;
    }

    console.log(`❌ 未找到选项: ${stage}`);
    return false;
  }

  /**
   * 设置应用场景
   */
  async setAppScene(scene) {
    console.log(`\n设置应用场景: ${scene}`);
    
    const selectPos = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return null;
      
      const label = Array.from(drawer.querySelectorAll('label')).find(l => l.textContent.includes('应用场景'));
      if (!label) return null;
      
      const formItem = label.closest('.ant-form-item');
      const select = formItem?.querySelector('.ant-select .ant-select-selector');
      if (!select) return null;
      
      const r = select.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    });

    if (!selectPos) {
      console.log('❌ 应用场景下拉框未找到');
      return false;
    }

    await this.page.mouse.click(selectPos.x, selectPos.y);
    await this.page.waitForTimeout(1000);

    const optionPos = await this.page.evaluate((scene) => {
      const dropdowns = document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
      for (const dd of dropdowns) {
        const options = dd.querySelectorAll('.ant-select-item-option');
        for (const option of options) {
          if (option.textContent.trim() === scene) {
            const r = option.getBoundingClientRect();
            return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
          }
        }
      }
      return null;
    }, scene);

    if (optionPos) {
      await this.page.mouse.click(optionPos.x, optionPos.y);
      await this.page.waitForTimeout(500);
      console.log(`✅ 应用场景已设置为: ${scene}`);
      return true;
    }

    console.log(`❌ 未找到选项: ${scene}`);
    return false;
  }

  /**
   * 获取排序维度列表
   */
  async getSortDimensions() {
    console.log('\n获取排序维度列表...');
    const dimensions = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return [];
      
      const items = drawer.querySelectorAll('.ant-list-item');
      return Array.from(items).map(item => {
        const title = item.querySelector('.ant-list-item-meta-title')?.textContent || '';
        return title.trim();
      });
    });

    console.log('排序维度:', dimensions);
    return dimensions;
  }

  /**
   * 上移排序维度
   */
  async moveSortDimensionUp(index) {
    console.log(`\n上移第 ${index + 1} 个排序维度...`);
    
    const moved = await this.page.evaluate((index) => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const items = drawer.querySelectorAll('.ant-list-item');
      if (index >= items.length) return false;
      
      const item = items[index];
      const upBtn = item.querySelector('.ant-list-item-action button:has-text("↑")');
      if (upBtn && !upBtn.disabled) {
        upBtn.click();
        return true;
      }
      return false;
    }, index);

    if (moved) {
      await this.page.waitForTimeout(500);
      console.log('✅ 上移成功');
    } else {
      console.log('❌ 上移失败（可能已是第一项）');
    }
    return moved;
  }

  /**
   * 下移排序维度
   */
  async moveSortDimensionDown(index) {
    console.log(`\n下移第 ${index + 1} 个排序维度...`);
    
    const moved = await this.page.evaluate((index) => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const items = drawer.querySelectorAll('.ant-list-item');
      if (index >= items.length) return false;
      
      const item = items[index];
      const downBtn = item.querySelector('.ant-list-item-action button:has-text("↓")');
      if (downBtn && !downBtn.disabled) {
        downBtn.click();
        return true;
      }
      return false;
    }, index);

    if (moved) {
      await this.page.waitForTimeout(500);
      console.log('✅ 下移成功');
    } else {
      console.log('❌ 下移失败（可能已是最后一项）');
    }
    return moved;
  }

  /**
   * 删除排序维度
   */
  async deleteSortDimension(index) {
    console.log(`\n删除第 ${index + 1} 个排序维度...`);
    
    const deleted = await this.page.evaluate((index) => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const items = drawer.querySelectorAll('.ant-list-item');
      if (index >= items.length) return false;
      
      const item = items[index];
      const deleteBtn = item.querySelector('.ant-list-item-action button:has-text("🗑")');
      if (deleteBtn) {
        deleteBtn.click();
        return true;
      }
      return false;
    }, index);

    if (deleted) {
      await this.page.waitForTimeout(500);
      console.log('✅ 删除成功');
    } else {
      console.log('❌ 删除失败');
    }
    return deleted;
  }

  /**
   * 设置目标匹配数量
   */
  async setTargetCount(count) {
    console.log(`\n设置目标匹配数量: ${count}`);
    
    const set = await this.page.evaluate((count) => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const input = drawer.querySelector('input[placeholder*="目标匹配数量"]');
      if (input) {
        input.value = count.toString();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
      return false;
    }, count);

    if (set) {
      await this.page.waitForTimeout(500);
      console.log(`✅ 目标匹配数量已设置为: ${count}`);
    } else {
      console.log('❌ 设置失败');
    }
    return set;
  }

  /**
   * 设置疲劳度
   */
  async setFatigue(fatigue) {
    console.log(`\n设置疲劳度: ${fatigue}`);
    
    const set = await this.page.evaluate((fatigue) => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const input = drawer.querySelector('input[placeholder*="疲劳度"]');
      if (input) {
        input.value = fatigue.toString();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
      return false;
    }, fatigue);

    if (set) {
      await this.page.waitForTimeout(500);
      console.log(`✅ 疲劳度已设置为: ${fatigue}`);
    } else {
      console.log('❌ 设置失败');
    }
    return set;
  }

  /**
   * 点击运行测试按钮
   */
  async runTest() {
    console.log('\n点击运行测试按钮...');
    
    const clicked = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const btn = drawer.querySelector('button:has-text("运行测试")');
      if (btn && !btn.disabled) {
        btn.click();
        return true;
      }
      return false;
    });

    if (clicked) {
      await this.page.waitForTimeout(3000); // 等待测试运行完成
      console.log('✅ 运行测试已触发');
    } else {
      console.log('❌ 运行测试按钮未找到或已禁用');
    }
    return clicked;
  }

  /**
   * 获取输出结果（匹配到的图组）
   */
  async getOutputGroups() {
    console.log('\n获取输出结果...');
    const groups = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return [];
      
      // 查找"匹配到的图组"区域
      const outputSection = drawer.querySelector('div:has-text("匹配到的图组")');
      if (!outputSection) return [];
      
      // 查找所有图组
      const groupDivs = outputSection.querySelectorAll('div:has(> .ant-tag)');
      return Array.from(groupDivs).map(groupDiv => {
        const title = groupDiv.querySelector('div')?.textContent || '';
        const tags = Array.from(groupDiv.querySelectorAll('.ant-tag')).map(tag => ({
          text: tag.textContent.trim(),
          color: tag.className.includes('green') ? 'green' : 
                 tag.className.includes('blue') ? 'blue' : 'white'
        }));
        return { title, tags };
      });
    });

    console.log('输出图组数量:', groups.length);
    groups.forEach((group, i) => {
      console.log(`  图组 ${i + 1}: ${group.title} - ${group.tags.length} 项`);
    });
    return groups;
  }

  /**
   * 验证输出结果
   */
  async validateOutputGroups(expectedGroupCount = 4, expectedItemsPerGroup = 7) {
    console.log(`\n验证输出结果 (期望 ${expectedGroupCount} 个图组，每组 ${expectedItemsPerGroup} 项)...`);
    const groups = await this.getOutputGroups();
    
    if (groups.length !== expectedGroupCount) {
      console.log(`❌ 图组数量不符: 期望 ${expectedGroupCount}，实际 ${groups.length}`);
      return false;
    }

    let allValid = true;
    for (let i = 0; i < groups.length; i++) {
      const group = groups[i];
      if (group.tags.length !== expectedItemsPerGroup) {
        console.log(`❌ 图组 ${i + 1} 项数不符: 期望 ${expectedItemsPerGroup}，实际 ${group.tags.length}`);
        allValid = false;
      }
      
      // 验证颜色分布
      const greenCount = group.tags.filter(t => t.color === 'green').length;
      const blueCount = group.tags.filter(t => t.color === 'blue').length;
      const whiteCount = group.tags.filter(t => t.color === 'white').length;
      
      if (greenCount !== 1 || blueCount !== 1 || whiteCount !== 5) {
        console.log(`❌ 图组 ${i + 1} 颜色分布不符: 绿${greenCount} 蓝${blueCount} 白${whiteCount}`);
        allValid = false;
      }
    }

    if (allValid) {
      console.log('✅ 输出结果验证通过');
    }
    return allValid;
  }

  /**
   * 保存节点配置
   */
  async save() {
    console.log('\n点击保存按钮...');
    
    const saved = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const saveBtn = drawer.querySelector('button:has-text("保存")');
      if (saveBtn && !saveBtn.disabled) {
        saveBtn.click();
        return true;
      }
      return false;
    });

    if (saved) {
      await this.page.waitForTimeout(2000);
      console.log('✅ 保存成功');
    } else {
      console.log('❌ 保存按钮未找到或已禁用');
    }
    return saved;
  }

  /**
   * 等待节点更新提示
   */
  async waitForNodeUpdated() {
    console.log('\n等待"节点已更新"提示...');
    
    try {
      await this.page.waitForFunction(() => {
        const notices = document.querySelectorAll('.ant-message-notice, .ant-notification-notice');
        for (const notice of notices) {
          if (notice.textContent.includes('节点已更新')) {
            return true;
          }
        }
        return false;
      }, { timeout: 5000 });
      
      console.log('✅ 检测到"节点已更新"提示');
      await this.page.waitForTimeout(1000);
      return true;
    } catch (e) {
      console.log('❌ 未检测到"节点已更新"提示');
      return false;
    }
  }

  /**
   * 保存策略配置（外层保存按钮）
   */
  async saveStrategy() {
    console.log('\n点击策略保存按钮...');
    
    const saved = await this.page.evaluate(() => {
      // 查找"保存"按钮（在试运行按钮旁边）
      const buttons = Array.from(document.querySelectorAll('button'));
      const saveBtn = buttons.find(btn => {
        const text = btn.textContent.trim();
        return text === '保存' || text === '保 存';
      });
      
      if (saveBtn && !saveBtn.disabled) {
        saveBtn.click();
        return true;
      }
      return false;
    });

    if (saved) {
      console.log('✅ 策略保存按钮已点击');
      await this.page.waitForTimeout(2000);
    } else {
      console.log('❌ 策略保存按钮未找到或已禁用');
    }
    return saved;
  }

  /**
   * 等待保存成功提示
   */
  async waitForSaveSuccess() {
    console.log('\n等待"保存成功"提示...');
    
    try {
      await this.page.waitForFunction(() => {
        const notices = document.querySelectorAll('.ant-message-notice, .ant-notification-notice');
        for (const notice of notices) {
          if (notice.textContent.includes('保存成功')) {
            return true;
          }
        }
        return false;
      }, { timeout: 5000 });
      
      console.log('✅ 检测到"保存成功"提示');
      await this.page.waitForTimeout(1000);
      return true;
    } catch (e) {
      console.log('❌ 未检测到"保存成功"提示');
      return false;
    }
  }

  /**
   * 点击试运行按钮
   */
  async clickTestRun() {
    console.log('\n点击试运行按钮...');
    
    const clicked = await this.page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const testRunBtn = buttons.find(btn => btn.textContent.includes('试运行'));
      
      if (testRunBtn && !testRunBtn.disabled) {
        testRunBtn.click();
        return true;
      }
      return false;
    });

    if (clicked) {
      console.log('✅ 试运行按钮已点击');
      await this.page.waitForTimeout(2000);
    } else {
      console.log('❌ 试运行按钮未找到或已禁用');
    }
    return clicked;
  }

  /**
   * 填写试运行参数
   */
  async fillTestRunParams(params = {}) {
    console.log('\n填写试运行参数...');
    
    const filled = await this.page.evaluate((params) => {
      // 查找试运行弹窗
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (!modal) return false;
      
      // 填写 seller_id
      if (params.sellerId) {
        const sellerIdInput = modal.querySelector('input[placeholder*="seller_id"]');
        if (sellerIdInput) {
          sellerIdInput.value = params.sellerId;
          sellerIdInput.dispatchEvent(new Event('input', { bubbles: true }));
          sellerIdInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      
      // 填写其他参数...
      
      return true;
    }, params);

    if (filled) {
      console.log('✅ 试运行参数已填写');
    } else {
      console.log('❌ 试运行参数填写失败');
    }
    return filled;
  }

  /**
   * 点击单次运行
   */
  async clickSingleRun() {
    console.log('\n点击单次运行...');
    
    const clicked = await this.page.evaluate(() => {
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (!modal) return false;
      
      const buttons = Array.from(modal.querySelectorAll('button'));
      const runBtn = buttons.find(btn => btn.textContent.includes('单次运行') || btn.textContent.includes('运行'));
      
      if (runBtn && !runBtn.disabled) {
        runBtn.click();
        return true;
      }
      return false;
    });

    if (clicked) {
      console.log('✅ 单次运行已触发');
      await this.page.waitForTimeout(5000); // 等待运行完成
    } else {
      console.log('❌ 单次运行按钮未找到');
    }
    return clicked;
  }

  /**
   * 获取运行结果
   */
  async getRunResult() {
    console.log('\n获取运行结果...');
    
    const result = await this.page.evaluate(() => {
      // 查找运行结果区域
      const modal = document.querySelector('.ant-modal:not(.ant-modal-hidden)');
      if (!modal) return null;
      
      // 查找成功/失败提示
      const successMsg = modal.querySelector('.ant-message-success, .ant-alert-success');
      const errorMsg = modal.querySelector('.ant-message-error, .ant-alert-error');
      
      // 查找结果数据
      const resultData = {};
      const preElements = modal.querySelectorAll('pre');
      preElements.forEach(pre => {
        const text = pre.textContent.trim();
        if (text) {
          try {
            resultData.json = JSON.parse(text);
          } catch (e) {
            resultData.text = text;
          }
        }
      });
      
      return {
        success: !!successMsg,
        error: !!errorMsg,
        successText: successMsg?.textContent || '',
        errorText: errorMsg?.textContent || '',
        data: resultData
      };
    });

    console.log('运行结果:', result);
    return result;
  }

  /**
   * 关闭抽屉
   */
  async close() {
    console.log('\n关闭抽屉...');
    
    const closed = await this.page.evaluate(() => {
      const drawer = document.querySelector('.ant-drawer-open');
      if (!drawer) return false;
      
      const closeBtn = drawer.querySelector('.ant-drawer-close');
      if (closeBtn) {
        closeBtn.click();
        return true;
      }
      return false;
    });

    if (closed) {
      await this.page.waitForTimeout(1000);
      console.log('✅ 抽屉已关闭');
    } else {
      console.log('❌ 关闭失败');
    }
    return closed;
  }
}

/**
 * 完整测试流程
 */
async function runFullTest() {
  console.log('=== F88 模板匹配节点编辑页面 - 全面自动化测试 ===\n');

  // 1. 连接 Chrome
  console.log('1. 连接到 Chrome...');
  const browser = await puppeteer.connect({
    browserURL: 'http://127.0.0.1:9222',
    defaultViewport: null
  });
  const page = (await browser.pages())[0];
  console.log('✅ Chrome 已连接\n');

  // 2. 初始化页面对象
  const nodeEditPage = new NodeEditTemplateMatchPage(page);
  await nodeEditPage.waitForLoad();

  // 3. 获取初始表单值
  console.log('2. 获取初始表单值...');
  const initialValues = await nodeEditPage.getAllFieldValues();
  console.log('初始值:', initialValues);

  // 4. 设置硬匹配字段
  console.log('\n3. 设置硬匹配字段...');
  await nodeEditPage.setHardMatchField('seller_id');

  // 5. 设置应用环节
  console.log('\n4. 设置应用环节...');
  await nodeEditPage.setAppStage('视觉');

  // 6. 设置应用场景
  console.log('\n5. 设置应用场景...');
  await nodeEditPage.setAppScene('主图素材');

  // 7. 获取排序维度
  console.log('\n6. 获取排序维度...');
  const dimensions = await nodeEditPage.getSortDimensions();
  console.log('排序维度:', dimensions);

  // 8. 测试排序维度操作
  console.log('\n7. 测试排序维度操作...');
  if (dimensions.length > 1) {
    await nodeEditPage.moveSortDimensionUp(1);
    await nodeEditPage.moveSortDimensionDown(0);
  }

  // 9. 设置目标匹配数量
  console.log('\n8. 设置目标匹配数量...');
  await nodeEditPage.setTargetCount(4);

  // 10. 设置疲劳度
  console.log('\n9. 设置疲劳度...');
  await nodeEditPage.setFatigue(2);

  // 11. 运行测试（抽屉内的运行测试按钮）
  console.log('\n10. 运行测试（抽屉内）...');
  await nodeEditPage.runTest();

  // 12. 验证输出结果
  console.log('\n11. 验证输出结果...');
  const outputValid = await nodeEditPage.validateOutputGroups(4, 7);
  console.log('输出验证:', outputValid ? '✅ 通过' : '❌ 失败');

  // 13. 保存节点配置
  console.log('\n12. 保存节点配置...');
  await nodeEditPage.save();

  // 14. 等待"节点已更新"提示
  console.log('\n13. 等待"节点已更新"提示...');
  const nodeUpdated = await nodeEditPage.waitForNodeUpdated();
  console.log('节点更新提示:', nodeUpdated ? '✅ 检测到' : '❌ 未检测到');

  // 15. 关闭抽屉
  console.log('\n14. 关闭抽屉...');
  await nodeEditPage.close();

  // 16. 保存策略配置（外层保存按钮）
  console.log('\n15. 保存策略配置...');
  await nodeEditPage.saveStrategy();

  // 17. 等待"保存成功"提示
  console.log('\n16. 等待"保存成功"提示...');
  const saveSuccess = await nodeEditPage.waitForSaveSuccess();
  console.log('策略保存:', saveSuccess ? '✅ 成功' : '❌ 失败');

  // 18. 点击试运行
  console.log('\n17. 点击试运行...');
  await nodeEditPage.clickTestRun();

  // 19. 填写试运行参数
  console.log('\n18. 填写试运行参数...');
  await nodeEditPage.fillTestRunParams({
    sellerId: 'test_seller_123'
  });

  // 20. 点击单次运行
  console.log('\n19. 点击单次运行...');
  await nodeEditPage.clickSingleRun();

  // 21. 获取运行结果
  console.log('\n20. 获取运行结果...');
  const runResult = await nodeEditPage.getRunResult();
  console.log('运行结果:', runResult);

  // 22. 验证运行结果
  console.log('\n21. 验证运行结果...');
  if (runResult && runResult.success) {
    console.log('✅ 试运行成功');
    console.log('结果数据:', runResult.data);
  } else {
    console.log('❌ 试运行失败');
    console.log('错误信息:', runResult?.errorText || '未知错误');
  }

  // 23. 断开连接
  browser.disconnect();
  console.log('\n✅ 完整流程测试完成');
  
  return {
    nodeUpdated,
    saveSuccess,
    runResult,
    success: nodeUpdated && saveSuccess && runResult?.success
  };
}

// 执行测试
if (require.main === module) {
  runFullTest().catch(err => {
    console.error('测试失败:', err);
    process.exit(1);
  });
}

module.exports = { NodeEditTemplateMatchPage, runFullTest };
