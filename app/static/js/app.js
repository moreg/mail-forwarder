// MailCapture & OTP Hub Client Logic
let state = {
  currentFilter: 'all', // 'all', 'unread', 'codes'
  selectedGroup: null,   // 转发母账号/分组 (如 apple01@icloud.com 或 直接收件)
  selectedAlias: null,   // 收件别名 (如 dev01@domain.com)
  selectedService: null,
  selectedSender: null,
  searchQuery: '',
  emails: [],
  selectedEmailId: null,
  stats: null,
  activeTab: 'html',
  activeCodeLang: 'python-api',
  apiKey: localStorage.getItem('mc_api_key') || '',
  authToken: localStorage.getItem('mc_auth_token') || '',
  authRequired: false,
  isLoggedIn: false
};

const SERVICE_ICONS = {
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
  steam: '🎮',
  netflix: '🎬',
  facebook: '👥',
  meta: '👥'
};

function getServiceIcon(serviceName) {
  if (!serviceName) return '🏢';
  const lower = serviceName.toLowerCase();
  for (const [k, icon] of Object.entries(SERVICE_ICONS)) {
    if (lower.includes(k)) return icon;
  }
  return '🏢';
}

function getGroupIcon(groupName) {
  if (!groupName) return '📂';
  const lower = groupName.toLowerCase();
  if (lower.includes('icloud') || lower.includes('apple') || lower.includes('me.com')) return '🍏';
  if (lower.includes('gmail') || lower.includes('google')) return '🔍';
  if (lower.includes('outlook') || lower.includes('hotmail') || lower.includes('microsoft')) return '🪟';
  if (lower.includes('直接收件') || lower.includes('direct')) return '🌐';
  return '📧';
}

function clearAllSidebarActive() {
  document.querySelectorAll(
    '.group-header, .group-alias-item, .service-group-item, .sender-group-item, .inbox-alias-item'
  ).forEach(el => el.classList.remove('active'));
}

// Presets for Test Mail Injection
const PRESETS = {
  apple: {
    from: "appleid@id.apple.com",
    to: "dev01@yourdomain.com",
    forwarded_by: "apple_master1@icloud.com",
    subject: "您的 Apple ID 验证码是 948210",
    body: "您好，您的 Apple ID 验证码是 948210。请在 10 分钟内输入此代码以完成双重认证登录。请勿与任何人共享此代码。"
  },
  github: {
    from: "noreply@github.com",
    to: "bot_developer@yourdomain.com",
    forwarded_by: "company_fwd@icloud.com",
    subject: "GitHub device verification code",
    body: "Please enter the following verification code to sign in to your GitHub account: 519283\nThis code will expire in 10 minutes."
  },
  telegram: {
    from: "login@telegram.org",
    to: "tg_alias@yourdomain.com",
    forwarded_by: "company_fwd@icloud.com",
    subject: "Telegram login code: 62819",
    body: "Dear user, here is your Telegram login code: 62819\nDo not give this code to anyone, even if they say they're from Telegram!"
  },
  google: {
    from: "no-reply@accounts.google.com",
    to: "google_direct@yourdomain.com",
    forwarded_by: "",
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
  if (state.authToken) {
    options.headers['Authorization'] = `Bearer ${state.authToken}`;
  }
  if (state.apiKey) {
    options.headers['X-API-Key'] = state.apiKey;
  }
  const res = await fetch(url, options);
  if (res.status === 401) {
    state.isLoggedIn = false;
    showLoginModal();
  }
  return res;
}

// Init App
let dashboardInitialized = false;

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  initDashboard();
  checkAuthAndInit();
});

