@echo off
chcp 65001 >nul
echo =======================================================
echo   正在启动 邮件接收与智能取码平台 (MailCapture & OTP Hub)
echo =======================================================
python app/main.py
pause
