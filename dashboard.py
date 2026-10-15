"""本地浏览器总览；Win32 热键仍由 memo.py 管理。"""
from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import base64

import storage

from storage import add_topic, delete_entry, delete_topic, get_topics, load_days, save, set_topic, update_entry

ASSETS = Path(__file__).resolve().parent / "web"
CATEGORIES = ("今日学习", "待补齐")


class Dashboard:
    def __init__(self, root):
        self.root = root
        self.topic_filter = "全部分类"
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(24)
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def respond(self, status, data, content_type="application/json; charset=utf-8"):
                body = (json.dumps(data, ensure_ascii=False).encode("utf-8")
                        if not isinstance(data, bytes) else data)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def route(self):
                path = urlsplit(self.path).path
                prefix = f"/{dashboard.token}"
                if path != prefix and not path.startswith(prefix + "/"):
                    self.respond(404, {"error": "Not found"})
                    return None
                return path[len(prefix):] or "/"

            def do_GET(self):
                route = self.route()
                if route is None:
                    return
                if route.startswith("/images/"):
                    root = storage.ROOT.resolve()
                    path = (root / unquote(route[len("/images/"):])).resolve()
                    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}.get(path.suffix.lower())
                    if not path.is_relative_to(root) or not mime:
                        self.respond(404, {"error": "图片不存在"})
                        return
                    try:
                        self.respond(200, path.read_bytes(), mime)
                    except OSError:
                        self.respond(404, {"error": "图片不存在"})
                    return
                if route == "/api/state":
                    try:
                        with dashboard.lock:
                            data = {"days": load_days(), "topics": get_topics(),
                                    "selectedTopic": dashboard.topic_filter,
                                    "today": date.today().isoformat()}
                        self.respond(200, data)
                    except (OSError, UnicodeError, ValueError) as exc:
                        self.respond(500, {"error": str(exc)})
                    return
                files = {"/": ("index.html", "text/html; charset=utf-8"),
                         "/app.css": ("app.css", "text/css; charset=utf-8"),
                         "/app.js": ("app.js", "text/javascript; charset=utf-8")}
                if route not in files:
                    self.respond(404, {"error": "Not found"})
                    return
                name, mime = files[route]
                try:
                    self.respond(200, (ASSETS / name).read_bytes(), mime)
                except OSError:
                    self.respond(500, {"error": "界面文件无法读取"})

            def do_POST(self):
                route = self.route()
                if route is None:
                    return
                if route not in ("/api/action", "/api/paste-image") or self.headers.get("X-Quick-Note") != dashboard.token:
                    self.respond(404, {"error": "Not found"})
                    return
                origin = self.headers.get("Origin")
                if origin and origin != f"http://127.0.0.1:{dashboard.server.server_port}":
                    self.respond(403, {"error": "Invalid origin"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > (64 * 1024 * 1024 if route == "/api/paste-image" else 1048576):
                        raise ValueError("请求大小无效")
                    if route == "/api/paste-image":
                        encoded_metadata = self.headers.get("X-Quick-Note-Image", "")
                        metadata = json.loads(base64.b64decode(encoded_metadata, validate=True).decode("utf-8"))
                        category, day = metadata.get("category"), metadata.get("day")
                        extension = metadata.get("extension")
                        if category not in CATEGORIES or not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                            raise ValueError("图片保存位置无效")
                        if extension not in (".png", ".bmp"):
                            raise ValueError("不支持的剪贴板图片格式")
                        image = (extension, self.rfile.read(size))
                        if extension == ".png" and not image[1].startswith(b"\x89PNG\r\n\x1a\n"):
                            raise ValueError("剪贴板图片数据无效")
                        with dashboard.lock:
                            path = storage.save_image_file(image, day)
                        relative = path.relative_to(storage.ROOT / day).as_posix()
                        self.respond(200, {"markdown": f"![图片]({relative})"})
                        return
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict):
                        raise ValueError("请求格式无效")
                    action = data.get("action")
                    with dashboard.lock:
                        if action == "selectTopic":
                            name = data.get("topic")
                            if name not in ("全部分类", *get_topics()):
                                raise ValueError("分类不存在")
                            dashboard.topic_filter = name
                            result = True
                        elif action == "addTopic":
                            name = data.get("topic")
                            if not isinstance(name, str):
                                raise ValueError("分类名称无效")
                            result = add_topic(name)
                        elif action == "deleteTopic":
                            name = data.get("topic")
                            if not isinstance(name, str):
                                raise ValueError("分类名称无效")
                            result = delete_topic(name)
                            if result and dashboard.topic_filter == data.get("topic"):
                                dashboard.topic_filter = "全部分类"
                        elif action in ("setTopic", "deleteEntry", "updateEntry"):
                            category, day, index = data.get("category"), data.get("day"), data.get("index")
                            if category not in CATEGORIES or not isinstance(day, str) or date.fromisoformat(day).isoformat() != day or type(index) is not int:
                                raise ValueError("记录位置无效")
                            if action == "updateEntry":
                                result = update_entry(category, day, index, data.get("content"), data.get("original"))
                            else:
                                result = (set_topic(category, day, index, data.get("topic"))
                                          if action == "setTopic" else delete_entry(category, day, index))
                        elif action == "addEntry":
                            category, day = data.get("category"), data.get("day")
                            content, topic = data.get("content"), data.get("topic")
                            if category not in CATEGORIES or not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                                raise ValueError("记录位置无效")
                            if not isinstance(content, str) or not content.strip():
                                raise ValueError("记录内容不能为空")
                            content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
                            if storage.ENTRY.search(content):
                                raise ValueError("正文不能包含记录标题格式（## 日期 时间），请调整该行")
                            if topic not in get_topics():
                                raise ValueError("分类不存在，请刷新后重试")
                            result = save(category, content, topic, day)
                        else:
                            raise ValueError("未知操作")
                    if not result:
                        raise ValueError("操作失败，请刷新后重试")
                    self.respond(200, {"ok": True})
                except (ValueError, TypeError, KeyError) as exc:
                    self.respond(400, {"error": str(exc)})
                except (OSError, UnicodeError) as exc:
                    self.respond(500, {"error": str(exc)})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}/{self.token}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        root.bind("<Destroy>", self._shutdown, add="+")

    def _shutdown(self, event):
        if event.widget is self.root:
            self.server.shutdown()
            self.server.server_close()

    def show(self):
        webbrowser.open(self.url)

    def refresh(self):
        # 浏览器在可见时定时重新读取本地记录。
        pass