// Setup Event Listeners
function setupEventListeners() {
  // Filter tabs
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      state.currentFilter = item.getAttribute('data-filter');
      state.selectedGroup = null;
      state.selectedAlias = null;
      state.selectedService = null;
      state.selectedSender = null;
      clearAllSidebarActive();
      fetchEmails();
    });
  });

  // Toggle all groups collapse/expand
  bindClick('btn-toggle-all-groups', () => {
    const nodes = document.querySelectorAll('.group-node');
    if (!nodes.length) return;
    const anyClosed = Array.from(nodes).some(n => !n.classList.contains('open'));
    nodes.forEach(n => {
      if (anyClosed) n.classList.add('open');
      else n.classList.remove('open');
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

// Auth Management
async function checkAuthAndInit() {
  try {
    const res = await fetch('/api/v1/auth/status', {
      headers: state.authToken ? { 'Authorization': `Bearer ${state.authToken}` } : {}
    });
    const json = await res.json();
    if (json.success) {
      state.authRequired = json.auth_required;
      if (json.auth_required) {
        if (json.logged_in) {
          state.isLoggedIn = true;
          hideLoginModal();
          updateLogoutButton(true);
          initDashboard();
        } else {
          state.isLoggedIn = false;
          showLoginModal();
          updateLogoutButton(false);
        }
      } else {
        state.isLoggedIn = true;
        hideLoginModal();
        updateLogoutButton(false);
        initDashboard();
      }
    } else {
      initDashboard();
    }
  } catch (err) {
    console.error('Auth check error:', err);
    initDashboard();
  }
}

function initDashboard() {
  if (dashboardInitialized) return;
  dashboardInitialized = true;
  setupSSE();
  fetchStats();
  fetchEmails();
  updateCodeSnippets();
  updateWizardContent();
}

function showLoginModal() {
  const modal = document.getElementById('modal-login');
  if (modal) {
    modal.style.display = 'flex';
    const input = document.getElementById('login-password-input');
    if (input) {
      input.value = '';
      setTimeout(() => input.focus(), 150);
    }
    const err = document.getElementById('login-err-tip');
    if (err) err.style.display = 'none';
  }
}

function hideLoginModal() {
  const modal = document.getElementById('modal-login');
  if (modal) modal.style.display = 'none';
}

function updateLogoutButton(show) {
  const btn = document.getElementById('btn-logout');
  if (btn) {
    btn.style.display = show ? 'inline-flex' : 'none';
  }
}

function setupModals() {
  const guideModal = document.getElementById('modal-guide');
  const apiModal = document.getElementById('modal-api');
  const settingsModal = document.getElementById('modal-settings');
  const testModal = document.getElementById('modal-test');
  const wizardModal = document.getElementById('modal-domain-wizard');
  const loginForm = document.getElementById('login-form');

  // Login form submit
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const pwdInput = document.getElementById('login-password-input');
      const errTip = document.getElementById('login-err-tip');
      const password = pwdInput ? pwdInput.value.trim() : '';

      try {
        const res = await fetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: password })
        });
        const json = await res.json();
        if (json.success) {
          state.authToken = json.token || '';
          localStorage.setItem('mc_auth_token', state.authToken);
          state.isLoggedIn = true;
          hideLoginModal();
          updateLogoutButton(state.authRequired);
          showToast('✅ 登录成功');
          initDashboard();
        } else {
          if (errTip) {
            errTip.innerText = json.detail || '密码或 API Key 错误';
            errTip.style.display = 'block';
          }
        }
      } catch (err) {
        if (errTip) {
          errTip.innerText = '登录失败: ' + err.message;
          errTip.style.display = 'block';
        }
      }
    });
  }

  // Toggle login password visibility
  bindClick('btn-toggle-login-pwd', () => {
    const pwdInput = document.getElementById('login-password-input');
    if (pwdInput) {
      pwdInput.type = pwdInput.type === 'password' ? 'text' : 'password';
    }
  });

  // Logout button
  bindClick('btn-logout', async () => {
    try {
      await fetch('/api/v1/auth/logout', { method: 'POST' });
    } catch (_) {}
    state.authToken = '';
    state.isLoggedIn = false;
    localStorage.removeItem('mc_auth_token');
    if (evtSource) {
      evtSource.close();
      evtSource = null;
    }
    updateLogoutButton(false);
    showLoginModal();
    showToast('已退出登录');
  });

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
        const forwardEl = document.getElementById('test-forwarded');
        const subjEl = document.getElementById('test-subject');
        const bodyEl = document.getElementById('test-body');
        if (fromEl) fromEl.value = p.from;
        if (toEl) toEl.value = p.to;
        if (forwardEl) forwardEl.value = p.forwarded_by || '';
        if (subjEl) subjEl.value = p.subject;
        if (bodyEl) bodyEl.value = p.body;
      }
    });
  });

  // Send Test Mail
  bindClick('btn-send-test', async () => {
    const fromEl = document.getElementById('test-from');
    const toEl = document.getElementById('test-to');
    const forwardEl = document.getElementById('test-forwarded');
    const subjEl = document.getElementById('test-subject');
    const bodyEl = document.getElementById('test-body');

    const fromAddr = fromEl ? fromEl.value.trim() : 'service@apple.com';
    const toAddr = toEl ? toEl.value.trim() : 'my_user@mydomain.com';
    const forwardedBy = forwardEl ? forwardEl.value.trim() : '';
    const subject = subjEl ? subjEl.value.trim() : 'Test Subject';
    const body = bodyEl ? bodyEl.value.trim() : 'Test Body';

    try {
      const res = await apiFetch('/api/v1/config/test-inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_address: fromAddr,
          to_address: toAddr,
          forwarded_by: forwardedBy,
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

  // Batch Export Pickup Links Modal
  const exportModal = document.getElementById('modal-export-links');
  bindClick('btn-export-links', () => {
    if (exportModal) exportModal.style.display = 'flex';
    initExportLinksModal();
  });
  bindClick('btn-close-export', () => {
    if (exportModal) exportModal.style.display = 'none';
  });
  bindClick('btn-cancel-export', () => {
    if (exportModal) exportModal.style.display = 'none';
  });

  bindEvent('export-group-select', 'change', updateExportLinks);
  bindEvent('export-domain-input', 'input', updateExportLinks);
  bindEvent('export-format-select', 'change', updateExportLinks);

  bindClick('btn-copy-all-links', () => {
    const textarea = document.getElementById('export-links-textarea');
    if (textarea && textarea.value) {
      navigator.clipboard.writeText(textarea.value).then(() => {
        showToast('✅ 已成功复制全部邮箱清单！');
      });
    }
  });

  // Domain Wizard Pool Generator Event Bindings
  bindEvent('wizard-pool-type', 'change', updateWizardPool);
  bindEvent('wizard-pool-prefix', 'input', updateWizardPool);
  bindEvent('wizard-pool-count', 'change', updateWizardPool);
  bindEvent('wizard-pool-format', 'change', updateWizardPool);
  bindClick('btn-regen-pool', updateWizardPool);
  bindClick('btn-copy-wizard-pool', copyWizardPool);

  // Manage & Batch Delete Mailboxes Modal Bindings
  bindClick('btn-manage-mailboxes', openManageMailboxesModal);
  bindClick('btn-close-manage-mailboxes', closeManageMailboxesModal);
  bindClick('btn-cancel-manage-mailboxes', closeManageMailboxesModal);
  bindEvent('manage-mailboxes-search', 'input', renderManageMailboxesTable);
  bindEvent('manage-mailboxes-group-filter', 'change', renderManageMailboxesTable);
  bindEvent('manage-check-all', 'change', toggleCheckAllManageMailboxes);
  bindClick('btn-confirm-batch-delete-mailboxes', executeBatchDeleteMailboxes);
}

function initExportLinksModal() {
  const domainInput = document.getElementById('export-domain-input');
  if (domainInput && !domainInput.value) {
    domainInput.value = window.location.origin;
  }
  const groupSelect = document.getElementById('export-group-select');
  if (groupSelect && state.stats && state.stats.groups) {
    const prevVal = groupSelect.value;
    groupSelect.innerHTML = '<option value="__all__">全部母账号与别名邮箱</option>' +
      state.stats.groups.map(g => `<option value="${escapeHtml(g.group_name)}">${escapeHtml(g.group_name)} (${g.aliases ? g.aliases.length : 0} 个别名)</option>`).join('');
    if (prevVal) groupSelect.value = prevVal;
  }
  updateExportLinks();
}

function updateExportLinks() {
  const groupSelect = document.getElementById('export-group-select');
  const domainInput = document.getElementById('export-domain-input');
  const formatSelect = document.getElementById('export-format-select');
  const textarea = document.getElementById('export-links-textarea');
  const countEl = document.getElementById('export-total-count');

  if (!state.stats || !state.stats.groups) {
    if (textarea) textarea.value = '暂无邮箱数据';
    return;
  }

  const selectedGroup = groupSelect ? groupSelect.value : '__all__';
  let domain = (domainInput ? domainInput.value.trim() : '') || window.location.origin;
  domain = domain.replace(/\/+$/, '');
  const format = formatSelect ? formatSelect.value : 'pool_link';

  let aliasesList = [];
  state.stats.groups.forEach(g => {
    if (selectedGroup === '__all__' || g.group_name === selectedGroup) {
      if (g.aliases && g.aliases.length > 0) {
        g.aliases.forEach(a => {
          if (!aliasesList.includes(a.to_address)) {
            aliasesList.push(a.to_address);
          }
        });
      }
    }
  });

  if (countEl) countEl.innerText = `${aliasesList.length} 个邮箱`;

  if (aliasesList.length === 0) {
    if (textarea) textarea.value = '(所选分组下暂无活跃别名邮箱)';
    return;
  }

  const formattedLines = aliasesList.map(addr => {
    if (format === 'pure_email') {
      return addr;
    } else if (format === 'pool_api') {
      return `${addr}----${domain}/api/v1/codes/latest?to=${addr}&timeout=30`;
    } else {
      const pickupUrl = `${domain}/mailboxes/${addr}`;
      return `${addr}----${pickupUrl}`;
    }
  });

  if (textarea) textarea.value = formattedLines.join('\n');
}

function updateWizardContent() {
  const domainInput = document.getElementById('wizard-domain-input');
  const domain = (domainInput ? domainInput.value.trim() : '') || 'mydomain.com';
  const apiHost = window.location.origin || 'http://YOUR_SERVER_IP:8000';

  // 1. Generate example Apple ID emails with dual copy options (纯邮箱 / 邮箱池格式)
  const chipsContainer = document.getElementById('wizard-email-chips');
  if (chipsContainer) {
    const examples = [
      `apple@${domain}`,
      `id01@${domain}`,
      `user_apple@${domain}`,
      `vip@${domain}`,
      `anything@${domain}`
    ];
    chipsContainer.innerHTML = examples.map(e => {
      const poolFormat = `${e}----${apiHost}/mailboxes/${e}`;
      return `
        <div class="email-chip">
          <span class="chip-addr" onclick="navigator.clipboard.writeText('${e}').then(()=>showToast('已复制纯邮箱: ${e}'))" title="点击复制纯邮箱地址">
            <span>✉️ ${e}</span>
          </span>
          <div class="chip-actions">
            <button type="button" class="chip-btn" onclick="navigator.clipboard.writeText('${e}').then(()=>showToast('已复制纯邮箱: ${e}'))" title="复制纯邮箱">复制</button>
            <button type="button" class="chip-btn chip-btn-pool" onclick="navigator.clipboard.writeText('${poolFormat}').then(()=>showToast('已复制邮箱池格式: ${poolFormat}'))" title="复制标准邮箱池格式: 邮箱----取件链接">🔗 邮箱池</button>
          </div>
        </div>
      `;
    }).join('');
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

  // 4. Update Mailbox Pool generator
  updateWizardPool();
}

function updateWizardPool() {
  const domainInput = document.getElementById('wizard-domain-input');
  const domain = (domainInput ? domainInput.value.trim() : '') || 'mydomain.com';
  const apiHost = window.location.origin || 'http://YOUR_SERVER_IP:8000';

  const typeEl = document.getElementById('wizard-pool-type');
  const prefixEl = document.getElementById('wizard-pool-prefix');
  const countEl = document.getElementById('wizard-pool-count');
  const formatEl = document.getElementById('wizard-pool-format');
  const textarea = document.getElementById('wizard-pool-textarea');
  const countBadge = document.getElementById('wizard-pool-count-badge');

  const type = typeEl ? typeEl.value : 'prefix_seq';
  const rawPrefix = (prefixEl ? prefixEl.value.trim() : '') || 'apple';
  const count = parseInt(countEl ? countEl.value : '10') || 10;
  const format = formatEl ? formatEl.value : 'pool_link';

  if (countBadge) countBadge.innerText = `${count} 个邮箱`;

  const randomStr = (len = 5) => {
    const chars = 'abcdefghjkmnpqrstuvwxyz23456789';
    let res = '';
    for (let i = 0; i < len; i++) {
      res += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return res;
  };

  const nameWords = ['user', 'bot', 'vip', 'member', 'service', 'dev', 'agent', 'team', 'account', 'client'];

  const generatedEmails = [];
  for (let i = 1; i <= count; i++) {
    let localPart = '';
    if (type === 'prefix_seq') {
      const numStr = String(i).padStart(2, '0');
      localPart = `${rawPrefix}${numStr}`;
    } else if (type === 'random_str') {
      localPart = `${rawPrefix ? rawPrefix + '_' : ''}${randomStr(5)}`;
    } else if (type === 'name_seq') {
      const word = nameWords[(i - 1) % nameWords.length];
      localPart = `${word}${i}`;
    }
    generatedEmails.push(`${localPart}@${domain}`);
  }

  const lines = generatedEmails.map(addr => {
    if (format === 'pure_email') {
      return addr;
    } else if (format === 'pool_api') {
      return `${addr}----${apiHost}/api/v1/codes/latest?to=${addr}&timeout=30`;
    } else {
      // Standard pool link format: email----pickup_url
      return `${addr}----${apiHost}/mailboxes/${addr}`;
    }
  });

  if (textarea) {
    textarea.value = lines.join('\n');
  }
}

function copyWizardPool() {
  const textarea = document.getElementById('wizard-pool-textarea');
  if (textarea && textarea.value) {
    navigator.clipboard.writeText(textarea.value).then(() => {
      showToast('✅ 已成功复制批量邮箱池！可直接粘贴至注册机/脚本使用');
    });
  }
}

// Settings API Handlers
async function loadSettingsData() {
  try {
    const res = await apiFetch('/api/v1/config');
    const json = await res.json();
    if (json.success) {
      const cfg = json.data;
      const adminPassEl = document.getElementById('cfg-admin-pass');
      const keyEl = document.getElementById('cfg-api-key');
      const passEl = document.getElementById('cfg-imap-pass');
      const kwEl = document.getElementById('cfg-otp-keywords');
      const statApi = document.getElementById('stat-api-port');
      const statSmtp = document.getElementById('stat-smtp-port');
      const statImap = document.getElementById('stat-imap-port');

      if (adminPassEl) adminPassEl.value = cfg.server.admin_password || '';
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
  const adminPassEl = document.getElementById('cfg-admin-pass');
  const keyEl = document.getElementById('cfg-api-key');
  const passEl = document.getElementById('cfg-imap-pass');
  const kwEl = document.getElementById('cfg-otp-keywords');

  const adminPassword = adminPassEl ? adminPassEl.value : '';
  const apiKey = keyEl ? keyEl.value.trim() : '';
  const imapPass = passEl ? passEl.value.trim() : 'password123';
  const rawKeywords = kwEl ? kwEl.value : '';
  const keywordsList = rawKeywords.split(/[,，\n]/).map(k => k.trim()).filter(Boolean);

  try {
    const res = await apiFetch('/api/v1/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        admin_password: adminPassword,
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
      checkAuthAndInit();
    }
  } catch (e) {
    showToast('保存失败: ' + e.message);
  }
}

// Setup Server-Sent Events (SSE)
let evtSource = null;
function setupSSE() {
  if (evtSource) {
    evtSource.close();
    evtSource = null;
  }
  if (state.authRequired && !state.isLoggedIn) {
    return;
  }
  let sseUrl = '/api/v1/stream';
  const params = [];
  if (state.authToken) {
    params.push(`token=${encodeURIComponent(state.authToken)}`);
  }
  if (state.apiKey) {
    params.push(`api_key=${encodeURIComponent(state.apiKey)}`);
  }
  if (params.length > 0) {
    sseUrl += '?' + params.join('&');
  }

  try {
    evtSource = new EventSource(sseUrl);

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
  } catch (err) {
    console.error('Failed to init SSE:', err);
  }
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
  const uniqueGroupsEl = document.getElementById('unique-groups-count');
  const uniqueServicesEl = document.getElementById('unique-services-count');
  const uniqueSendersEl = document.getElementById('unique-senders-count');

  if (totalEl) totalEl.innerText = stats.total_emails || 0;
  if (unreadEl) unreadEl.innerText = stats.unread_emails || 0;
  if (codesEl) codesEl.innerText = stats.total_codes || 0;
  if (uniqueGroupsEl) uniqueGroupsEl.innerText = (stats.groups || []).length;
  if (uniqueServicesEl) uniqueServicesEl.innerText = (stats.top_services || []).length;
  if (uniqueSendersEl) uniqueSendersEl.innerText = (stats.top_senders || []).length;

  if (stats.config) {
    const chipApi = document.getElementById('chip-api-port');
    const chipSmtp = document.getElementById('chip-smtp-port');
    const chipImap = document.getElementById('chip-imap-port');
    if (chipApi) chipApi.innerText = stats.config.api_port || '8000';
    if (chipSmtp) chipSmtp.innerText = stats.config.smtp_port || '2525';
    if (chipImap) chipImap.innerText = stats.config.imap_port || '1143';
  }

  // 1. Render Forwarding Groups Tree (转发母账号 -> 下属别名层级树)
  renderGroupsTree(stats.groups || []);

  // 2. Render Services Group (发件服务商分组)
  const servicesList = document.getElementById('services-group-list');
  if (servicesList) {
    if (stats.top_services && stats.top_services.length > 0) {
      servicesList.innerHTML = stats.top_services.map(item => `
        <div class="service-group-item inbox-alias-item ${state.selectedService === item.service_name ? 'active' : ''}" data-service="${escapeHtml(item.service_name)}">
          <span class="group-label" title="${escapeHtml(item.service_name)}">
            <span class="group-icon">${getServiceIcon(item.service_name)}</span>
            <span>${escapeHtml(item.service_name)}</span>
          </span>
          <span class="badge-sm">${item.count}</span>
        </div>
      `).join('');

      servicesList.querySelectorAll('.service-group-item').forEach(el => {
        el.addEventListener('click', () => {
          const sName = el.getAttribute('data-service');
          if (state.selectedService === sName) {
            state.selectedService = null;
            el.classList.remove('active');
          } else {
            clearAllSidebarActive();
            el.classList.add('active');
            state.selectedService = sName;
            state.selectedGroup = null;
            state.selectedAlias = null;
            state.selectedSender = null;
          }
          fetchEmails();
        });
      });
    } else {
      servicesList.innerHTML = '<div class="empty-hint">暂无服务分组</div>';
    }
  }

  // 3. Render Senders Group (常用发件人分组)
  const sendersList = document.getElementById('senders-group-list');
  if (sendersList) {
    if (stats.top_senders && stats.top_senders.length > 0) {
      sendersList.innerHTML = stats.top_senders.map(item => `
        <div class="sender-group-item inbox-alias-item ${state.selectedSender === item.from_address ? 'active' : ''}" data-sender="${escapeHtml(item.from_address)}">
          <span class="group-label" title="${escapeHtml(item.from_address)}">
            <span class="group-icon">✉️</span>
            <span>${escapeHtml(item.from_address)}</span>
          </span>
          <span class="badge-sm">${item.count}</span>
        </div>
      `).join('');

      sendersList.querySelectorAll('.sender-group-item').forEach(el => {
        el.addEventListener('click', () => {
          const sAddr = el.getAttribute('data-sender');
          if (state.selectedSender === sAddr) {
            state.selectedSender = null;
            el.classList.remove('active');
          } else {
            clearAllSidebarActive();
            el.classList.add('active');
            state.selectedSender = sAddr;
            state.selectedGroup = null;
            state.selectedAlias = null;
            state.selectedService = null;
          }
          fetchEmails();
        });
      });
    } else {
      sendersList.innerHTML = '<div class="empty-hint">暂无发件人记录</div>';
    }
  }
}

// Render Forwarding Groups Tree
function renderGroupsTree(groups) {
  const container = document.getElementById('forwarding-groups-tree');
  if (!container) return;

  if (!groups || groups.length === 0) {
    container.innerHTML = '<div class="empty-hint">暂无转发分组</div>';
    return;
  }

  container.innerHTML = groups.map((g, idx) => {
    const isGroupActive = (state.selectedGroup === g.group_name && !state.selectedAlias);
    const hasActiveChild = (g.aliases || []).some(a => a.to_address === state.selectedAlias);
    const isGroupOpen = isGroupActive || hasActiveChild || idx === 0;
    const groupIcon = getGroupIcon(g.group_name);

    const aliasesHtml = (g.aliases || []).map(a => {
      const isAliasActive = state.selectedAlias === a.to_address;
      return `
        <div class="group-alias-item ${isAliasActive ? 'active' : ''}" data-alias="${escapeHtml(a.to_address)}" data-group="${escapeHtml(g.group_name)}">
          <div class="group-alias-label" title="${escapeHtml(a.to_address)}">
            <span class="group-icon">📥</span>
            <span>${escapeHtml(a.to_address)}</span>
          </div>
          <div class="group-badges">
            ${a.latest_code ? `<span class="mini-code-pill" title="最新验证码: ${escapeHtml(a.latest_code)}">${escapeHtml(a.latest_code)}</span>` : ''}
            <span class="badge-sm">${a.email_count}</span>
            <button class="btn-copy-alias-link" data-copy-link="${escapeHtml(a.to_address)}" title="复制该邮箱专属访客取件链接">🔗</button>
            <button class="btn-delete-alias" data-delete-alias="${escapeHtml(a.to_address)}" data-count="${a.email_count}" title="删除此邮箱及其所有邮件">🗑️</button>
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="group-node ${isGroupOpen ? 'open' : ''}" data-group-node="${escapeHtml(g.group_name)}">
        <div class="group-header ${isGroupActive ? 'active' : ''}" data-group="${escapeHtml(g.group_name)}">
          <div class="group-title-wrap" title="${escapeHtml(g.group_name)}">
            <span class="group-caret">▶</span>
            <span class="group-icon">${groupIcon}</span>
            <span class="group-name">${escapeHtml(g.group_name)}</span>
          </div>
          <div class="group-badges">
            ${g.unread_emails > 0 ? `<span class="badge-unread-dot" title="${g.unread_emails} 封未读"></span>` : ''}
            <span class="badge-sm">${g.total_emails}</span>
          </div>
        </div>
        <div class="group-children">
          ${aliasesHtml || '<div class="empty-hint" style="padding: 4px 0;">暂无别名</div>'}
        </div>
      </div>
    `;
  }).join('');

  // 1. Group Header Clicks (Toggle tree & filter whole group)
  container.querySelectorAll('.group-header').forEach(header => {
    header.addEventListener('click', (e) => {
      const gName = header.getAttribute('data-group');
      const node = header.closest('.group-node');

      // Toggle collapse/open on click
      if (node) {
        node.classList.toggle('open');
      }

      if (state.selectedGroup === gName && !state.selectedAlias) {
        state.selectedGroup = null;
        header.classList.remove('active');
      } else {
        clearAllSidebarActive();
        header.classList.add('active');
        state.selectedGroup = gName;
        state.selectedAlias = null;
        state.selectedService = null;
        state.selectedSender = null;
      }
      fetchEmails();
    });
  });

  // 2. Alias Item Clicks (Filter specific alias inbox)
  container.querySelectorAll('.group-alias-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const alias = item.getAttribute('data-alias');
      const gName = item.getAttribute('data-group');

      if (state.selectedAlias === alias) {
        state.selectedAlias = null;
        item.classList.remove('active');
      } else {
        clearAllSidebarActive();
        item.classList.add('active');
        state.selectedAlias = alias;
        state.selectedGroup = gName;
        state.selectedService = null;
        state.selectedSender = null;
      }
      fetchEmails();
    });
  });

  // 3. Quick Copy Pickup Link Button
  container.querySelectorAll('.btn-copy-alias-link').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const addr = btn.getAttribute('data-copy-link');
      if (addr) {
        const pickupUrl = `${window.location.origin}/mailboxes/${addr}`;
        const copyText = `${addr}----${pickupUrl}`;
        navigator.clipboard.writeText(copyText).then(() => {
          showToast(`已复制取件格式: ${addr}----${pickupUrl}`);
        });
      }
    });
  });

  // 4. Single Alias Delete Button
  container.querySelectorAll('.btn-delete-alias').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const addr = btn.getAttribute('data-delete-alias');
      const count = btn.getAttribute('data-count') || '0';
      if (!addr) return;
      if (!confirm(`确定要删除邮箱 【${addr}】 及其所有的 ${count} 封邮件和验证码吗？此操作不可恢复。`)) return;
      batchDeleteMailboxes([addr]);
    });
  });
}

