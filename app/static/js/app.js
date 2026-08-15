// MailCapture & OTP Hub Client Logic
let state = {
  currentFilter: 'all', // 'all', 'unread', 'codes'
  selectedAlias: null,
  searchQuery: '',
  emails: [],
  selectedEmailId: null,
  stats: null,
  activeTab: 'html',
  activeCodeLang: 'python-api',
  apiKey: localStorage.getItem('mc_api_key') || ''
};

// Presets for Test Mail Injection
const PRESETS = {
  apple: {
    from: "appleid@id.apple.com",
    to: "my_icloud@domain.com",
    subject: "您的 Apple ID 验证码是 948210",
    body: "您好，您的 Apple ID 验证码是 948210。请在 10 分钟内输入此代码以完成双重认证登录。请勿与任何人共享此代码。"
  },
  github: {
    from: "noreply@github.com",
    to: "developer@domain.com",
    subject: "GitHub device verification code",
    body: "Please enter the following verification code to sign in to your GitHub account: 519283\nThis code will expire in 10 minutes."
  },
  telegram: {
    from: "login@telegram.org",
    to: "telegram_user@domain.com",
    subject: "Telegram login code: 62819",
    body: "Dear user, here is your Telegram login code: 62819\nDo not give this code to anyone, even if they say they're from Telegram!"
  },
  google: {
    from: "no-reply@accounts.google.com",
    to: "google_alias@domain.com",
    subject: "Google 账号验证码",
    body: "G-749102 是您的 Google 验证码。请使用此代码验证您的身份。"
  }
};

// Safe event binding helper (Prevents any single missing element from crashing the script)
function bindClick(id, handler) {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener('click', handler);
  }
}

function bindEvent(id, eventType, handler) {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener(eventType, handler);
  }
}

// DOM Elements
const mailCardsList = document.getElementById('mail-cards-list');
const emptyDetailState = document.getElementById('empty-detail-state');
const detailContent = document.getElementById('detail-content');
const searchInput = document.getElementById('search-input');
const sseStatus = document.getElementById('sse-status');

// Secure Fetch Wrapper
async function apiFetch(url, options = {}) {
  options.headers = options.headers || {};
  if (state.apiKey) {
    options.headers['X-API-Key'] = state.apiKey;
  }
  return fetch(url, options);
}

// Init App
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  setupSSE();
  fetchStats();
  fetchEmails();
  updateCodeSnippets();
  updateWizardContent();
});

