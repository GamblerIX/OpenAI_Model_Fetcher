import customtkinter as ctk
import requests
import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional, Callable
from urllib.parse import urlparse, urljoin
from datetime import datetime


# ==================== API Client ====================

class APIError(Exception):
    """API请求错误的自定义异常类"""
    pass


class OpenAIAPIClient:
    """OpenAI API客户端类"""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.strip()
        self.api_key = api_key.strip() if api_key else None
        
    @staticmethod
    def validate_url(url: str) -> bool:
        """验证URL格式"""
        try:
            url = url.strip()
            if not url:
                return False
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                return False
            if not parsed.netloc:
                return False
            return True
        except Exception:
            return False
    
    def fetch_models(self) -> Dict:
        """获取模型列表"""
        try:
            endpoint = urljoin(self.base_url.rstrip('/') + '/', 'models')
            headers = {'Accept': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            response = requests.get(
                endpoint,
                timeout=30,
                headers=headers
            )
            
            if response.status_code == 401:
                raise APIError("认证失败：API密钥无效或缺失（401 Unauthorized）")
            elif response.status_code == 404:
                raise APIError(f"端点不存在：{endpoint} 未找到（404 Not Found）")
            elif response.status_code == 500:
                raise APIError("服务器错误：API服务器内部错误（500 Internal Server Error）")
            elif response.status_code != 200:
                raise APIError(f"HTTP错误：状态码 {response.status_code}")
            
            try:
                data = response.json()
            except ValueError as e:
                raise APIError(f"JSON解析错误：响应不是有效的JSON格式 - {str(e)}")
            
            if not isinstance(data, dict):
                raise APIError("响应格式错误：期望JSON对象")
            if 'data' not in data:
                raise APIError("响应格式错误：缺少'data'字段")
            if not isinstance(data['data'], list):
                raise APIError("响应格式错误：'data'字段应为数组")
            
            return data
            
        except requests.exceptions.Timeout:
            raise APIError("请求超时：连接超过30秒未响应，请检查网络连接或BaseURL是否正确")
        except requests.exceptions.ConnectionError as e:
            raise APIError(f"连接错误：无法连接到服务器，请检查网络连接和BaseURL - {str(e)}")
        except requests.exceptions.RequestException as e:
            raise APIError(f"网络请求错误：{str(e)}")
        except APIError:
            raise
        except Exception as e:
            raise APIError(f"未知错误：{str(e)}")


# ==================== Config Manager ====================

class ConfigManager:
    """配置管理器类"""
    
    def __init__(self):
        home_dir = Path.home()
        self.config_dir = home_dir / ".openai_model_fetcher"
        self.config_file = self.config_dir / "config.json"
        self._ensure_config_dir()
    
    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            print(f"警告: 无法创建配置目录 {self.config_dir}: {e}")
        except Exception as e:
            print(f"警告: 创建配置目录时发生错误: {e}")
    
    def save_config(self, url: str, api_key: Optional[str] = None) -> None:
        """保存配置到文件"""
        try:
            config_data = {
                "base_url": url,
                "api_key": api_key if api_key else "",
                "last_updated": datetime.now().isoformat()
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
        except PermissionError as e:
            raise PermissionError(f"无法写入配置文件 {self.config_file}: 权限被拒绝") from e
        except Exception as e:
            raise Exception(f"保存配置时发生错误: {e}") from e
    
    def load_config(self) -> Dict[str, Optional[str]]:
        """从配置文件加载配置"""
        try:
            if not self.config_file.exists():
                return {"base_url": None, "api_key": None}
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                return {
                    "base_url": config_data.get("base_url"),
                    "api_key": config_data.get("api_key", "")
                }
        except json.JSONDecodeError as e:
            print(f"警告: 配置文件格式错误，将被忽略: {e}")
            return {"base_url": None, "api_key": None}
        except PermissionError as e:
            print(f"警告: 无法读取配置文件 {self.config_file}: 权限被拒绝")
            return {"base_url": None, "api_key": None}
        except Exception as e:
            print(f"警告: 加载配置时发生错误: {e}")
            return {"base_url": None, "api_key": None}
    
    def clear_config(self) -> None:
        """清除配置文件"""
        try:
            if self.config_file.exists():
                self.config_file.unlink()
        except PermissionError as e:
            raise PermissionError(f"无法删除配置文件 {self.config_file}: 权限被拒绝") from e
        except Exception as e:
            raise Exception(f"清除配置时发生错误: {e}") from e


# ==================== GUI Components ====================

class InputFrame(ctk.CTkFrame):
    """BaseURL和API Key输入框架"""
    
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Base URL
        self.url_label = ctk.CTkLabel(
            self,
            text="Base URL:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.url_label.pack(pady=(10, 5), padx=10, anchor="w")
        
        self.url_entry = ctk.CTkEntry(
            self,
            placeholder_text="例如: https://api.openai.com/v1",
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(pady=(0, 10), padx=10, fill="x")
        
        # API Key
        self.key_label = ctk.CTkLabel(
            self,
            text="API Key :",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.key_label.pack(pady=(5, 5), padx=10, anchor="w")
        
        self.key_entry = ctk.CTkEntry(
            self,
            placeholder_text="sk-...",
            height=40,
            font=ctk.CTkFont(size=13),
            show="●"
        )
        self.key_entry.pack(pady=(0, 10), padx=10, fill="x")
        
        self.validation_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="red"
        )
        self.validation_label.pack(pady=(0, 5), padx=10, anchor="w")
        self.validation_label.pack_forget()
    
    def get_url(self) -> str:
        return self.url_entry.get().strip()
    
    def get_api_key(self) -> str:
        return self.key_entry.get().strip()
    
    def set_url(self, url: str) -> None:
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
    
    def set_api_key(self, api_key: str) -> None:
        self.key_entry.delete(0, "end")
        if api_key:
            self.key_entry.insert(0, api_key)
    
    def show_validation_error(self, message: str) -> None:
        self.validation_label.configure(text=message)
        self.validation_label.pack(pady=(0, 5), padx=10, anchor="w")
    
    def hide_validation_error(self) -> None:
        self.validation_label.pack_forget()
    
    def clear(self) -> None:
        self.url_entry.delete(0, "end")
        self.key_entry.delete(0, "end")
        self.hide_validation_error()


class ControlFrame(ctk.CTkFrame):
    """控制按钮框架"""
    
    def __init__(self, master, fetch_callback: Optional[Callable] = None, 
                 refresh_callback: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.fetch_callback = fetch_callback
        self.refresh_callback = refresh_callback
        
        button_container = ctk.CTkFrame(self, fg_color="transparent")
        button_container.pack(pady=10, padx=10, fill="x")
        
        self.fetch_button = ctk.CTkButton(
            button_container,
            text="获取",
            command=self._on_fetch_click,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8
        )
        self.fetch_button.pack(side="left", padx=(0, 10), expand=True, fill="x")
        
        self.refresh_button = ctk.CTkButton(
            button_container,
            text="刷新",
            command=self._on_refresh_click,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=8,
            fg_color="gray40",
            hover_color="gray30"
        )
        self.refresh_button.pack(side="left", expand=True, fill="x")
    
    def _on_fetch_click(self) -> None:
        if self.fetch_callback:
            self.fetch_callback()
    
    def _on_refresh_click(self) -> None:
        if self.refresh_callback:
            self.refresh_callback()
    
    def set_loading_state(self, is_loading: bool) -> None:
        if is_loading:
            self.fetch_button.configure(state="disabled", text="Loading...")
            self.refresh_button.configure(state="disabled")
        else:
            self.fetch_button.configure(state="normal", text="获取成功！")
            self.refresh_button.configure(state="normal")


class ResultsFrame(ctk.CTkFrame):
    """模型列表显示框架"""
    
    def __init__(self, master, export_callback: Optional[Callable] = None, **kwargs):
        super().__init__(master, **kwargs)
        
        self.export_callback = export_callback
        self.model_ids = []
        
        # 标题和导出按钮容器
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(10, 5), padx=10, fill="x")
        
        self.title_label = ctk.CTkLabel(
            header_frame,
            text="Models:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.title_label.pack(side="left")
        
        self.export_button = ctk.CTkButton(
            header_frame,
            text="导出模型ID",
            command=self._on_export_click,
            width=100,
            height=30,
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            state="disabled"
        )
        self.export_button.pack(side="right")
        
        self.scrollable_frame = ctk.CTkScrollableFrame(
            self,
            height=300,
            fg_color="gray20"
        )
        self.scrollable_frame.pack(pady=(0, 10), padx=10, fill="both", expand=True)
        
        self.model_widgets = []
    
    def _on_export_click(self) -> None:
        if self.export_callback:
            self.export_callback()
    
    def add_model(self, model_id: str) -> None:
        self.model_ids.append(model_id)
        
        model_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="gray25")
        model_frame.pack(pady=5, padx=5, fill="x")
        
        model_label = ctk.CTkLabel(
            model_frame,
            text=f"○ {model_id}",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        model_label.pack(side="left", padx=10, pady=10, fill="x", expand=True)
        
        copy_button = ctk.CTkButton(
            model_frame,
            text="Copy",
            command=lambda: self.copy_to_clipboard(model_id),
            width=80,
            height=30,
            font=ctk.CTkFont(size=12),
            corner_radius=6
        )
        copy_button.pack(side="right", padx=10, pady=10)
        
        self.model_widgets.append(model_frame)
        self.export_button.configure(state="normal")
    
    def clear_models(self) -> None:
        for widget in self.model_widgets:
            widget.destroy()
        self.model_widgets.clear()
        self.model_ids.clear()
        self.export_button.configure(state="disabled")
    
    def get_model_ids(self) -> list:
        return self.model_ids.copy()
    
    def copy_to_clipboard(self, text: str) -> None:
        try:
            root = self.winfo_toplevel()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            print(f"已复制到剪贴板: {text}")
        except Exception as e:
            print(f"复制到剪贴板失败: {e}")


# ==================== Main Application ====================

class ModelFetcherApp:
    """主应用程序类"""
    
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.root = ctk.CTk()
        self.root.title("OpenAI Model Fetcher")
        self.root.geometry("700x650")
        self.root.minsize(600, 500)
        
        self.config_manager = ConfigManager()
        self.api_client: Optional[OpenAIAPIClient] = None
        
        self._setup_layout()
        self._load_saved_config()
        self._setup_keyboard_shortcuts()
    
    def _setup_layout(self) -> None:
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(3, weight=0)
        self.root.grid_columnconfigure(0, weight=1)
        
        main_container = ctk.CTkFrame(self.root, fg_color="transparent")
        main_container.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=20, pady=20)
        main_container.grid_rowconfigure(2, weight=1)
        main_container.grid_columnconfigure(0, weight=1)
        
        self.input_frame = InputFrame(main_container)
        self.input_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.input_frame.url_entry.bind("<KeyRelease>", self._on_url_change)
        
        self.control_frame = ControlFrame(
            main_container,
            fetch_callback=self._on_fetch_click,
            refresh_callback=self._on_refresh_click
        )
        self.control_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        self.results_frame = ResultsFrame(
            main_container,
            export_callback=self._on_export_click
        )
        self.results_frame.grid(row=2, column=0, sticky="nsew")
        
        self.status_label = ctk.CTkLabel(
            self.root,
            text="Ready",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.status_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
    
    def _on_fetch_click(self) -> None:
        self.fetch_models_async()
    
    def _on_refresh_click(self) -> None:
        self.fetch_models_async()
    
    def _on_export_click(self) -> None:
        model_ids = self.results_frame.get_model_ids()
        if not model_ids:
            self.show_status("没有可导出的模型", "warning")
            return
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"model_ids_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                for model_id in model_ids:
                    f.write(f"{model_id}\n")
            
            self.show_success(f"成功导出 {len(model_ids)} 个模型ID到 {filename}")
        except Exception as e:
            self.show_error(f"导出失败: {str(e)}")
    
    def fetch_models_async(self) -> None:
        base_url = self.input_frame.get_url()
        api_key = self.input_frame.get_api_key()
        
        if not base_url:
            self.input_frame.show_validation_error("请输入BaseURL")
            return
        
        if not OpenAIAPIClient.validate_url(base_url):
            self.input_frame.show_validation_error("无效的URL格式，请输入有效的HTTP/HTTPS地址")
            return
        
        self.input_frame.hide_validation_error()
        self.control_frame.set_loading_state(True)
        self.show_status("正在获取模型列表...", "info")
        self.results_frame.clear_models()
        
        def worker():
            try:
                self.api_client = OpenAIAPIClient(base_url, api_key)
                result = self.api_client.fetch_models()
                self.root.after(0, lambda: self._on_fetch_success(result))
            except APIError as e:
                self.root.after(0, lambda: self._on_fetch_error(str(e)))
            except Exception as e:
                self.root.after(0, lambda: self._on_fetch_error(f"未知错误: {str(e)}"))
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def _on_fetch_success(self, result: dict) -> None:
        self.control_frame.set_loading_state(False)
        models = result.get("data", [])
        
        if not models:
            self.show_status("未找到任何模型", "warning")
            return
        
        for model in models:
            model_id = model.get("id", "Unknown")
            self.results_frame.add_model(model_id)
        
        self.show_success(f"成功获取 {len(models)} 个模型")
        base_url = self.input_frame.get_url()
        api_key = self.input_frame.get_api_key()
        self._save_config(base_url, api_key)
    
    def _on_fetch_error(self, error_message: str) -> None:
        self.control_frame.set_loading_state(False)
        self.show_error(error_message)
    
    def show_status(self, message: str, status_type: str = "info") -> None:
        color_map = {
            "info": "white",
            "success": "green",
            "warning": "orange",
            "error": "red"
        }
        color = color_map.get(status_type, "white")
        self.status_label.configure(text=message, text_color=color)
    
    def show_error(self, error_message: str) -> None:
        if "超时" in error_message or "timeout" in error_message.lower():
            guidance = "请检查网络连接和BaseURL是否正确"
        elif "连接错误" in error_message or "connection" in error_message.lower():
            guidance = "请检查网络连接和BaseURL是否可访问"
        elif "401" in error_message:
            guidance = "可能需要API密钥，请检查API文档"
        elif "404" in error_message:
            guidance = "请确认BaseURL是否正确，是否包含正确的版本路径"
        elif "500" in error_message:
            guidance = "服务器出现问题，请稍后重试"
        elif "JSON" in error_message:
            guidance = "服务器返回了无效的响应格式"
        else:
            guidance = "请检查BaseURL和网络连接"
        
        full_message = f"{error_message}\n提示: {guidance}"
        self.show_status(full_message, "error")
    
    def show_success(self, message: str) -> None:
        self.show_status(message, "success")
    
    def _load_saved_config(self) -> None:
        config = self.config_manager.load_config()
        if config.get("base_url"):
            self.input_frame.set_url(config["base_url"])
            if config.get("api_key"):
                self.input_frame.set_api_key(config["api_key"])
            self.show_status(f"已加载保存的配置", "info")
    
    def _save_config(self, url: str, api_key: Optional[str] = None) -> None:
        try:
            self.config_manager.save_config(url, api_key)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def _clear_config(self) -> None:
        try:
            self.config_manager.clear_config()
        except Exception as e:
            print(f"清除配置失败: {e}")
    
    def _on_url_change(self, event) -> None:
        url = self.input_frame.get_url()
        if not url:
            self._clear_config()
    
    def _setup_keyboard_shortcuts(self) -> None:
        self.root.bind("<Return>", lambda e: self._on_fetch_click())
        self.root.bind("<F5>", lambda e: self._on_refresh_click())
    
    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = ModelFetcherApp()
        app.run()
    except KeyboardInterrupt:
        print("\n应用程序被用户中断")
    except Exception as e:
        print(f"应用程序发生错误: {e}")
        import traceback
        traceback.print_exc()