// Batch delete mailboxes handler
async function batchDeleteMailboxes(mailboxesList) {
  if (!mailboxesList || mailboxesList.length === 0) return;
  try {
    const res = await apiFetch('/api/v1/emails/batch-delete-mailboxes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mailboxes: mailboxesList })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✅ 已成功删除 ${mailboxesList.length} 个邮箱 (清理 ${data.deleted_count} 封邮件)`);
      if (mailboxesList.includes(state.selectedAlias)) {
        state.selectedAlias = null;
      }
      state.selectedEmailId = null;
      renderDetailEmpty();
      await fetchStats();
      await fetchEmails();
      const modal = document.getElementById('modal-manage-mailboxes');
      if (modal && modal.style.display !== 'none') {
        renderManageMailboxesTable();
      }
    } else {
      showToast('删除失败: ' + (data.message || '未知错误'));
    }
  } catch (err) {
    showToast('删除失败: ' + err.message);
  }
}

// Mailbox Management Modal Functions
let manageMailboxesSelected = new Set();

function openManageMailboxesModal() {
  const modal = document.getElementById('modal-manage-mailboxes');
  if (!modal) return;
  modal.style.display = 'flex';
  manageMailboxesSelected.clear();

  const groupSelect = document.getElementById('manage-mailboxes-group-filter');
  if (groupSelect && state.stats && state.stats.groups) {
    groupSelect.innerHTML = '<option value="__all__">全部分组</option>' +
      state.stats.groups.map(g => `<option value="${escapeHtml(g.group_name)}">${escapeHtml(g.group_name)}</option>`).join('');
  }

  const searchInput = document.getElementById('manage-mailboxes-search');
  if (searchInput) searchInput.value = '';

  renderManageMailboxesTable();
}

