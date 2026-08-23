// Visitor Pickup Page (访客独立取件客户端脚本)
let guestState = {
  mailbox: '',
  emails: [],
  selectedEmailId: null,
  latestCode: null,
  searchQuery: '',
  activeTab: 'html'
};

const GUEST_SERVICE_ICONS = {
  apple: '🍏',
  google: '🔍',
  telegram: '✈️',
  github: '🐙',
  microsoft: '🪟',
  openai: '🤖',
  chatgpt: '🤖',
  discord: '💬',
  amazon: '📦',
  twitter: '🐦',
  x: '🐦',
  paypal: '💳',
  steam: '🎮'
};

function getServiceIcon(serviceName) {
  if (!serviceName) return '⚡';
  const lower = serviceName.toLowerCase();
  for (const [k, icon] of Object.entries(GUEST_SERVICE_ICONS)) {
    if (lower.includes(k)) return icon;
  }
  return '⚡';
}

function parseMailboxFromUrl() {
  const path = window.location.pathname;
  // Match /mailboxes/xxx, /mail/xxx, /m/xxx or /api/v1/mailboxes/xxx
  const match = path.match(/\/(?:mailboxes|mail|m)\/([^/?#]+)/i);
  if (match && match[1]) {
    return decodeURIComponent(match[1].trim());
  }
  const urlParams = new URLSearchParams(window.location.search);
  const to = urlParams.get('to') || urlParams.get('email') || urlParams.get('mailbox');
  if (to) return decodeURIComponent(to.trim());

  return '';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr.replace(' ', 'T') + 'Z');
    if (isNaN(d.getTime())) return isoStr;
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
    return d.toLocaleDateString([], { month: '2-digit', day: '2-digit' }) + ' ' +
           d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (_) {
    return isoStr;
  }
}

function showToast(msg, duration = 2500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerText = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

// Init Page
document.addEventListener('DOMContentLoaded', () => {
  guestState.mailbox = parseMailboxFromUrl();
  const addrEl = document.getElementById('guest-mailbox-addr');
  if (addrEl) {
    addrEl.innerText = guestState.mailbox || '(未指定邮箱地址)';
  }
  document.title = `${guestState.mailbox || '访客取件'} | 邮件接收与取码`;

  setupEventListeners();
  if (guestState.mailbox) {
    setupGuestSSE();
    loadMailboxData();
  } else {
    showToast('未在链接中检测到有效的邮箱地址', 4000);
  }
});

function setupEventListeners() {
  // 1. Copy Mailbox Address
  const copyMailboxBtn = document.getElementById('btn-copy-mailbox');
  const pill = document.getElementById('guest-mailbox-pill');
  const doCopyMailbox = () => {
    if (guestState.mailbox) {
      navigator.clipboard.writeText(guestState.mailbox).then(() => {
        showToast(`已复制邮箱: ${guestState.mailbox}`);
      });
    }
  };
  if (copyMailboxBtn) copyMailboxBtn.addEventListener('click', (e) => { e.stopPropagation(); doCopyMailbox(); });
  if (pill) pill.addEventListener('click', doCopyMailbox);

  // 2. Manual Refresh
  const refreshBtn = document.getElementById('btn-guest-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      loadMailboxData();
      showToast('已刷新邮件列表');
    });
  }

  // 3. Hero Copy Button
  const heroCopyBtn = document.getElementById('btn-hero-copy');
  if (heroCopyBtn) {
    heroCopyBtn.addEventListener('click', () => {
      if (guestState.latestCode && guestState.latestCode.code) {
        navigator.clipboard.writeText(guestState.latestCode.code).then(() => {
          showToast(`✅ 已成功复制验证码: ${guestState.latestCode.code}`);
          heroCopyBtn.classList.add('btn-copy-success');
          setTimeout(() => heroCopyBtn.classList.remove('btn-copy-success'), 1200);
        });
      }
    });
  }

  // 4. Search input
  const searchInput = document.getElementById('guest-search-input');
  if (searchInput) {
    let timer;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        guestState.searchQuery = e.target.value.trim();
        filterAndRenderList();
      }, 250);
    });
  }

  // 5. Detail View Tabs
  document.querySelectorAll('.tab-btn[data-gtab]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn[data-gtab]').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panels .tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.getAttribute('data-gtab');
      guestState.activeTab = tab;
      const targetPanel = document.getElementById(`g-panel-${tab}`);
      if (targetPanel) targetPanel.classList.add('active');
    });
  });

  // 6. Download EML
  const downloadEmlBtn = document.getElementById('btn-g-download-eml');
  if (downloadEmlBtn) {
    downloadEmlBtn.addEventListener('click', () => {
      if (!guestState.selectedEmailId) return;
      window.open(`/api/v1/mailboxes/${encodeURIComponent(guestState.mailbox)}/emails/${guestState.selectedEmailId}/raw`, '_blank');
    });
  }
}

