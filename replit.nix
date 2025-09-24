# Replit Configuration for Telegram OTP Bot

modules = ["python-3.10"]

[nix]
channel = "stable-22_11"

[deployment]
run = ["sh", "-c", "python main.py"]

[[ports]]
localPort = 5000
externalPort = 80
