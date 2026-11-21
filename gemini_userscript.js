// ==UserScript==
// @name         AI Usage Monitor – Gemini
// @namespace    ai-usage-monitor
// @version      0.4
// @description  Lấy % hạn mức Gemini (5 giờ + tuần) và tên gói, gửi về server Python cục bộ
// @match        https://gemini.google.com/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        unsafeWindow
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  'use strict';
  const SERVER = 'http://127.0.0.1:8765/gemini';
  const SECRET = 'DAN-KHOA-BI-MAT-CUA-BAN-VAO-DAY'; // phải GIỐNG HỆT trong gemini_receiver.py
  const REFRESH_MIN = 30; // dữ liệu cũ hơn bao nhiêu phút thì gọi lại
  const LOCK_MIN = 5;     // sau 1 lần thử thất bại, chờ bao nhiêu phút mới thử tiếp
  const IS_TOP = window.top === window;

  console.log('[usage-monitor] v0.4 đã nạp trên', location.pathname, IS_TOP ? '(cửa sổ chính)' : '(iframe)');

  const page = unsafeWindow;
  const originalFetch = page.fetch;
  const minutesSince = (t) => (Date.now() - t) / 60000;

  // ---------- Đọc JSON: getUsageInfo.subscriptionTier + pools[{poolType, percentageUsed, gxu.windowRefreshesAt}] ----------
  function parseUsage(text) {
    const json = JSON.parse(text.replace(/^\)\]\}'\s*/, '')); // bỏ tiền tố chống XSSI nếu có
    const out = { tier: null, windows: [] };
    (function walk(node) {
      if (!node || typeof node !== 'object') return;
      if (typeof node.subscriptionTier === 'string') out.tier = node.subscriptionTier;
      if (typeof node.percentageUsed === 'number') {
        out.windows.push({
          poolType: node.poolType ?? null,
          percentageUsed: node.percentageUsed,
          windowRefreshesAt: node.gxu?.windowRefreshesAt ?? node.windowRefreshesAt ?? null,
        });
      }
      for (const v of Object.values(node)) walk(v);
    })(json);
    return out;
  }

  // ---------- Gửi CHỈ tên gói + các con số về server Python ----------
  function report(usage) {
    GM_xmlhttpRequest({
      method: 'POST',
      url: SERVER,
      headers: { 'Content-Type': 'application/json', 'X-Monitor-Key': SECRET },
      data: JSON.stringify(usage),
      onload: (r) => {
        console.log('[usage-monitor] server trả lời:', r.status, r.responseText);
        if (r.status === 200) GM_setValue('lastReport', Date.now());
      },
      onerror: () => console.warn('[usage-monitor] không gửi được – server Python đã chạy chưa?'),
    });
  }

  // ---------- GHI LẠI mẫu request (chỉ khi chắc chắn là truy vấn usage) ----------
  function saveTemplate(args) {
    try {
      const init = args[1] || {};
      const body = init.body;
      const bodyType = Object.prototype.toString.call(body);
      if (body != null && typeof body !== 'string' && bodyType !== '[object URLSearchParams]') {
        console.warn('[usage-monitor] body kiểu', bodyType, 'chưa hỗ trợ – không lưu mẫu');
        return;
      }
      const tpl = {
        url: String(args[0]?.url ?? args[0]),
        method: init.method || 'GET',
        headers: Object.fromEntries(new Headers(init.headers || {})),
        body: body == null ? null : String(body),
        savedAt: Date.now(),
      };
      GM_setValue('usageRequest', tpl);
      console.log('[usage-monitor] đã lưu mẫu request:', tpl.method, tpl.url.slice(0, 90));
    } catch (e) {
      console.warn('[usage-monitor] không lưu được mẫu', e);
    }
  }

  // ---------- Bọc fetch của trang (bắt dữ liệu + ghi mẫu) ----------
  page.fetch = async function (...args) {
    let isUsage = false;
    let responded = false;
    const originalArgs = args;
    try {
      isUsage = String(args[0]?.url ?? args[0]).includes('executeQuery');
      // Relay "giật dây huỷ" ngay khi đọc xong -> thay bằng dây của ta
      const pageSignal = args[1]?.signal;
      if (isUsage && pageSignal) {
        const ours = new AbortController();
        if (pageSignal.aborted) ours.abort(pageSignal.reason);
        pageSignal.addEventListener('abort', () => { if (!responded) ours.abort(pageSignal.reason); });
        args = [args[0], { ...args[1], signal: ours.signal }];
      }
    } catch (e) { /* tuyệt đối không làm hỏng trang */ }

    const resp = await originalFetch.apply(this, args);
    responded = true;

    if (isUsage) {
      resp.clone().text().then((text) => {
        const usage = parseUsage(text);
        if (!usage.windows.length) return; // executeQuery của truy vấn khác -> bỏ qua
        console.log('[usage-monitor] bắt được', usage.windows.length, 'cửa sổ | gói', usage.tier, usage.windows);
        saveTemplate(originalArgs);
        report(usage);
      }).catch((e) => console.warn('[usage-monitor] lỗi đọc response', e));
    }
    return resp;
  };

  // ---------- PHÁT LẠI định kỳ (chỉ cửa sổ chính) ----------
  if (!IS_TOP) return; // trong iframe thì chỉ bắt dữ liệu

  async function refreshByReplay() {
    const age = minutesSince(GM_getValue('lastReport', 0));
    if (age < REFRESH_MIN) {
      console.log(`[usage-monitor] dữ liệu còn mới (${age.toFixed(1)}/${REFRESH_MIN} phút) – bỏ qua`);
      return;
    }
    const lockLeft = (GM_getValue('replayLock', 0) - Date.now()) / 60000;
    if (lockLeft > 0) {
      console.log(`[usage-monitor] đang khoá thêm ${lockLeft.toFixed(1)} phút (tab khác vừa thử) – bỏ qua`);
      return;
    }
    const tpl = GM_getValue('usageRequest', null);
    if (!tpl) {
      console.log('[usage-monitor] chưa có mẫu request – hãy mở Settings → Hạn mức sử dụng 1 lần');
      return;
    }
    GM_setValue('replayLock', Date.now() + LOCK_MIN * 60000); // khoá trong lúc đang thử
    console.log(`[usage-monitor] dữ liệu cũ ${age.toFixed(1)} phút -> phát lại executeQuery (mẫu lưu ${Math.round(minutesSince(tpl.savedAt))} phút trước)`);
    try {
      const resp = await originalFetch.call(page, tpl.url, {
        method: tpl.method,
        headers: tpl.headers,
        body: tpl.body ?? undefined,
        credentials: 'include',
      });
      const usage = parseUsage(await resp.text());
      console.log('[usage-monitor] phát lại: HTTP', resp.status, '| tìm thấy', usage.windows.length, 'cửa sổ | gói', usage.tier);
      if (usage.windows.length) {
        report(usage);
        GM_setValue('replayLock', 0); // thành công -> mở khoá ngay
      } else {
        console.warn('[usage-monitor] mẫu có thể đã hết hạn – mở lại trang Hạn mức để làm mới mẫu');
      }
    } catch (e) {
      console.warn('[usage-monitor] lỗi khi phát lại', e); // thất bại -> giữ khoá LOCK_MIN phút
    }
  }

  window.addEventListener('load', () => {
    setTimeout(refreshByReplay, 10000);      // 10 giây sau khi tải trang
    setInterval(refreshByReplay, 5 * 60000); // rồi cứ 5 phút kiểm tra 1 lần
  });
})();