// Load Mailbox Emails & Latest Code
async function loadMailboxData() {
  if (!guestState.mailbox) return;
  try {
    const res = await fetch(`/api/v1/mailboxes/${encodeURIComponent(guestState.mailbox)}`, {
      headers: { 'Accept': 'application/json' }
    });
    const json = await res.json();
    if (json.success) {
      guestState.emails = json.data || [];
      guestState.latestCode = json.latest_code;
      
      const countEl = document.getElementById('guest-mail-count');
      if (countEl) countEl.innerText = json.total_emails || guestState.emails.length;

      updateHeroOtpBox(json.latest_code);
      filterAndRenderList();

      // Auto select first email if none selected
      if (guestState.emails.length > 0 && !guestState.selectedEmailId) {
        selectGuestEmail(guestState.emails[0].id);
      }
    }
  } catch (err) {
    console.error('Failed to load mailbox data:', err);
  }
}

// Update Top Hero Card with Latest OTP
function updateHeroOtpBox(codeRecord) {
  const heroCard = document.getElementById('guest-hero-card');
  const codeValEl = document.getElementById('hero-code-val');
  const serviceIconEl = document.getElementById('hero-service-icon');
  const serviceNameEl = document.getElementById('hero-service-name');
  const descEl = document.getElementById('hero-desc');
  const heroCopyBtn = document.getElementById('btn-hero-copy');
  const timeTipEl = document.getElementById('hero-time-tip');

  if (codeRecord && codeRecord.code) {
    if (codeValEl) {
      codeValEl.innerText = codeRecord.code;
      codeValEl.classList.add('has-code');
    }
    if (serviceIconEl) serviceIconEl.innerText = getServiceIcon(codeRecord.service_name);
    if (serviceNameEl) serviceNameEl.innerText = `${codeRecord.service_name || '验证码'} · 最新动态口令`;
    if (descEl) descEl.innerText = codeRecord.context_snippet || codeRecord.subject || '已成功提取验证信息';
    if (heroCopyBtn) {
      heroCopyBtn.disabled = false;
    }
    if (timeTipEl) {
      timeTipEl.innerText = `到达时间: ${formatTime(codeRecord.created_at)}`;
    }
    if (heroCard) heroCard.classList.add('active-code');
  } else {
    if (codeValEl) {
      codeValEl.innerText = '------';
      codeValEl.classList.remove('has-code');
    }
    if (serviceIconEl) serviceIconEl.innerText = '⚡';
    if (serviceNameEl) serviceNameEl.innerText = '等待新邮件中...';
    if (descEl) descEl.innerText = '该邮箱目前尚未收到验证码。新邮件到达时将自动秒级提取并高亮呈现！';
    if (heroCopyBtn) heroCopyBtn.disabled = true;
    if (timeTipEl) timeTipEl.innerText = '';
    if (heroCard) heroCard.classList.remove('active-code');
  }
}

