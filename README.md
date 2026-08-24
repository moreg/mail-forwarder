# 邮件接收与智能取码平台 (MailCapture & OTP Hub)

一个功能完备、高并发、支持多种邮件接入方式（**iCloud 转发 / Cloudflare 邮件路由 / 自建 SMTP / Webhook**）与智能提取验证码（OTP）、并提供 **REST API 长轮询极速取码** 和 **标准虚拟 IMAP4 服务** 的现代化邮件聚合管理系统。

---

## ✨ 核心特性

- 📥 **多途径邮件接入**：
  - **内置 SMTP 接收服务** (端口 25 或 2525)：直接作为 MX 节点接收来自公网的直接投递或转发邮件。
  - **Cloudflare / 通用 Webhook 接入** (`/api/v1/webhook/inbound`)：配合 Cloudflare 免费邮件路由，无需开放服务器 25 端口即可零成本接收任意域名邮件。
  - **iCloud 规则转发聚合**：无缝接收由 iCloud 邮箱、Gmail、Outlook 等设置的自动转发规则邮件。
- 🔑 **智能取码引擎 (OTP Extractor)**：
  - 自动识别 Apple/iCloud、Google、Telegram、GitHub、OpenAI、Discord 等主流服务。
  - 上下文多模态算法精准提取 **4~8 位数字/混合验证码、动态口令、PIN码** 以及 **激活/确认链接**。
- ⚡ **自动化极速取码接口 (REST API)**：
  - `GET /api/v1/codes/latest?to=xxx&timeout=30`：提供带长轮询挂起特性的取码接口，邮件未到时自动等待，邮件到达秒级返回。
- 📬 **虚拟 IMAP4 服务** (端口 1143 / 143)：
  - 支持任何标准邮件客户端（Outlook, Thunderbird）或 Python `imaplib` 等自动化脚本登录读取。
- 🖥️ **现代化实时 Web 仪表盘**：
  - 内置 Server-Sent Events (SSE) 实时流，新邮件无感刷新、一键复制验证码、邮件沙箱 HTML 预览、多别名过滤。

---

## 🚀 快速启动

### 1. 本地启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务 (默认包含 Web控制台: 8000, SMTP: 2525, IMAP: 1143)
python app/main.py
```

启动后访问: `http://127.0.0.1:8000` 即可进入 Web 管理面板。

### 2. Docker 一键运行

```bash
# 构建镜像
docker build -t mailcapture-otp .

# 启动容器
docker run -d \
  -p 8000:8000 \
  -p 2525:2525 \
  -p 1143:1143 \
  -v $(pwd)/data:/app/data \
  --name mailcapture \
  mailcapture-otp
```

---

## ⚙️ 配置文件说明 (`config.yaml`)

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  api_key: ""                       # API 访问秘钥 (留空免鉴权)

smtp:
  enabled: true
  host: "0.0.0.0"
  port: 2525                        # SMTP 接收端口 (正式公网部署建议 25)
  domain: "localhost"

imap:
  enabled: true
  host: "0.0.0.0"
  port: 1143                        # 虚拟 IMAP 监听端口
  auth_password: "password123"      # 统一 IMAP 访问密码

storage:
  db_path: "data/mailbox.db"        # SQLite 数据库文件
```

---

## 📖 接入方案指南

### 方案 1: iCloud 邮件自动转发 (最常用)
1. 打开 **[iCloud 网页版 (iCloud.com)](https://www.icloud.com/mail)** 并登录。
2. 点击左下角 **设置 (⚙️) -> 规则 (Rules)**。
3. 添加新规则：
   - 条件：**如果邮件发往 / 包含某些关键字**（或所有邮件）
   - 操作：**转发到 (Forward to)** -> 填入您的专属接收地址（如 `user@yourdomain.com`）。
4. 您的系统在收到 iCloud 转发的邮件后，即可秒级提取出验证码。

### 方案 2: Cloudflare Email Routing 零公网端口接收 (100% 免费推荐)
1. 在 Cloudflare 绑定您的域名，在侧边栏进入 **Email Routing (电子邮件路由)**。
2. 开启路由并添加 Catch-all 规则或指定别名。
3. 创建一个免费的 **Cloudflare Worker**，填入以下代码转发至本系统：
```javascript
export default {
  async email(message, env, ctx) {
    const rawEmail = await new Response(message.raw).text();
    await fetch("http://YOUR_SERVER_IP:8000/api/v1/webhook/inbound", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        raw: rawEmail,
        to: message.to,
        from: message.from
      })
    });
  }
}
```

---

## 💻 脚本取码示例

### 1. Python REST API 极速取码 (长轮询)

```python
import requests

# 请求最新验证码，timeout=30 表示如果在30秒内有新邮件到达，立即返回验证码
resp = requests.get("http://127.0.0.1:8000/api/v1/codes/latest", params={
    "to": "user@yourdomain.com",
    "timeout": 30
}).json()

if resp.get("found"):
    print("提取到的验证码:", resp["code"])
    print("服务来源:", resp["service_name"])
else:
    print("未收到验证码:", resp["message"])
```

### 2. Python 标准 IMAP 客户端取件

```python
import imaplib
import email
import re

mail = imaplib.IMAP4("127.0.0.1", 1143)
mail.login("user@yourdomain.com", "password123")
mail.select("INBOX")

# 搜索所有邮件
status, messages = mail.search(None, "ALL")
msg_ids = messages[0].split()

if msg_ids:
    latest_id = msg_ids[-1]
    res, msg_data = mail.fetch(latest_id, "(RFC822)")
    raw_email = msg_data[0][1].decode('utf-8', errors='ignore')
    
    # 提取验证码
    match = re.search(r'(?:验证码|code)[^\d]{0,10}?(\d{4,8})', raw_email, re.IGNORECASE)
    if match:
        print("IMAP 提取到验证码:", match.group(1))

mail.logout()
```

### 3. cURL 命令行取码

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/codes/latest?to=user@yourdomain.com&timeout=30"
```

### 4. 特殊取码格式 (format=special)

访客短链页路由 `/mailboxes/{email}` 与 API 路由 `/api/v1/mailboxes/{email}` 追加 `?format=special` 后，固定只返回四个字段的精简 JSON（与 iCloud 隐私邮箱面板短链对齐），注册工具可直接解析：

```json
{"code":"123456","receivedAt":"2026-08-23T12:00:00Z","to":"user@example.com","from":"OpenAI"}
```

- `code`：最新验证码；`receivedAt`：收件时间（UTC RFC3339，`Z` 结尾）；`to`：当前邮箱地址；`from`：固定值 `OpenAI`。
- 暂无验证码时返回 `{"status":"waiting"}`（HTTP 200），轮询脚本按 `status` 判断等待、按 `code` 取值。
- 取码入口示例：`curl "http://127.0.0.1:8000/mailboxes/user@yourdomain.com?format=special"`