function closeManageMailboxesModal() {
  const modal = document.getElementById('modal-manage-mailboxes');
  if (modal) modal.style.display = 'none';
  manageMailboxesSelected.clear();
}

function getAllMailboxesFromStats() {
  const list = [];
  if (!state.stats || !state.stats.groups) return list;
  state.stats.groups.forEach(g => {
    (g.aliases || []).forEach(a => {
      list.push({
        to_address: a.to_address,
        group_name: g.group_name,
        email_count: a.email_count,
        unread_count: a.unread_count,
        latest_code: a.latest_code,
        latest_service: a.latest_service,
        last_seen: a.last_seen
      });
    });
  });
  return list;
}

function renderManageMailboxesTable() {
  const tbody = document.getElementById('manage-mailboxes-tbody');
  const searchInput = document.getElementById('manage-mailboxes-search');
  const groupSelect = document.getElementById('manage-mailboxes-group-filter');
  const checkAllBox = document.getElementById('manage-check-all');

  if (!tbody) return;

  const q = (searchInput ? searchInput.value.trim().toLowerCase() : '');
  const selectedGroup = groupSelect ? groupSelect.value : '__all__';

  let items = getAllMailboxesFromStats();
  if (selectedGroup !== '__all__') {
    items = items.filter(i => i.group_name === selectedGroup);
  }
  if (q) {
    items = items.filter(i => i.to_address.toLowerCase().includes(q) || i.group_name.toLowerCase().includes(q));
  }

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px 0;">暂无可管理的域名邮箱</td></tr>`;
    if (checkAllBox) checkAllBox.checked = false;
    updateManageSelectedBadge();
    return;
  }

  const allVisibleSelected = items.length > 0 && items.every(i => manageMailboxesSelected.has(i.to_address));
  if (checkAllBox) checkAllBox.checked = allVisibleSelected;

  tbody.innerHTML = items.map(item => {
    const isChecked = manageMailboxesSelected.has(item.to_address);
    const pickupUrl = `${window.location.origin}/mailboxes/${encodeURIComponent(item.to_address)}`;
    return `
      <tr class="${isChecked ? 'selected-row' : ''}">
        <td style="text-align: center;">
          <input type="checkbox" class="manage-item-checkbox" data-addr="${escapeHtml(item.to_address)}" ${isChecked ? 'checked' : ''}>
        </td>
        <td>
          <div style="font-weight: 600; font-family: var(--font-mono); color: var(--primary-color); display: flex; align-items: center; gap: 6px;">
            <span>${escapeHtml(item.to_address)}</span>
            <a href="${pickupUrl}" target="_blank" class="btn-xs-icon" style="text-decoration: none;" title="打开此邮箱独立取件页">↗</a>
          </div>
        </td>
        <td><span class="badge-sm" style="background-color: #f1f5f9;">${escapeHtml(item.group_name)}</span></td>
        <td style="text-align: center;"><span class="badge-sm" style="background-color: #e0f2fe; color: #0284c7; font-weight: 700;">${item.email_count}</span></td>
        <td>${item.latest_code ? `<span class="mini-code-pill">${escapeHtml(item.latest_code)}</span>` : '<span style="color: var(--text-muted);">-</span>'}</td>
        <td style="color: var(--text-secondary); font-size: 11.5px;">${formatTime(item.last_seen)}</td>
        <td style="text-align: right;">
          <button type="button" class="btn btn-ghost btn-danger btn-sm btn-delete-single-table" data-addr="${escapeHtml(item.to_address)}" data-count="${item.email_count}" style="padding: 2px 8px; font-size: 11px;">删除</button>
        </td>
      </tr>
    `;
  }).join('');

  // Row checkbox click
  tbody.querySelectorAll('.manage-item-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      const addr = cb.getAttribute('data-addr');
      if (cb.checked) {
        manageMailboxesSelected.add(addr);
      } else {
        manageMailboxesSelected.delete(addr);
      }
      renderManageMailboxesTable();
    });
  });

  // Single delete button in table
  tbody.querySelectorAll('.btn-delete-single-table').forEach(btn => {
    btn.addEventListener('click', () => {
      const addr = btn.getAttribute('data-addr');
      const count = btn.getAttribute('data-count') || '0';
      if (!addr) return;
      if (!confirm(`确定要删除邮箱 【${addr}】 及其所有的 ${count} 封邮件和验证码吗？`)) return;
      batchDeleteMailboxes([addr]);
    });
  });

  updateManageSelectedBadge();
}

