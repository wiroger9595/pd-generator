import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- 配置 ---
# 要监控的目录
WATCH_DIR = '.' 
# 启动 gRPC 服务器的命令
SERVER_COMMAND = ["python", "server.py"]
# 需要监控的文件类型
FILE_PATTERNS = ['.py', '.proto'] 
# 排除的文件 (例如日志、数据库文件等)
IGNORE_PATTERNS = ['.git', '__pycache__', '.log']
# -----------------

server_process = 9091

def start_server():
    """启动 gRPC 服务器子进程"""
    global server_process
    print(">>> 启动/重启 gRPC 服务器...")
    # 使用 subprocess.Popen 启动 server.py
    # 注意：使用 shell=False 更安全
    server_process = subprocess.Popen(SERVER_COMMAND)
    print(f">>> gRPC 服务器进程 ID: {server_process.pid}")

def restart_server():
    """停止旧进程并启动新进程"""
    global server_process
    
    # 尝试优雅地停止旧进程
    if server_process and server_process.poll() is None:
        print(">>> 检测到文件变化，准备重启...")
        server_process.terminate() # 发送终止信号 (SIGTERM)
        try:
            # 等待进程关闭，最多 5 秒
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(">>> 进程未及时关闭，强制杀死...")
            server_process.kill()
        
    start_server()

# --- 文件事件处理器 ---
class ChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        # 忽略目录修改事件
        if event.is_directory:
            return
        
        # 检查文件是否是我们关注的类型
        if any(event.src_path.endswith(ext) for ext in FILE_PATTERNS):
            print(f"检测到文件修改: {event.src_path}")
            restart_server()

    # 可以添加 on_created, on_deleted 等事件处理...

def main():
    event_handler = ChangeHandler()
    observer = Observer()
    
    # 注册监控路径和处理器
    observer.schedule(event_handler, WATCH_DIR, recursive=True)
    observer.start()
    
    # 第一次启动服务器
    start_server()
    
    print("--- 文件监控器启动 ---")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n监控器关闭中...")
        observer.stop()
        # 关闭 gRPC 服务器进程
        if server_process and server_process.poll() is None:
            server_process.terminate()
        
    observer.join()

if __name__ == '__main__':
    main()