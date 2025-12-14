import sys
import os
import json
import threading
import webbrowser
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, urljoin

# Fix for PyAppify: PySide6 requires PATH environment variable
if 'PATH' not in os.environ:
    os.environ['PATH'] = ''

import requests
from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
)
from qfluentwidgets import (
    LineEdit, PushButton, PrimaryPushButton, BodyLabel,
    StrongBodyLabel, CardWidget, ScrollArea, InfoBar,
    InfoBarPosition, setTheme, Theme, FluentIcon,
    NavigationItemPosition, SubtitleLabel, TitleLabel,
    SearchLineEdit, ComboBox
)
from qfluentwidgets.window import FluentWindow


class APIError(Exception):
    pass


class OpenAIAPIClient:
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url.strip()
        self.api_key = api_key.strip() if api_key else None

    @staticmethod
    def validate_url(url: str) -> bool:
        try:
            parsed = urlparse(url.strip())
            return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
        except Exception:
            return False

    def fetch_models(self) -> dict:
        try:
            endpoint = urljoin(self.base_url.rstrip('/') + '/', 'models')
            headers = {'Accept': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            resp = requests.get(endpoint, timeout=30, headers=headers)
            
            error_msgs = {401: "认证失败：API密钥无效或缺失",
                         404: f"端点不存在：{endpoint}", 500: "服务器内部错误"}
            if resp.status_code in error_msgs:
                raise APIError(error_msgs[resp.status_code])
            if resp.status_code != 200:
                raise APIError(f"HTTP错误：状态码 {resp.status_code}")

            data = resp.json()
            if not isinstance(data.get('data'), list):
                raise APIError("响应格式错误：缺少有效的'data'字段")
            return data

        except requests.exceptions.Timeout:
            raise APIError("请求超时：连接超过30秒未响应")
        except requests.exceptions.ConnectionError as e:
            raise APIError(f"连接错误：{e}")
        except requests.exceptions.RequestException as e:
            raise APIError(f"网络请求错误：{e}")
        except (ValueError, KeyError) as e:
            raise APIError(f"响应解析错误：{e}")
        except APIError:
            raise
        except Exception as e:
            raise APIError(f"未知错误：{e}")


class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".openai_model_fetcher"
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, name: str) -> Path:
        return self.config_dir / f"{name}.json"

    def save(self, name: str, url: str, api_key: str = None):
        self._get_path(name).write_text(json.dumps({
            "base_url": url, "api_key": api_key or "",
            "last_updated": datetime.now().isoformat()
        }, indent=2, ensure_ascii=False), encoding='utf-8')

    def load(self, name: str) -> dict:
        try:
            path = self._get_path(name)
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8'))
                return {"base_url": data.get("base_url"), "api_key": data.get("api_key", "")}
        except Exception:
            pass
        return {"base_url": None, "api_key": None}

    def delete(self, name: str):
        self._get_path(name).unlink(missing_ok=True)

    def list_profiles(self) -> list:
        return [p.stem for p in self.config_dir.glob("*.json")]

    def clear_all(self):
        for p in self.config_dir.glob("*.json"):
            p.unlink(missing_ok=True)


class WorkerSignals(QObject):
    success = Signal(dict)
    error = Signal(str)