// Render Email List Cards
function filterAndRenderList() {
  const container = document.getElementById('guest-cards-list');
  if (!container) return;

  let items = guestState.emails || [];
  if (guestState.searchQuery) {
    const q = guestState.searchQuery.toLowerCase();
    items = items.filter(e => 
      (e.subject && e.subject.toLowerCase().includes(q)) ||
      (e.from_address && e.from_address.toLowerCase().includes(q)) ||
      (e.body_text && e.body_text.toLowerCase().includes(q))
    );
  }

  if (items.length === 0) {
    container.innerHTML = '<div class="empty-hint">暂无邮件记录</div>';
    return;
  }

  container.innerHTML = items.map(item => {
    const isSelected = guestState.selectedEmailId === item.id;
    const otpChip = item.latest_code ? `
      <div class="card-otp-chip" data-copy="${escapeHtml(item.latest_code)}" title="点击复制验证码">
        <span class="service-pill">${escapeHtml(item.service_name || 'OTP')}</span>
        <span>${escapeHtml(item.latest_code)}</span>
      </div>
    ` : '';

    return `
      <div class="mail-card ${isSelected ? 'active' : ''}" data-id="${item.id}">
        <div class="card-top">
          <span class="card-sender" title="${escapeHtml(item.from_address)}">${escapeHtml(item.from_address)}</span>
          <span class="card-time">${formatTime(item.created_at)}</span>
        </div>
        <div class="card-subject">${escapeHtml(item.subject || '(无主题)')}</div>
        ${otpChip}
      </div>
    `;
  }).join('');

  // 1. Copy chip click
  container.querySelectorAll('.card-otp-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      const code = chip.getAttribute('data-copy');
      if (code) {
        navigator.clipboard.writeText(code).then(() => {
          showToast(`已复制验证码: ${code}`);
        });
      }
    });
  });

  // 2. Select card
  container.querySelectorAll('.mail-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = parseInt(card.getAttribute('data-id'));
      selectGuestEmail(id);
    });
  });
}

const guestEmailDetailCache = new Map();

// Select Single Email with 0ms Instant Preview & Local Caching
async function selectGuestEmail(id) {
  guestState.selectedEmailId = id;
  
  // 1. Update active card highlight directly
  const container = document.getElementById('guest-cards-list');
  if (container) {
    container.querySelectorAll('.mail-card').forEach(c => {
      if (parseInt(c.getAttribute('data-id')) === id) {
        c.classList.add('active');
      } else {
        c.classList.remove('active');
      }
    });
  }

  const emptyState = document.getElementById('guest-empty-state');
  const detailContent = document.getElementById('guest-detail-content');
  if (emptyState) emptyState.style.display = 'none';
  if (detailContent) detailContent.style.display = 'flex';

  // 2. Instant Optimistic Render from summary
  const summaryItem = (guestState.emails || []).find(e => e.id === id);
  if (summaryItem) {
    renderGuestEmailDetailPreview(summaryItem);
  }

  // 3. Check memory cache for instant full rendering
  if (guestEmailDetailCache.has(id)) {
    renderGuestEmailDetail(guestEmailDetailCache.get(id));
    return;
  }

  // 4. Fetch full details asynchronously
  try {
    const res = await fetch(`/api/v1/mailboxes/${encodeURIComponent(guestState.mailbox)}/emails/${id}`);
    const json = await res.json();
    if (json.success) {
      guestEmailDetailCache.set(id, json.data);
      if (guestState.selectedEmailId === id) {
        renderGuestEmailDetail(json.data);
      }
    }
  } catch (err) {
    showToast('加载邮件详情失败: ' + err.message);
  }
}

// Instant 0ms Preview Render for Guest Page
function renderGuestEmailDetailPreview(email) {
  const subjEl = document.getElementById('g-detail-subject');
  const fromEl = document.getElementById('g-detail-from');
  const toEl = document.getElementById('g-detail-to');
  const timeEl = document.getElementById('g-detail-time');

  if (subjEl) subjEl.innerText = email.subject || '(无主题)';
  if (fromEl) fromEl.innerText = email.from_address;
  if (toEl) toEl.innerText = email.to_address;
  if (timeEl) timeEl.innerText = formatTime(email.created_at);

  const otpBanner = document.getElementById('g-otp-banner');
  if (email.latest_code) {
    if (otpBanner) otpBanner.style.display = 'flex';
    const tagEl = document.getElementById('g-otp-tag');
    const valEl = document.getElementById('g-otp-val');
    const snipEl = document.getElementById('g-otp-snippet');
    const copyBtn = document.getElementById('btn-g-copy-inline');

    if (tagEl) tagEl.innerText = email.service_name || 'OTP';
    if (valEl) valEl.innerText = email.latest_code;
    if (snipEl) snipEl.innerText = '已识别到验证码';
    if (copyBtn) {
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(email.latest_code).then(() => {
          showToast(`已复制: ${email.latest_code}`);
        });
      };
    }
  } else {
    if (otpBanner) otpBanner.style.display = 'none';
  }

  const textEl = document.getElementById('g-text-preview-content');
  if (textEl && email.body_text) textEl.innerText = email.body_text;
}

