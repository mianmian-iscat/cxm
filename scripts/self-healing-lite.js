/**
 * scripts/self-healing-lite.js
 *
 * 轻量自愈引擎（Node 侧），对标 Python 端 core/self_healing.py 的 10 种策略中最高频的 5 种，
 * 专门覆盖 Puppeteer 直连执行链路（run-browser-test.js）原本没有接入自愈的断层。
 *
 * 5 大策略（按优先级顺序）：
 *   1. SELECTOR_FALLBACK   用例提供 selectorCandidates[] 列表，逐个重试
 *   2. CDP_RELOCATE        selector 失效 → 用 aria-label / role / text 重新定位
 *   3. KNOWLEDGE_FIX       命中「已知 AntD 组件迁移表」自动改写 selector
 *   4. TEXT_FALLBACK       clickText 用文本兜底（含 trim 匹配）
 *   5. NETWORK_RETRY       网络错误 → 等待 + 重试当前 step 一次
 *
 * 用法（在 run-browser-test.js 的 catch 块内调用）：
 *   const healed = await SelfHealingLite.tryHeal(page, step, error, { knowledge });
 *   if (healed.success) { stepResult.healing = healed; } else { break; }
 */
'use strict';

// ────────────────────────────────────────────────────────────────────────────
// 1. 知识库：AntD 组件升级常见选择器修正（来自截图中的"DOM 选择器修正表"）
// ────────────────────────────────────────────────────────────────────────────
const _DEFAULT_KNOWLEDGE = [
  // 参与人标签：.ant-tag → .ant-select-selection-item
  { from: /\.ant-tag\b/, to: '.ant-select-selection-item', reason: 'AntD 5.x Select tag 类名迁移' },
  // 下拉项：.ant-select-dropdown-menu-item → .ant-select-item-option-content
  { from: /ant-select-dropdown-menu-item/, to: '.ant-select-item-option-content', reason: 'AntD 5.x Select 下拉项类名迁移' },
  // Modal 按钮文案
  { from: /^确认$/, to: '确认导入', reason: '批量导入确认按钮文案变更', context: 'modal' },
  { from: /^确定$/, to: '确认清空', reason: '清空确认按钮文案变更', context: 'modal' },
  { from: /^取消$/, to: '取 消', reason: 'AntD Modal 取消按钮中间带空格', context: 'modal', trim: true },
];

// ────────────────────────────────────────────────────────────────────────────
// 2. 自愈入口
// ────────────────────────────────────────────────────────────────────────────
class SelfHealingLite {
  constructor({ knowledge = _DEFAULT_KNOWLEDGE, logger = console } = {}) {
    this.knowledge = knowledge;
    this.logger = logger;
    this.stats = { attempts: 0, success: 0, byStrategy: {} };
  }

  /**
   * 尝试自愈。返回 { success, strategy, healedSelector, reason, retried? }
   * 策略按优先级顺序执行，先成功的赢。
   *
   * @param {import('puppeteer').Page} page
   * @param {object} step  当前 step（含 selector / text / selectorCandidates 等）
   * @param {Error}  error 原始错误
   * @param {object} opts  额外上下文（knowledge / retryMs）
   */
  async tryHeal(page, step, error, opts = {}) {
    this.stats.attempts += 1;
    const msg = (error && error.message) || '';

    // 5) 网络错误 → 简单等待重试（不走其他策略）
    if (this._isNetworkError(msg)) {
      return await this._tryNetworkRetry(page, step, opts);
    }

    // 仅处理"找不到元素"类错误
    if (!this._isElementNotFoundError(msg)) {
      return { success: false, strategy: 'none', reason: '非元素定位错误，跳过自愈' };
    }

    // 1) SELECTOR_FALLBACK
    if (Array.isArray(step.selectorCandidates) && step.selectorCandidates.length) {
      const r = await this._trySelectorCandidates(page, step, step.selectorCandidates);
      if (r.success) return this._record('SELECTOR_FALLBACK', r);
    }

    // 3) KNOWLEDGE_FIX（知识库优先于通用 CDP_RELOCATE）
    if (step.selector) {
      const r = await this._tryKnowledgeFix(page, step);
      if (r.success) return this._record('KNOWLEDGE_FIX', r);
    }

    // 2) CDP_RELOCATE（aria-label / role / text）
    {
      const r = await this._tryCdpRelocate(page, step);
      if (r.success) return this._record('CDP_RELOCATE', r);
    }

    // 4) TEXT_FALLBACK（clickText 兜底：trim 匹配）
    if (step.text) {
      const r = await this._tryTextFallback(page, step);
      if (r.success) return this._record('TEXT_FALLBACK', r);
    }

    return { success: false, strategy: 'none', reason: '所有策略均未命中' };
  }

  getStats() { return { ...this.stats }; }

  // ──────────────────────────────────────────────────────────────────────────
  // 内部策略
  // ──────────────────────────────────────────────────────────────────────────
  _record(strategy, r) {
    this.stats.success += 1;
    this.stats.byStrategy[strategy] = (this.stats.byStrategy[strategy] || 0) + 1;
    return { success: true, strategy, ...r };
  }

