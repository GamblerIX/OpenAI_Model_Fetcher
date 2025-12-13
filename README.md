# OpenAI Model Fetcher

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6--Fluent-green)](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

> 一个用于从 OpenAI 兼容 API 端点获取和显示可用模型列表的桌面 GUI 应用程序。

## 快速开始

1. 浏览器访问 [Release](https://github.com/GamblerIX/OpenAI_Model_Fetcher/releases/latest) 页面
2. 下载以下任一版本（推荐 Nuitka）：
   - `OpenAI_Model_Fetcher_Nuitka.exe` - 推荐，体积小性能好
   - `OpenAI_Model_Fetcher_PyAppify.exe` - 支持多版本切换且UI更美观
   - `OpenAI_Model_Fetcher_PyInstaller.exe` - 兼容性好
3. 双击启动即可

---

## 特性

- 🚀 **快速获取模型列表**：从任何 OpenAI 兼容的 API 端点获取模型
- 🎨 **现代化深色主题界面**：使用 PySide6-Fluent-Widgets 构建的直观 GUI
- 🔍 **模型搜索筛选**：快速搜索和过滤模型列表
- 📁 **多配置文件支持**：保存和管理多个 API 配置
- 📋 **一键复制**：轻松复制单个模型 ID 到剪贴板
- 📤 **模型导出**：将模型 ID 列表导出到文本文件
- ⚡ **异步操作**：网络请求不阻塞用户界面
- 🛡️ **错误处理**：详细的错误提示和用户指导
- ⌨️ **键盘快捷键**：支持 Enter 键获取和 F5 刷新

---

## 开发相关

### 源码运行

```bash
git clone https://github.com/GamblerIX/OpenAI_Model_Fetcher.git
cd OpenAI_Model_Fetcher
pip install -r requirements.txt
python main.py
```

### 项目结构

```
OpenAI_Model_Fetcher/
├── .github/workflows/  # CI/CD 自动构建
├── main.py             # 应用程序唯一文件
├── requirements.txt    # Python 依赖
└── README.md           # 项目文档
```

### 配置

应用程序在用户主目录保存配置：`~/.openai_model_fetcher/`

支持多个配置文件，可在侧边栏"配置"页面管理。

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Enter  | 获取模型 |
| F5     | 刷新列表 |

### 错误代码

| 代码 | 说明 |
|------|------|
| 401  | 未授权 - 检查 API Key |
| 404  | 未找到 - 确认端点路径 |
| 500  | 服务器错误 |

---

## 许可证：[MIT LICENSE](LICENSE)

> **温馨提示**：请妥善保管您的 API Key，不要与他人分享。