class ModelCard(CardWidget):
    def __init__(self, model_id: str, parent=None):
        super().__init__(parent)
        self.model_id = model_id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        label = BodyLabel(f"○ {model_id}")
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        copy_btn = PushButton("Copy")
        copy_btn.setFixedWidth(80)
        copy_btn.clicked.connect(self._copy)

        layout.addWidget(label)
        layout.addWidget(copy_btn)

    def _copy(self):
        QApplication.clipboard().setText(self.model_id)
        InfoBar.success("已复制", self.model_id, parent=self.window(),
                       position=InfoBarPosition.TOP_RIGHT, duration=2000)


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")
        self.config = ConfigManager()
        self.model_ids, self.model_cards, self.all_models = [], [], []
        self.signals = WorkerSignals()
        self.current_profile = "default"
        self._setup_ui()
        self._connect()
        self._load_config()
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_F5), self, self._fetch)

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(36, 20, 36, 20)
        main.setSpacing(15)
        main.addWidget(TitleLabel("获取模型列表"))

        # 输入卡片
        input_card = CardWidget()
        inp = QVBoxLayout(input_card)
        inp.setContentsMargins(16, 16, 16, 16)
        inp.setSpacing(10)

        self.url_entry = LineEdit()
        self.url_entry.setPlaceholderText("例如: https://api.openai.com/v1")
        self.url_entry.setFixedHeight(40)

        self.key_entry = LineEdit()
        self.key_entry.setPlaceholderText("sk-...")
        self.key_entry.setEchoMode(LineEdit.Password)
        self.key_entry.setFixedHeight(40)

        self.validation_label = BodyLabel("")
        self.validation_label.setStyleSheet("color: #ff6b6b;")
        self.validation_label.hide()

        for label, widget in [("Base URL:", self.url_entry), ("API Key:", self.key_entry)]:
            inp.addWidget(StrongBodyLabel(label))
            inp.addWidget(widget)
        inp.addWidget(self.validation_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.fetch_btn = PrimaryPushButton("获取")
        self.fetch_btn.setFixedHeight(40)
        self.fetch_btn.setIcon(FluentIcon.DOWNLOAD)
        self.refresh_btn = PushButton("刷新 (F5)")
        self.refresh_btn.setFixedHeight(40)
        self.refresh_btn.setIcon(FluentIcon.SYNC)
        btn_layout.addWidget(self.fetch_btn)
        btn_layout.addWidget(self.refresh_btn)

        # 结果卡片
        results_card = CardWidget()
        res = QVBoxLayout(results_card)
        res.setContentsMargins(16, 16, 16, 16)
        res.setSpacing(10)

        # 搜索和导出
        header = QHBoxLayout()
        header.addWidget(StrongBodyLabel("Models:"))
        header.addStretch()
        
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("搜索模型...")
        self.search_box.setFixedWidth(200)
        self.search_box.textChanged.connect(self._filter_models)
        header.addWidget(self.search_box)
        
        self.export_btn = PushButton("导出")
        self.export_btn.setIcon(FluentIcon.SAVE)
        self.export_btn.setEnabled(False)
        header.addWidget(self.export_btn)

        self.scroll_area = ScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(250)
        self.scroll_area.setStyleSheet("""
            ScrollArea { background-color: #2d2d2d; border-radius: 8px; border: none; }
            QScrollBar:vertical { width: 8px; background: transparent; }
            QScrollBar::handle:vertical { background: #555; border-radius: 4px; }
        """)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(8, 8, 8, 8)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)

        res.addLayout(header)
        res.addWidget(self.scroll_area)

        main.addWidget(input_card)
        main.addLayout(btn_layout)
        main.addWidget(results_card, 1)

    def _connect(self):
        self.fetch_btn.clicked.connect(self._fetch)
        self.refresh_btn.clicked.connect(self._fetch)
        self.export_btn.clicked.connect(self._export)
        self.url_entry.returnPressed.connect(self._fetch)
        self.key_entry.returnPressed.connect(self._fetch)
        self.signals.success.connect(self._on_success)
        self.signals.error.connect(self._on_error)

    def _filter_models(self, text: str):
        text = text.lower().strip()
        self._clear_model_cards()
        filtered = [m for m in self.all_models if text in m.lower()] if text else self.all_models
        for model_id in filtered:
            self._add_model_card(model_id)
        self.model_ids = filtered

    def _fetch(self):
        url = self.url_entry.text().strip()
        if not url:
            return self._show_validation("请输入BaseURL")
        if not OpenAIAPIClient.validate_url(url):
            return self._show_validation("无效的URL格式")

        self.validation_label.hide()
        self._set_loading(True)
        self._notify("正在获取模型列表...", "info")
        self._clear_models()

        def worker():
            try:
                result = OpenAIAPIClient(url, self.key_entry.text().strip()).fetch_models()
                self.signals.success.emit(result)
            except APIError as e:
                self.signals.error.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, result: dict):
        self._set_loading(False)
        models = result.get("data", [])
        if not models:
            return self._notify("未找到任何模型", "warning")

        self.all_models = [m.get("id", "Unknown") for m in models]
        for model_id in self.all_models:
            self._add_model_card(model_id)
        self.model_ids = self.all_models.copy()
        self._notify(f"成功获取 {len(models)} 个模型", "success")
        self.config.save(self.current_profile, self.url_entry.text().strip(), 
                        self.key_entry.text().strip())

    def _on_error(self, msg: str):
        self._set_loading(False)
        hints = {"超时": "检查网络连接", "连接": "检查URL是否可访问", "401": "检查API密钥",
                 "404": "确认BaseURL正确", "500": "服务器问题，稍后重试"}
        hint = next((v for k, v in hints.items() if k in msg), "检查BaseURL和网络")
        InfoBar.error("错误", f"{msg}\n提示: {hint}", parent=self.window(),
                     position=InfoBarPosition.TOP_RIGHT, duration=5000)

    def _export(self):
        if not self.model_ids:
            return InfoBar.warning("提示", "没有可导出的模型", parent=self.window(),
                                  position=InfoBarPosition.TOP_RIGHT, duration=3000)
        try:
            filename = f"model_ids_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            Path(filename).write_text('\n'.join(self.model_ids), encoding='utf-8')
            InfoBar.success("导出成功", f"已导出到 {filename}", parent=self.window(),
                           position=InfoBarPosition.TOP_RIGHT, duration=4000)
        except Exception as e:
            InfoBar.error("导出失败", str(e), parent=self.window(),
                         position=InfoBarPosition.TOP_RIGHT, duration=4000)

    def _add_model_card(self, model_id: str):
        card = ModelCard(model_id)
        self.model_cards.append(card)
        self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, card)
        self.export_btn.setEnabled(True)

    def _clear_model_cards(self):
        for c in self.model_cards:
            c.deleteLater()
        self.model_cards.clear()

    def _clear_models(self):
        self._clear_model_cards()
        self.model_ids.clear()
        self.all_models.clear()
        self.search_box.clear()
        self.export_btn.setEnabled(False)

    def _set_loading(self, loading: bool):
        self.fetch_btn.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        self.fetch_btn.setText("Loading..." if loading else "获取")

    def _show_validation(self, msg: str):
        self.validation_label.setText(msg)
        self.validation_label.show()

    def _notify(self, msg: str, level: str = "info"):
        getattr(InfoBar, level)("", msg, parent=self.window(),
                                position=InfoBarPosition.TOP_RIGHT, duration=3000)

    def _load_config(self):
        cfg = self.config.load(self.current_profile)
        if cfg.get("base_url"):
            self.url_entry.setText(cfg["base_url"])
            if cfg.get("api_key"):
                self.key_entry.setText(cfg["api_key"])
            self._notify("已加载保存的配置", "info")

    def switch_profile(self, name: str):
        self.current_profile = name
        self._clear_models()
        self._load_config()