  _isElementNotFoundError(msg) {
    return /找不到元素|No node found|TimeoutError|waiting for selector|no element/i.test(msg);
  }

  _isNetworkError(msg) {
    return /ERR_ABORTED|net::|ECONNRESET|ETIMEDOUT|socket hang up|Timeout exceeded/i.test(msg);
  }

  // 策略 1：selectorCandidates 逐个重试
  async _trySelectorCandidates(page, step, candidates) {
    for (const sel of candidates) {
      if (sel === step.selector) continue;
      try {
        const el = await page.waitForSelector(sel, { timeout: 2000, visible: true });
        if (!el) continue;
        await this._performAction(page, step, el);
        return { success: true, healedSelector: sel, reason: `selectorCandidates 命中: ${sel}` };
      } catch (_) { /* continue */ }
    }
    return { success: false };
  }

  // 策略 3：知识库匹配
  async _tryKnowledgeFix(page, step) {
    const origSel = step.selector;
    for (const rule of this.knowledge) {
      let newSel = null;
      if (rule.from instanceof RegExp && rule.from.test(origSel)) {
        newSel = origSel.replace(rule.from, rule.to);
      } else if (typeof rule.from === 'string' && origSel.includes(rule.from)) {
        newSel = origSel.replace(rule.from, rule.to);
      }
      if (!newSel || newSel === origSel) continue;
      try {
        const el = await page.waitForSelector(newSel, { timeout: 2000, visible: true });
        if (!el) continue;
        await this._performAction(page, step, el);
        return {
          success: true,
          healedSelector: newSel,
          originalSelector: origSel,
          reason: rule.reason || '知识库命中',
        };
      } catch (_) { /* continue */ }
    }
    return { success: false };
  }

  // 策略 2：CDP 重定位（aria-label / role / text）
  async _tryCdpRelocate(page, step) {
    const candidates = [];

    // aria-label
    if (step['aria-label'] || step.ariaLabel) {
      candidates.push(`[aria-label="${step['aria-label'] || step.ariaLabel}"]`);
    }
    // role + name
    if (step.role && step.name) {
      candidates.push(`[role="${step.role}"][name="${step.name}"]`);
    }
    // data-testid
    if (step.testId) {
      candidates.push(`[data-testid="${step.testId}"]`);
    }
    // 文本兜底：button/span/div 内含文本
    if (step.text) {
      const text = step.text.trim();
      candidates.push(
        `//button[contains(normalize-space(),"${text}")]`,
        `//span[normalize-space()="${text}"]`,
        `//a[normalize-space()="${text}"]`,
      );
    }

    for (const sel of candidates) {
      try {
        let el;
        if (sel.startsWith('//')) {
          const found = await page.$x(sel);
          el = found[0];
        } else {
          el = await page.waitForSelector(sel, { timeout: 1500, visible: true });
        }
        if (!el) continue;
        await this._performAction(page, step, el);
        return { success: true, healedSelector: sel, reason: `CDP 重定位命中: ${sel}` };
      } catch (_) { /* continue */ }
    }
    return { success: false };
  }

  // 策略 4：文本兜底（trim 匹配）
  async _tryTextFallback(page, step) {
    const text = (step.text || '').trim();
    if (!text) return { success: false };
    try {
      const clicked = await page.evaluate((targetText) => {
        const nodes = Array.from(document.querySelectorAll('button, a, span, div, label'));
        for (const el of nodes) {
          const visible = el.offsetParent !== null;
          if (!visible) continue;
          const txt = (el.textContent || '').trim();
          if (txt === targetText) {
            el.click();
            return true;
          }
        }
        return false;
      }, text);
      if (clicked) return { success: true, reason: `文本兜底匹配: "${text}"` };
    } catch (_) { /* ignore */ }
    return { success: false };
  }

  // 策略 5：网络错误重试
  async _tryNetworkRetry(page, step, opts) {
    const retryMs = opts.retryMs || 1500;
    try {
      await new Promise(r => setTimeout(r, retryMs));
      // 重新加载当前页面
      try { await page.reload({ waitUntil: 'domcontentloaded', timeout: 10000 }); } catch (_) {}
      return { success: false, reason: '已重试但需上层重新执行 step', retried: true };
    } catch (_) {
      return { success: false };
    }
  }

  // 根据 step.type 执行对应动作
  async _performAction(page, step, el) {
    switch (step.type) {
      case 'click':
      case 'clickText':
        await el.click();
        break;
      case 'hover':
        await el.hover();
        break;
      case 'fill':
        await el.click({ clickCount: 3 });
        await page.keyboard.type(step.value || '', { delay: 30 });
        break;
      default:
        throw new Error(`自愈不支持的 step type: ${step.type}`);
    }
  }
}

module.exports = { SelfHealingLite, DEFAULT_KNOWLEDGE: _DEFAULT_KNOWLEDGE };
