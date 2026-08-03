// 补丁：为 selectOption 添加 placeholderText 支持
// 使用方法：在 impl.py 中调用前 patch 或直接修改 _node_bridge.js

const patchSelectOption = `
      // 2. 定位 selector → 获取坐标（支持 labelText 或 placeholderText 两种方式）
      const selectorCoords = await page.evaluate((lText, pText, lClass) => {
        let label = null;
        let item = null;

        // 方式 A: 通过 labelText 找 label 元素
        if (lText) {
          const labels = [...document.querySelectorAll('.' + lClass + ', .ant-form-item-label label')];
          label = labels.find(l => l.innerText?.trim() === lText);
          if (label) {
            item = label.parentElement;
            for (let i = 0; i < 6; i++) {
              const cls = item.className?.toString() || '';
              if (cls.includes('formily-item') || cls.includes('form-item') || cls.includes('ant-form-item')) break;
              if (!item.parentElement) break;
              item = item.parentElement;
            }
          }
        }

        // 方式 B: 通过 placeholderText 找 select（当 label 不存在时）
        if (!label && pText) {
          // 找包含 placeholder 文本的 selector
          const selectors = [...document.querySelectorAll('.tbd-select-selector, .ant-select-selector')];
          for (const sel of selectors) {
            if (sel.innerText?.includes(pText)) {
              // 向上找 formily-item
              let parent = sel.parentElement;
              for (let i = 0; i < 6; i++) {
                const cls = parent.className?.toString() || '';
                if (cls.includes('formily-item') || cls.includes('form-item') || cls.includes('ant-form-item')) {
                  item = parent;
                  break;
                }
                if (!parent.parentElement) break;
                parent = parent.parentElement;
              }
              if (item) break;
            }
          }
        }

        if (!item) return { err: 'selector item not found: label=' + (lText || 'none') + ' placeholder=' + (pText || 'none') };

        // 找 selector（tbd-select-selector 或 ant-select-selector）
        const sel = item.querySelector('.tbd-select-selector, .ant-select-selector, select');
        if (!sel) return { err: 'selector not found in item', itemClass: item.className?.toString()?.slice(0,60) };

        // 优先不滚动（sticky header 里尔 3 已可见），若坐标为空再尝试 nearest
        let r = sel.getBoundingClientRect();
        if (!r.width) {
          sel.scrollIntoView({ block: 'nearest', behavior: 'instant' });
          r = sel.getBoundingClientRect();
        }
        if (!r.width) return { err: 'selector has zero width (off-screen?)' };
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height };
      }, labelText, placeholderText, labelClass);
`;

console.log("补丁内容已生成，请手动应用到 _node_bridge.js 第 232-262 行");
