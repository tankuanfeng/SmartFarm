# SmartFarm

智慧农场监测系统，面向鸡舍环境监测和农作物产量预测，提供本机开发用的注册、登录和主功能工作台。

## 运行应用

从工作区根目录运行：

```powershell
pip install -r .\requirements.txt
$env:SECRET_KEY = (& python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

也可以进入本项目目录后运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\requirements.txt
$env:SECRET_KEY = (& python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

打开 <http://127.0.0.1:5000>。用户数据保存在 `instance\smartfarm.sqlite3`，密码只以 Werkzeug 哈希形式存储。

**安全提示：** 当前开发服务器使用本机 HTTP。POST 表单不会把密码放进 URL，但 HTTP 不加密网络传输；仅在本机回环地址使用，不要开放到局域网或互联网。正式部署前需配置 HTTPS 和强随机 `SECRET_KEY`。

## 运行测试

在项目目录运行：

```powershell
python -m unittest discover -s tests
```

从工作区根目录运行：

```powershell
python -m unittest discover -s .\SmartFarm\tests
```