function updateManageSelectedBadge() {
  const selectedCountEl = document.getElementById('manage-mailboxes-selected-count');
  const deleteBtn = document.getElementById('btn-confirm-batch-delete-mailboxes');
  const count = manageMailboxesSelected.size;
  if (selectedCountEl) selectedCountEl.innerText = `已选 ${count} 个`;
  if (deleteBtn) {
    deleteBtn.disabled = count === 0;
    deleteBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
      批量删除所选邮箱 (${count})
    `;
  }
}

function toggleCheckAllManageMailboxes(e) {
  const isChecked = e.target.checked;
  const searchInput = document.getElementById('manage-mailboxes-search');
  const groupSelect = document.getElementById('manage-mailboxes-group-filter');

  const q = (searchInput ? searchInput.value.trim().toLowerCase() : '');
  const selectedGroup = groupSelect ? groupSelect.value : '__all__';

  let items = getAllMailboxesFromStats();
  if (selectedGroup !== '__all__') {
    items = items.filter(i => i.group_name === selectedGroup);
  }
  if (q) {
    items = items.filter(i => i.to_address.toLowerCase().includes(q) || i.group_name.toLowerCase().includes(q));
  }

  if (isChecked) {
    items.forEach(i => manageMailboxesSelected.add(i.to_address));
  } else {
    items.forEach(i => manageMailboxesSelected.delete(i.to_address));
  }
  renderManageMailboxesTable();
}

async function executeBatchDeleteMailboxes() {
  const list = Array.from(manageMailboxesSelected);
  if (list.length === 0) return;
  if (!confirm(`⚠️ 批量删除确认：\n确定要永久删除选中的 ${list.length} 个域名邮箱及其全部邮件和验证码吗？\n此操作不可撤销！`)) {
    return;
  }
  await batchDeleteMailboxes(list);
  manageMailboxesSelected.clear();
}

// Detail cache to avoid repeated network fetching when switching back and forth between emails
const emailDetailCache = new Map();

// Fetch Emails
async function fetchEmails(autoSelectFirst = false) {
  let url = '/api/v1/emails?page=1&page_size=50';
  if (state.selectedGroup && !state.selectedAlias) {
    url += `&group=${encodeURIComponent(state.selectedGroup)}`;
  }
  if (state.selectedAlias) {
    url += `&to=${encodeURIComponent(state.selectedAlias)}`;
  }
  if (state.selectedService) {
    url += `&service=${encodeURIComponent(state.selectedService)}`;
  }
  if (state.selectedSender) {
    url += `&from=${encodeURIComponent(state.selectedSender)}`;
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

      if (autoSelectFirst && items.length > 0) {
        selectEmail(items[0].id);
      } else if (state.selectedEmailId && !items.some(e => e.id === state.selectedEmailId)) {
        state.selectedEmailId = null;
        renderDetailEmpty();
      }
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
      <div class="card-otp-chip" data-copy-code="${escapeHtml(item.latest_code)}" title="点击直接复制验证码">
        <span class="service-pill">${escapeHtml(item.service_name || 'OTP')}</span>
        <span>${escapeHtml(item.latest_code)}</span>
      </div>
    ` : '';

    const forwardBadge = (item.forwarded_by && item.forwarded_by !== '直接收件') ? `
      <span class="badge-forward" title="转发母账号: ${escapeHtml(item.forwarded_by)}">
        <span>↪</span> ${escapeHtml(item.forwarded_by)}
      </span>
    ` : '';

    return `
      <div class="mail-card ${isSelected ? 'active' : ''} ${isUnread ? 'unread' : ''}" data-id="${item.id}">
        <div class="card-top">
          <span class="card-sender" title="${escapeHtml(item.from_address)}">${escapeHtml(item.from_address)}</span>
          <div class="card-top-right">
            <span class="card-time">${formatTime(item.created_at)}</span>
            <button class="btn-card-delete" title="直接删除此邮件" data-delete-id="${item.id}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </div>
        <div class="card-to">
          <span>To: ${escapeHtml(item.to_address)}</span>
          ${forwardBadge}
        </div>
        <div class="card-subject">${escapeHtml(item.subject || '(无主题)')}</div>
        ${otpChip}
      </div>
    `;
  }).join('');

  // 1. Delete button click handler on card
  mailCardsList.querySelectorAll('.btn-card-delete').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = parseInt(btn.getAttribute('data-delete-id'));
      if (!id) return;
      try {
        const res = await apiFetch(`/api/v1/emails/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
          showToast('邮件已删除');
          emailDetailCache.delete(id);
          if (state.selectedEmailId === id) {
            state.selectedEmailId = null;
            renderDetailEmpty();
          }
          fetchStats();
          fetchEmails();
        }
      } catch (err) {
        showToast('删除失败: ' + err.message);
      }
    });
  });

  // 2. Click to copy OTP code directly from card chip
  mailCardsList.querySelectorAll('.card-otp-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      const code = chip.getAttribute('data-copy-code');
      if (code) {
        navigator.clipboard.writeText(code).then(() => {
          showToast(`已复制验证码: ${code}`);
        });
      }
    });
  });

  // 3. Card click handler (Open detail)
  mailCardsList.querySelectorAll('.mail-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = parseInt(card.getAttribute('data-id'));
      selectEmail(id);
    });
  });
}

// Select Single Email with 0ms Instant Preview & Local Caching
async function selectEmail(id) {
  state.selectedEmailId = id;

  // 1. Update active card highlight directly (0ms DOM manipulation, no full list rebuild)
  if (mailCardsList) {
    mailCardsList.querySelectorAll('.mail-card').forEach(c => {
      if (parseInt(c.getAttribute('data-id')) === id) {
        c.classList.add('active');
        c.classList.remove('unread');
      } else {
        c.classList.remove('active');
      }
    });
  }

  // 2. Instant Optimistic Render from summary
  const summaryItem = (state.emails || []).find(e => e.id === id);
  if (summaryItem) {
    if (!summaryItem.is_read) {
      summaryItem.is_read = 1;
      const unreadCountEl = document.getElementById('count-unread');
      if (unreadCountEl) {
        const cur = parseInt(unreadCountEl.innerText) || 0;
        if (cur > 0) unreadCountEl.innerText = cur - 1;
      }
    }
    renderEmailDetailPreview(summaryItem);
  }

  // 3. Check memory cache for instant full rendering
  if (emailDetailCache.has(id)) {
    renderEmailDetail(emailDetailCache.get(id));
    return;
  }

  // 4. Fetch full details asynchronously
  try {
    const res = await apiFetch(`/api/v1/emails/${id}`);
    const json = await res.json();
    if (json.success) {
      emailDetailCache.set(id, json.data);
      if (state.selectedEmailId === id) {
        renderEmailDetail(json.data);
      }
    }
  } catch (e) {
    showToast('获取邮件详情失败: ' + e.message);
  }
}

// Instant 0ms Preview Render
function renderEmailDetailPreview(email) {
  if (emptyDetailState) emptyDetailState.style.display = 'none';
  if (detailContent) detailContent.style.display = 'flex';

  const subjEl = document.getElementById('detail-subject');
  const fromEl = document.getElementById('detail-from');
  const toEl = document.getElementById('detail-to');
  const timeEl = document.getElementById('detail-time');
  const forwardRow = document.getElementById('meta-row-forwarded');
  const forwardEl = document.getElementById('detail-forwarded');

  if (subjEl) subjEl.innerText = email.subject || '(无主题)';
  if (fromEl) fromEl.innerText = email.from_address;
  if (toEl) toEl.innerText = email.to_address;
  if (timeEl) timeEl.innerText = email.created_at;

  if (forwardRow && forwardEl) {
    if (email.forwarded_by && email.forwarded_by !== '直接收件') {
      forwardEl.innerText = email.forwarded_by;
      forwardRow.style.display = 'flex';
    } else {
      forwardRow.style.display = 'none';
    }
  }

  // OTP Banner Preview
  const otpBanner = document.getElementById('otp-highlight-banner');
  if (email.latest_code) {
    if (otpBanner) otpBanner.style.display = 'flex';
    const tagEl = document.getElementById('otp-service-tag');
    const valEl = document.getElementById('otp-highlight-value');
    const snipEl = document.getElementById('otp-snippet');
    const copyBtn = document.getElementById('btn-oneclick-copy');

    if (tagEl) tagEl.innerText = email.service_name || 'OTP';
    if (valEl) valEl.innerText = email.latest_code;
    if (snipEl) snipEl.innerText = '已识别到验证信息';

    if (copyBtn) {
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(email.latest_code).then(() => {
          showToast(`已复制验证码: ${email.latest_code}`);
        });
      };
    }
  } else {
    if (otpBanner) otpBanner.style.display = 'none';
  }

  // Plain Text Preview
  const textEl = document.getElementById('text-preview-content');
  if (textEl && email.body_text) textEl.innerText = email.body_text;
}

function renderEmailDetail(email) {
  if (emptyDetailState) emptyDetailState.style.display = 'none';
  if (detailContent) detailContent.style.display = 'flex';

  const subjEl = document.getElementById('detail-subject');
  const fromEl = document.getElementById('detail-from');
  const toEl = document.getElementById('detail-to');
  const timeEl = document.getElementById('detail-time');
  const forwardRow = document.getElementById('meta-row-forwarded');
  const forwardEl = document.getElementById('detail-forwarded');

  if (subjEl) subjEl.innerText = email.subject || '(无主题)';
  if (fromEl) fromEl.innerText = email.from_address;
  if (toEl) toEl.innerText = email.to_address;
  if (timeEl) timeEl.innerText = email.created_at;

  if (forwardRow && forwardEl) {
    if (email.forwarded_by && email.forwarded_by !== '直接收件') {
      forwardEl.innerText = email.forwarded_by;
      forwardRow.style.display = 'flex';
    } else {
      forwardRow.style.display = 'none';
    }
  }

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