function renderGuestEmailDetail(email) {
  const subjEl = document.getElementById('g-detail-subject');
  const fromEl = document.getElementById('g-detail-from');
  const toEl = document.getElementById('g-detail-to');
  const timeEl = document.getElementById('g-detail-time');

  if (subjEl) subjEl.innerText = email.subject || '(无主题)';
  if (fromEl) fromEl.innerText = email.from_address;
  if (toEl) toEl.innerText = email.to_address;
  if (timeEl) timeEl.innerText = formatTime(email.created_at);

  // Inline OTP Banner
  const otpBanner = document.getElementById('g-otp-banner');
  const codes = email.codes || [];
  if (codes.length > 0) {
    const codeObj = codes[0];
    if (otpBanner) otpBanner.style.display = 'flex';
    const tagEl = document.getElementById('g-otp-tag');
    const valEl = document.getElementById('g-otp-val');
    const snipEl = document.getElementById('g-otp-snippet');
    const copyBtn = document.getElementById('btn-g-copy-inline');

    if (tagEl) tagEl.innerText = codeObj.service_name || 'OTP';
    if (valEl) valEl.innerText = codeObj.code;
    if (snipEl) snipEl.innerText = codeObj.context_snippet || '已识别到验证码';
    if (copyBtn) {
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(codeObj.code).then(() => {
          showToast(`已复制验证码: ${codeObj.code}`);
        });
      };
    }
  } else {
    if (otpBanner) otpBanner.style.display = 'none';
  }

  // HTML Preview Frame
  const iframe = document.getElementById('g-html-iframe');
  if (iframe) {
    if (email.body_html) {
      iframe.srcdoc = email.body_html;
    } else {
      iframe.srcdoc = `<pre style="font-family: sans-serif; padding: 20px; white-space: pre-wrap;">${escapeHtml(email.body_text)}</pre>`;
    }
  }

  // Plain Text Preview
  const textEl = document.getElementById('g-text-preview');
  if (textEl) textEl.innerText = email.body_text || '(无纯文本正文)';

  // Raw Preview
  const rawEl = document.getElementById('g-raw-preview');
  if (rawEl) rawEl.innerText = email.raw_eml || '(未保存 Raw 报文)';

  // OTP Table
  const otpContainer = document.getElementById('g-otp-container');
  if (otpContainer) {
    if (codes.length > 0) {
      otpContainer.innerHTML = codes.map(c => `
        <div class="otp-card-item">
          <div>
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">${escapeHtml(c.service_name || '服务商')} · ${c.code_type}</div>
            <div class="otp-code-big">${escapeHtml(c.code)}</div>
            ${c.verification_url ? `<div style="margin-top: 4px;"><a href="${escapeHtml(c.verification_url)}" target="_blank" class="btn btn-outline btn-sm">打开验证链接 ↗</a></div>` : ''}
          </div>
          <button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText('${escapeHtml(c.code)}').then(()=>showToast('已复制: ${escapeHtml(c.code)}'))">
            一键复制
          </button>
        </div>
      `).join('');
    } else {
      otpContainer.innerHTML = '<div class="empty-hint">此邮件未检测到验证码或激活链接</div>';
    }
  }
}

// Setup Dedicated SSE Stream for this Mailbox
function setupGuestSSE() {
  if (!guestState.mailbox) return;
  const badge = document.getElementById('guest-sse-badge');
  const streamUrl = `/api/v1/mailboxes/${encodeURIComponent(guestState.mailbox)}/stream`;
  const sse = new EventSource(streamUrl);

  sse.onopen = () => {
    if (badge) {
      badge.innerHTML = '<span class="live-dot pulse"></span><span class="live-text">实时监听中</span>';
      badge.classList.remove('disconnected');
    }
  };

  sse.addEventListener('new_email', (e) => {
    try {
      const data = JSON.parse(e.data);
      showToast(`📬 收到来自 ${data.from_address} 的新邮件！`, 4000);
      loadMailboxData();
    } catch (_) {
      loadMailboxData();
    }
  });

  sse.onerror = () => {
    if (badge) {
      badge.innerHTML = '<span class="live-dot" style="background-color: #f59e0b;"></span><span class="live-text">连接重试中</span>';
      badge.classList.add('disconnected');
    }
  };
}