// Setup Event Listeners
function setupEventListeners() {
  // Filter tabs
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      state.currentFilter = item.getAttribute('data-filter');
      state.selectedAlias = null;
      document.querySelectorAll('.inbox-alias-item').forEach(a => a.classList.remove('active'));
      fetchEmails();
    });
  });

  // Search
  if (searchInput) {
    let searchTimer;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.searchQuery = e.target.value.trim();
        fetchEmails();
      }, 300);
    });
  }

  // Refresh
  bindClick('btn-refresh-list', () => {
    fetchStats();
    fetchEmails();
    showToast('已刷新邮件列表');
  });

  // Clear all
  bindClick('btn-clear-all', async () => {
    if (!confirm('确定要清空所有邮件和验证码吗？此操作不可恢复。')) return;
    try {
      const res = await apiFetch('/api/v1/emails', { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showToast(`已清空 ${data.deleted_count} 封邮件`);
        state.selectedEmailId = null;
        renderDetailEmpty();
        fetchStats();
        fetchEmails();
      }
    } catch (e) {
      showToast('清空失败: ' + e.message);
    }
  });

  // Detail View Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      state.activeTab = tabId;
      const targetPanel = document.getElementById(`panel-${tabId}`);
      if (targetPanel) targetPanel.classList.add('active');
    });
  });

  // Delete current email
  bindClick('btn-delete-current', async () => {
    if (!state.selectedEmailId) return;
    try {
      const res = await apiFetch(`/api/v1/emails/${state.selectedEmailId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.success) {
        showToast('邮件已删除');
        state.selectedEmailId = null;
        renderDetailEmpty();
        fetchStats();
        fetchEmails();
      }
    } catch (e) {
      showToast('删除失败: ' + e.message);
    }
  });

  // Download EML
  bindClick('btn-download-eml', () => {
    if (!state.selectedEmailId) return;
    window.open(`/api/v1/emails/${state.selectedEmailId}/raw`, '_blank');
  });

  // Modals management
  setupModals();
}

function setupModals() {
  const guideModal = document.getElementById('modal-guide');
  const apiModal = document.getElementById('modal-api');
  const settingsModal = document.getElementById('modal-settings');
  const testModal = document.getElementById('modal-test');
  const wizardModal = document.getElementById('modal-domain-wizard');

  // Domain Wizard
  bindClick('btn-domain-wizard', () => {
    if (wizardModal) wizardModal.style.display = 'flex';
    updateWizardContent();
  });
  bindClick('btn-close-wizard', () => {
    if (wizardModal) wizardModal.style.display = 'none';
  });
  bindClick('btn-close-wizard-footer', () => {
    if (wizardModal) wizardModal.style.display = 'none';
  });
  bindClick('btn-gen-wizard', updateWizardContent);
  bindEvent('wizard-domain-input', 'input', updateWizardContent);

  bindClick('btn-copy-worker', () => {
    const codeEl = document.getElementById('wizard-cf-worker-code');
    if (codeEl) {
      navigator.clipboard.writeText(codeEl.innerText).then(() => showToast('Cloudflare Worker 脚本已复制'));
    }
  });

  // Guide Modal
  bindClick('btn-guide-modal', () => {
    if (guideModal) guideModal.style.display = 'flex';
  });
  bindClick('btn-close-guide', () => {
    if (guideModal) guideModal.style.display = 'none';
  });
  bindClick('btn-guide-ok', () => {
    if (guideModal) guideModal.style.display = 'none';
  });

  // API Snippets Modal
  bindClick('btn-api-modal', () => {
    if (apiModal) apiModal.style.display = 'flex';
    updateCodeSnippets();
  });
  bindClick('btn-close-api', () => {
    if (apiModal) apiModal.style.display = 'none';
  });
  bindClick('btn-close-api-footer', () => {
    if (apiModal) apiModal.style.display = 'none';
  });

  // Settings Modal
  bindClick('btn-settings-modal', async () => {
    if (settingsModal) settingsModal.style.display = 'flex';
    await loadSettingsData();
  });
  bindClick('btn-close-settings', () => {
    if (settingsModal) settingsModal.style.display = 'none';
  });
  bindClick('btn-cancel-settings', () => {
    if (settingsModal) settingsModal.style.display = 'none';
  });
  bindClick('btn-save-settings', async (e) => {
    e.preventDefault();
    await saveSettingsData();
    if (settingsModal) settingsModal.style.display = 'none';
  });

  // Test Email Injector Modal
  bindClick('btn-test-modal', () => {
    if (testModal) testModal.style.display = 'flex';
  });
  bindClick('btn-close-test', () => {
    if (testModal) testModal.style.display = 'none';
  });
  bindClick('btn-cancel-test', () => {
    if (testModal) testModal.style.display = 'none';
  });

  // Preset buttons
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const presetKey = btn.getAttribute('data-preset');
      const p = PRESETS[presetKey];
      if (p) {
        const fromEl = document.getElementById('test-from');
        const toEl = document.getElementById('test-to');
        const subjEl = document.getElementById('test-subject');
        const bodyEl = document.getElementById('test-body');
        if (fromEl) fromEl.value = p.from;
        if (toEl) toEl.value = p.to;
        if (subjEl) subjEl.value = p.subject;
        if (bodyEl) bodyEl.value = p.body;
      }
    });
  });

  // Send Test Mail
  bindClick('btn-send-test', async () => {
    const fromEl = document.getElementById('test-from');
    const toEl = document.getElementById('test-to');
    const subjEl = document.getElementById('test-subject');
    const bodyEl = document.getElementById('test-body');

    const fromAddr = fromEl ? fromEl.value.trim() : 'service@apple.com';
    const toAddr = toEl ? toEl.value.trim() : 'my_user@mydomain.com';
    const subject = subjEl ? subjEl.value.trim() : 'Test Subject';
    const body = bodyEl ? bodyEl.value.trim() : 'Test Body';

    try {
      const res = await apiFetch('/api/v1/config/test-inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_address: fromAddr,
          to_address: toAddr,
          subject: subject,
          body_text: body
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast('✅ 测试邮件已成功注入并完成解析！');
        if (testModal) testModal.style.display = 'none';
        fetchStats();
        fetchEmails();
        if (data.result && data.result.email_id) {
          selectEmail(data.result.email_id);
        }
      }
    } catch (e) {
      showToast('注入失败: ' + e.message);
    }
  });

  // Generator input & tabs
  bindEvent('gen-email-input', 'input', updateCodeSnippets);
  document.querySelectorAll('.code-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.activeCodeLang = tab.getAttribute('data-lang');
      updateCodeSnippets();
    });
  });

  // Copy code snippet
  bindClick('btn-copy-snippet', () => {
    const codeEl = document.getElementById('code-snippet-box');
    if (codeEl) {
      navigator.clipboard.writeText(codeEl.innerText).then(() => {
        showToast('示例代码已复制到剪贴板');
      });
    }
  });
}

function updateWizardContent() {
  const domainInput = document.getElementById('wizard-domain-input');
  const domain = (domainInput ? domainInput.value.trim() : '') || 'mydomain.com';
  const apiHost = window.location.origin || 'http://YOUR_SERVER_IP:8000';

  // 1. Generate example Apple ID emails
  const chipsContainer = document.getElementById('wizard-email-chips');
  if (chipsContainer) {
    const examples = [
      `apple@${domain}`,
      `id01@${domain}`,
      `user_apple@${domain}`,
      `vip@${domain}`,
      `anything@${domain}`
    ];
    chipsContainer.innerHTML = examples.map(e => `
      <span class="email-chip" title="点击复制" onclick="navigator.clipboard.writeText('${e}').then(()=>showToast('已复制: ${e}'))">
        <span>✉️ ${e}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
      </span>
    `).join('');
  }

  // 2. Generate Cloudflare Worker Code
  const cfCodeEl = document.getElementById('wizard-cf-worker-code');
  if (cfCodeEl) {
    const cfCode = `export default {
  async email(message, env, ctx) {
    // 1. 读取接收到的原始邮件内容
    const rawEmail = await new Response(message.raw).text();
    
    // 2. 发送给您的邮件接收平台 Webhook
    const targetUrl = "${apiHost}/api/v1/webhook/inbound";
    
    await fetch(targetUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        raw: rawEmail,
        to: message.to,
        from: message.from
      })
    });
  }
};`;
    cfCodeEl.innerText = cfCode;
  }

  // 3. Update MX record hints
  const mxValEl = document.getElementById('wizard-mx-val');
  if (mxValEl) {
    mxValEl.innerText = `mail.${domain} (指向您的服务器IP)`;
  }
}

// Settings API Handlers
async function loadSettingsData() {
  try {
    const res = await apiFetch('/api/v1/config');
    const json = await res.json();
    if (json.success) {
      const cfg = json.data;
      const keyEl = document.getElementById('cfg-api-key');
      const passEl = document.getElementById('cfg-imap-pass');
      const kwEl = document.getElementById('cfg-otp-keywords');
      const statApi = document.getElementById('stat-api-port');
      const statSmtp = document.getElementById('stat-smtp-port');
      const statImap = document.getElementById('stat-imap-port');

      if (keyEl) keyEl.value = cfg.server.api_key || '';
      if (passEl) passEl.value = cfg.imap.auth_password || '';
      if (kwEl) kwEl.value = (cfg.otp.keywords || []).join(', ');
      
      if (statApi) statApi.innerText = cfg.server.port;
      if (statSmtp) statSmtp.innerText = cfg.smtp.port;
      if (statImap) statImap.innerText = cfg.imap.port;
    }
  } catch (e) {
    showToast('加载配置失败: ' + e.message);
  }
}

async function saveSettingsData() {
  const keyEl = document.getElementById('cfg-api-key');
  const passEl = document.getElementById('cfg-imap-pass');
  const kwEl = document.getElementById('cfg-otp-keywords');

  const apiKey = keyEl ? keyEl.value.trim() : '';
  const imapPass = passEl ? passEl.value.trim() : 'password123';
  const rawKeywords = kwEl ? kwEl.value : '';
  const keywordsList = rawKeywords.split(/[,，\n]/).map(k => k.trim()).filter(Boolean);

  try {
    const res = await apiFetch('/api/v1/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: apiKey,
        imap_password: imapPass,
        otp_keywords: keywordsList
      })
    });
    const json = await res.json();
    if (json.success) {
      state.apiKey = apiKey;
      localStorage.setItem('mc_api_key', apiKey);
      showToast('✅ 系统配置已保存并实时生效');
    }
  } catch (e) {
    showToast('保存失败: ' + e.message);
  }
}

// Setup Server-Sent Events (SSE)
function setupSSE() {
  const evtSource = new EventSource('/api/v1/stream');

  evtSource.onopen = () => {
    if (sseStatus) {
      sseStatus.classList.remove('disconnected');
      const label = sseStatus.querySelector('.status-label');
      if (label) label.innerText = '实时流已连接';
    }
  };

  evtSource.addEventListener('email_event', (e) => {
    try {
      const payload = JSON.parse(e.data);
      if (payload.event === 'new_email') {
        handleIncomingEmail(payload.data);
      }
    } catch (err) {
      console.error('SSE Error:', err);
    }
  });

  evtSource.onerror = () => {
    if (sseStatus) {
      sseStatus.classList.add('disconnected');
      const label = sseStatus.querySelector('.status-label');
      if (label) label.innerText = '连接断开，重连中...';
    }
  };
}

function handleIncomingEmail(data) {
  showToast(`📥 收到新邮件: ${data.subject || '无主题'}`);
  fetchStats();
  fetchEmails();
  if (!state.selectedEmailId) {
    selectEmail(data.id);
  }
}

// Fetch Stats
async function fetchStats() {
  try {
    const res = await apiFetch('/api/v1/stats');
    const json = await res.json();
    if (json.success) {
      state.stats = json.data;
      renderStats(json.data);
    }
  } catch (e) {
    console.error('Failed to fetch stats:', e);
  }
}

function renderStats(stats) {
  const totalEl = document.getElementById('count-total');
  const unreadEl = document.getElementById('count-unread');
  const codesEl = document.getElementById('count-codes');
  const uniqueEl = document.getElementById('unique-inboxes-count');

  if (totalEl) totalEl.innerText = stats.total_emails || 0;
  if (unreadEl) unreadEl.innerText = stats.unread_emails || 0;
  if (codesEl) codesEl.innerText = stats.total_codes || 0;
  if (uniqueEl) uniqueEl.innerText = stats.unique_inboxes || 0;

  if (stats.config) {
    const chipApi = document.getElementById('chip-api-port');
    const chipSmtp = document.getElementById('chip-smtp-port');
    const chipImap = document.getElementById('chip-imap-port');
    if (chipApi) chipApi.innerText = stats.config.api_port || '8000';
    if (chipSmtp) chipSmtp.innerText = stats.config.smtp_port || '2525';
    if (chipImap) chipImap.innerText = stats.config.imap_port || '1143';
  }

  // Render top inboxes list in sidebar
  const inboxesList = document.getElementById('inbox-aliases-list');
  if (inboxesList) {
    if (stats.top_inboxes && stats.top_inboxes.length > 0) {
      inboxesList.innerHTML = stats.top_inboxes.map(item => `
        <div class="inbox-alias-item ${state.selectedAlias === item.to_address ? 'active' : ''}" data-addr="${escapeHtml(item.to_address)}">
          <span style="overflow: hidden; text-overflow: ellipsis;">${escapeHtml(item.to_address)}</span>
          <span class="badge-sm">${item.count}</span>
        </div>
      `).join('');

      inboxesList.querySelectorAll('.inbox-alias-item').forEach(el => {
        el.addEventListener('click', () => {
          const addr = el.getAttribute('data-addr');
          if (state.selectedAlias === addr) {
            state.selectedAlias = null;
            el.classList.remove('active');
          } else {
            document.querySelectorAll('.inbox-alias-item').forEach(i => i.classList.remove('active'));
            el.classList.add('active');
            state.selectedAlias = addr;
          }
          fetchEmails();
        });
      });
    } else {
      inboxesList.innerHTML = '<div class="empty-hint">暂无活跃别名</div>';
    }
  }
}

// Fetch Emails
async function fetchEmails() {
  let url = '/api/v1/emails?page=1&page_size=50';
  if (state.selectedAlias) {
    url += `&to=${encodeURIComponent(state.selectedAlias)}`;
  }
  if (state.searchQuery) {
    url += `&search=${encodeURIComponent(state.searchQuery)}`;
  }
  if (state.currentFilter === 'unread') {
    url += `&is_read=false`;
  }

  try {
    const res = await apiFetch(url);
    const json = await res.json();
    if (json.success) {
      let items = json.data || [];
      if (state.currentFilter === 'codes') {
        items = items.filter(e => !!e.latest_code);
      }
      state.emails = items;
      renderEmailList(items);
    }
  } catch (e) {
    if (mailCardsList) mailCardsList.innerHTML = `<div class="empty-hint">加载失败: ${e.message}</div>`;
  }
}

function renderEmailList(items) {
  if (!mailCardsList) return;
  if (!items || items.length === 0) {
    mailCardsList.innerHTML = '<div class="empty-hint">暂无邮件记录</div>';
    return;
  }

  mailCardsList.innerHTML = items.map(item => {
    const isSelected = state.selectedEmailId === item.id;
    const isUnread = !item.is_read;
    const otpChip = item.latest_code ? `
      <div class="card-otp-chip">
        <span class="service-pill">${escapeHtml(item.service_name || 'OTP')}</span>
        <span>${escapeHtml(item.latest_code)}</span>
      </div>
    ` : '';

    return `
      <div class="mail-card ${isSelected ? 'active' : ''} ${isUnread ? 'unread' : ''}" data-id="${item.id}">
        <div class="card-top">
          <span class="card-sender" title="${escapeHtml(item.from_address)}">${escapeHtml(item.from_address)}</span>
          <span class="card-time">${formatTime(item.created_at)}</span>
        </div>
        <div class="card-to">To: ${escapeHtml(item.to_address)}</div>
        <div class="card-subject">${escapeHtml(item.subject || '(无主题)')}</div>
        ${otpChip}
      </div>
    `;
  }).join('');

  mailCardsList.querySelectorAll('.mail-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = parseInt(card.getAttribute('data-id'));
      selectEmail(id);
    });
  });
}

// Select Single Email
async function selectEmail(id) {
  state.selectedEmailId = id;
  renderEmailList(state.emails);

  try {
    const res = await apiFetch(`/api/v1/emails/${id}`);
    const json = await res.json();
    if (json.success) {
      renderEmailDetail(json.data);
      fetchStats();
    }
  } catch (e) {
    showToast('获取邮件详情失败: ' + e.message);
  }
}

function renderEmailDetail(email) {
  if (emptyDetailState) emptyDetailState.style.display = 'none';
  if (detailContent) detailContent.style.display = 'flex';

  const subjEl = document.getElementById('detail-subject');
  const fromEl = document.getElementById('detail-from');
  const toEl = document.getElementById('detail-to');
  const timeEl = document.getElementById('detail-time');

  if (subjEl) subjEl.innerText = email.subject || '(无主题)';
  if (fromEl) fromEl.innerText = email.from_address;
  if (toEl) toEl.innerText = email.to_address;
  if (timeEl) timeEl.innerText = email.created_at;

  // OTP Highlight Banner
  const otpBanner = document.getElementById('otp-highlight-banner');
  const codes = email.codes || [];
  if (codes.length > 0) {
    const primaryCode = codes[0];
    if (otpBanner) otpBanner.style.display = 'flex';
    const tagEl = document.getElementById('otp-service-tag');
    const valEl = document.getElementById('otp-highlight-value');
    const snipEl = document.getElementById('otp-snippet');
    const copyBtn = document.getElementById('btn-oneclick-copy');

    if (tagEl) tagEl.innerText = primaryCode.service_name || 'OTP';
    if (valEl) valEl.innerText = primaryCode.code;
    if (snipEl) snipEl.innerText = primaryCode.context_snippet || '已识别到验证信息';

    if (copyBtn) {
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(primaryCode.code).then(() => {
          showToast(`已复制验证码: ${primaryCode.code}`);
        });
      };
    }
  } else {
    if (otpBanner) otpBanner.style.display = 'none';
  }

  // HTML tab iframe preview
  const iframe = document.getElementById('html-iframe');
  if (iframe) {
    if (email.body_html) {
      iframe.srcdoc = email.body_html;
    } else {
      iframe.srcdoc = `<pre style="font-family: sans-serif; padding: 20px; white-space: pre-wrap;">${escapeHtml(email.body_text)}</pre>`;
    }
  }

  // Plain Text tab
  const textEl = document.getElementById('text-preview-content');
  if (textEl) textEl.innerText = email.body_text || '(无纯文本正文)';

  // OTP & Links tab
  const otpContainer = document.getElementById('otp-table-container');
  if (otpContainer) {
    if (codes.length > 0) {
      otpContainer.innerHTML = codes.map(c => `
        <div class="otp-card-item">
          <div>
            <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 4px;">来源: <strong>${escapeHtml(c.service_name)}</strong> (${c.code_type})</div>
            <div class="otp-code-big">${escapeHtml(c.code)}</div>
            ${c.verification_url ? `<div style="font-size: 12px; margin-top: 6px;"><a href="${escapeHtml(c.verification_url)}" target="_blank" style="color: var(--primary-color);">点击打开验证链接 ↗</a></div>` : ''}
            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">上下文: ${escapeHtml(c.context_snippet || '-')}</div>
          </div>
          <button class="btn btn-outline btn-sm copy-btn" data-code="${escapeHtml(c.code)}">复制</button>
        </div>
      `).join('');

      otpContainer.querySelectorAll('.copy-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const code = btn.getAttribute('data-code');
          navigator.clipboard.writeText(code).then(() => showToast(`已复制: ${code}`));
        });
      });
    } else {
      otpContainer.innerHTML = '<div class="empty-hint">本封邮件未提取到验证码或激活链接</div>';
    }
  }

  // Raw Header / EML
  const rawEl = document.getElementById('raw-preview-content');
  if (rawEl) rawEl.innerText = email.raw_eml || '无 Raw 数据';
}

function renderDetailEmpty() {
  if (emptyDetailState) emptyDetailState.style.display = 'flex';
  if (detailContent) detailContent.style.display = 'none';
}

// Code Generator Snippets
function updateCodeSnippets() {
  const genInput = document.getElementById('gen-email-input');
  const targetEmail = (genInput ? genInput.value.trim() : '') || 'test@domain.com';
  const apiHost = window.location.origin || 'http://127.0.0.1:8000';
  const box = document.getElementById('code-snippet-box');
  if (!box) return;

  if (state.activeCodeLang === 'python-api') {
    box.innerText = `import requests
import time

# 1. 极速长轮询获取最新验证码 (timeout=30 秒自动挂起等待邮件到达)
url = "${apiHost}/api/v1/codes/latest"
params = {
    "to": "${targetEmail}",
    "timeout": 30
}

response = requests.get(url, params=params).json()

if response.get("found"):
    code = response["code"]
    service = response["service_name"]
    print(f"✅ 成功获取 {service} 验证码: {code}")
else:
    print("❌ 超时未收到验证码")`;
  } else if (state.activeCodeLang === 'python-imap') {
    box.innerText = `import imaplib
import email
from email.header import decode_header
import re

# 2. 通过标准虚拟 IMAP4 服务拉取并取码
IMAP_HOST = "127.0.0.1"
IMAP_PORT = 1143
USERNAME = "${targetEmail}"
PASSWORD = "password123"

mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)
mail.login(USERNAME, PASSWORD)
mail.select("INBOX")