class ProfilesPage(QWidget):
    profile_switched = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("profilesPage")
        self.config = ConfigManager()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(20)
        layout.addWidget(TitleLabel("配置管理"))

        # 新建配置
        new_card = CardWidget()
        new_layout = QVBoxLayout(new_card)
        new_layout.setContentsMargins(16, 16, 16, 16)
        new_layout.setSpacing(12)
        new_layout.addWidget(SubtitleLabel("新建配置"))

        row = QHBoxLayout()
        self.new_name = LineEdit()
        self.new_name.setPlaceholderText("配置名称")
        self.new_name.setFixedHeight(36)
        self.create_btn = PrimaryPushButton("创建")
        self.create_btn.setIcon(FluentIcon.ADD)
        self.create_btn.clicked.connect(self._create_profile)
        row.addWidget(self.new_name)
        row.addWidget(self.create_btn)
        new_layout.addLayout(row)

        # 配置列表
        list_card = CardWidget()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)
        list_layout.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("已保存的配置"))
        self.refresh_list_btn = PushButton("刷新")
        self.refresh_list_btn.setIcon(FluentIcon.SYNC)
        self.refresh_list_btn.setFixedWidth(80)
        self.refresh_list_btn.clicked.connect(self._refresh_list)
        header.addStretch()
        header.addWidget(self.refresh_list_btn)
        list_layout.addLayout(header)

        self.profile_scroll = ScrollArea()
        self.profile_scroll.setWidgetResizable(True)
        self.profile_scroll.setMinimumHeight(300)
        self.profile_scroll.setStyleSheet("""
            ScrollArea { background-color: #2d2d2d; border-radius: 8px; border: none; }
        """)

        self.profile_content = QWidget()
        self.profile_layout = QVBoxLayout(self.profile_content)
        self.profile_layout.setContentsMargins(8, 8, 8, 8)
        self.profile_layout.setSpacing(8)
        self.profile_layout.addStretch()
        self.profile_scroll.setWidget(self.profile_content)
        list_layout.addWidget(self.profile_scroll)

        layout.addWidget(new_card)
        layout.addWidget(list_card, 1)

        self._refresh_list()

    def _create_profile(self):
        name = self.new_name.text().strip()
        if not name:
            return InfoBar.warning("提示", "请输入配置名称", parent=self.window(),
                                  position=InfoBarPosition.TOP_RIGHT, duration=3000)
        if name in self.config.list_profiles():
            return InfoBar.warning("提示", "配置已存在", parent=self.window(),
                                  position=InfoBarPosition.TOP_RIGHT, duration=3000)
        self.config.save(name, "", "")
        self.new_name.clear()
        self._refresh_list()
        InfoBar.success("成功", f"已创建配置: {name}", parent=self.window(),
                       position=InfoBarPosition.TOP_RIGHT, duration=3000)

    def _refresh_list(self):
        # 清空列表
        for i in reversed(range(self.profile_layout.count() - 1)):
            w = self.profile_layout.itemAt(i).widget()
            if w:
                w.deleteLater()

        profiles = self.config.list_profiles()
        if not profiles:
            profiles = ["默认"]
            self.config.save("默认", "", "")

        for name in profiles:
            card = CardWidget()
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 8, 12, 8)

            label = BodyLabel(f"📁 {name}")
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

            use_btn = PushButton("使用")
            use_btn.setFixedWidth(60)
            use_btn.clicked.connect(lambda _, n=name: self._use_profile(n))

            del_btn = PushButton("删除")
            del_btn.setIcon(FluentIcon.DELETE)
            del_btn.setFixedWidth(80)
            del_btn.clicked.connect(lambda _, n=name: self._delete_profile(n))

            row.addWidget(label)
            row.addWidget(use_btn)
            row.addWidget(del_btn)

            self.profile_layout.insertWidget(self.profile_layout.count() - 1, card)

    def _use_profile(self, name: str):
        self.profile_switched.emit(name)
        InfoBar.success("已切换", f"当前配置: {name}", parent=self.window(),
                       position=InfoBarPosition.TOP_RIGHT, duration=2000)

    def _delete_profile(self, name: str):
        if name == "default":
            return InfoBar.warning("提示", "无法删除默认配置", parent=self.window(),
                                  position=InfoBarPosition.TOP_RIGHT, duration=3000)
        self.config.delete(name)
        self._refresh_list()
        InfoBar.success("已删除", f"配置: {name}", parent=self.window(),
                       position=InfoBarPosition.TOP_RIGHT, duration=2000)


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.config = ConfigManager()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(20)
        layout.addWidget(TitleLabel("设置"))

        # 配置卡片
        cfg_card = CardWidget()
        cfg = QVBoxLayout(cfg_card)
        cfg.setContentsMargins(16, 16, 16, 16)
        cfg.setSpacing(12)
        cfg.addWidget(SubtitleLabel("数据管理"))
        path_label = BodyLabel(f"配置目录: {self.config.config_dir}")
        path_label.setStyleSheet("color: #888;")
        cfg.addWidget(path_label)
        clear_btn = PushButton("清除所有配置")
        clear_btn.setIcon(FluentIcon.DELETE)
        clear_btn.clicked.connect(self._clear)
        cfg.addWidget(clear_btn)

        # 快捷键卡片
        shortcut_card = CardWidget()
        sc = QVBoxLayout(shortcut_card)
        sc.setContentsMargins(16, 16, 16, 16)
        sc.setSpacing(8)
        sc.addWidget(SubtitleLabel("快捷键"))
        shortcuts = [("Enter", "获取模型"), ("F5", "刷新列表")]
        for key, desc in shortcuts:
            row = QHBoxLayout()
            key_label = BodyLabel(key)
            key_label.setStyleSheet("color: #4fc3f7; font-weight: bold;")
            row.addWidget(key_label)
            row.addWidget(BodyLabel(f"- {desc}"))
            row.addStretch()
            sc.addLayout(row)

        # 关于卡片
        about_card = CardWidget()
        about = QVBoxLayout(about_card)
        about.setContentsMargins(16, 16, 16, 16)
        about.setSpacing(8)
        about.addWidget(SubtitleLabel("关于"))
        about.addWidget(BodyLabel("OpenAI Model Fetcher v1.1"))
        info = BodyLabel("用于获取 OpenAI 兼容 API 的模型列表")
        info.setStyleSheet("color: #888;")
        about.addWidget(info)

        layout.addWidget(cfg_card)
        layout.addWidget(shortcut_card)
        layout.addWidget(about_card)
        layout.addStretch()

    def _clear(self):
        try:
            self.config.clear_all()
            InfoBar.success("成功", "所有配置已清除", parent=self.window(),
                           position=InfoBarPosition.TOP_RIGHT, duration=3000)
        except Exception as e:
            InfoBar.error("错误", str(e), parent=self.window(),
                         position=InfoBarPosition.TOP_RIGHT, duration=3000)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenAI Model Fetcher")
        self.resize(1000, 750)
        self.setMinimumSize(800, 600)
        setTheme(Theme.DARK)
        self.navigationInterface.setExpandWidth(140)

        self.home_page = HomePage(self)
        self.profiles_page = ProfilesPage(self)
        self.settings_page = SettingsPage(self)

        # 连接配置切换信号
        self.profiles_page.profile_switched.connect(self.home_page.switch_profile)

        # 侧边栏导航
        self.addSubInterface(self.home_page, FluentIcon.HOME, "主页")
        self.addSubInterface(self.profiles_page, FluentIcon.FOLDER, "配置")
        
        self.navigationInterface.addItem(
            routeKey="github", icon=FluentIcon.GITHUB, text="GitHub",
            onClick=lambda: webbrowser.open('https://github.com/GamblerIX/OpenAI_Model_Fetcher/'),
            position=NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(self.settings_page, FluentIcon.SETTING, "设置",
                            position=NavigationItemPosition.BOTTOM)
        self.navigationInterface.setCurrentItem(self.home_page.objectName())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    MainWindow().show()
    sys.exit(app.exec())
