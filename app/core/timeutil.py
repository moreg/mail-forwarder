"""时间工具：统一把库内 UTC 时间字符串转成无时区歧义的 epoch 秒。

下游取码客户端（如 turb-gpt-free-register 的 generic_api 渠道）会把无时区
后缀的时间字符串按其本机时区解析，非 UTC 机器上会放行旧验证码（UTC-X）
或误杀新验证码（UTC+X）；epoch 秒数字没有歧义。
"""
from datetime import datetime, timezone
from typing import Optional


def utc_str_to_epoch(value) -> Optional[int]:
    """解析 "YYYY-MM-DD HH:MM:SS"(库内按 UTC 存储) 为 epoch 秒；失败返回 None。"""
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return int(dt.replace(tzinfo=timezone.utc).timestamp())