# 搜索未读或所有邮件
status, messages = mail.search(None, "ALL")
msg_ids = messages[0].split()

if msg_ids:
    latest_id = msg_ids[-1]
    res, msg_data = mail.fetch(latest_id, "(RFC822)")
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)
    print("邮件主题:", msg.get("Subject"))
    # 从邮件正文正则提取 4-8 位验证码
    body = raw_email.decode('utf-8', errors='ignore')
    match = re.search(r'(?:验证码|code)[^\\d]{0,10}?(\\d{4,8})', body, re.IGNORECASE)
    if match:
        print("提取到验证码:", match.group(1))

mail.logout()`;
  } else if (state.activeCodeLang === 'curl') {
    box.innerText = `# cURL 极速取码 (长轮询 30s)
curl -X GET "${apiHost}/api/v1/codes/latest?to=${encodeURIComponent(targetEmail)}&timeout=30"`;
  } else if (state.activeCodeLang === 'nodejs') {
    box.innerText = `// Node.js Fetch 示例
async function getLatestOTP() {
  const res = await fetch("${apiHost}/api/v1/codes/latest?to=${encodeURIComponent(targetEmail)}&timeout=30");
  const data = await res.json();
  if (data.found) {
    console.log("验证码:", data.code, "服务:", data.service_name);
  } else {
    console.log("未找到验证码:", data.message);
  }
}
getLatestOTP();`;
  }
}

// Helpers
function showToast(msg) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerText = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 2800);
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

function formatTime(timeStr) {
  if (!timeStr) return '';
  try {
    const date = new Date(timeStr);
    const now = new Date();
    const diff = (now - date) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    return timeStr.split(' ')[0];
  } catch {
    return timeStr;
  }
}
