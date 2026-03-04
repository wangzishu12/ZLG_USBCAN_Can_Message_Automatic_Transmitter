import pandas as pd
import time
import threading
from collections import defaultdict
import sys

# ================= 配置区域 =================
# 1. 默认的发送间隔 (毫秒)
# 警告：如果ID数量多，设置过小会导致缓冲区溢出丢包
# 建议：20个ID以上时，尝试设置为 20ms 或 50ms
DEFAULT_SEND_INTERVAL_MS = 50

# 2. 自定义ID发送间隔 (毫秒)
# 格式：{ CAN_ID(十进制): 间隔毫秒数 }
CUSTOM_ID_INTERVALS = {
    # 示例: 0x100: 5, 
}

# 3. 高性能模式配置
# 当缓冲区满时，最大等待时间 (秒)。设为 None 表示无限等待直到发出（不丢包但会降频）
BUFFER_FULL_TIMEOUT = None

# 是否启用平滑发送：如果检测到丢包（超时），自动短暂休眠以缓解拥堵
ENABLE_SMOOTHING = True


# ===========================================

def send_command_blocking(can, send_id, data_bytes):
    """
    阻塞式发送：如果缓冲区满，会一直等待直到有空位，确保不丢包
    """
    max_wait_time = BUFFER_FULL_TIMEOUT
    start_wait = time.time()

    while True:
        # 1. 寻找空位
        frame_idx = -1
        # 优化：直接遍历，找到第一个ID为0的
        if hasattr(can, 'sendbuf'):
            for i, frame in enumerate(can.sendbuf):
                if frame.ID == 0x0:
                    frame_idx = i
                    break
        else:
            print("错误: CAN对象没有sendbuf属性")
            return False

        if frame_idx != -1:
            # 找到空位，立即填充并发送
            frame_obj = can.sendbuf[frame_idx]
            frame_obj.ID = send_id
            # 设置扩展帧标志
            if send_id > 0x7FF:
                frame_obj.ExternFlag = True
            else:
                frame_obj.ExternFlag = False

            # 假设 data_bytes 已经是 list of int
            length = len(data_bytes)
            if length == 8:
                # 某些库支持直接setdata(list)
                if hasattr(frame_obj, 'setdata'):
                    frame_obj.setdata(data_bytes)
                else:
                    frame_obj.Data = data_bytes
            else:
                frame_obj.DataLen = length
                # 安全赋值，防止越界
                for k in range(min(length, 8)):
                    frame_obj.Data[k] = data_bytes[k]

            can.transmit()
            return True

        # 2. 缓冲区满了
        if max_wait_time is not None:
            if (time.time() - start_wait) > max_wait_time:
                # 超时，被迫丢包
                return False

        # 让出一点点CPU时间片，让底层驱动有机会把数据发走
        time.sleep(0.0002)  # 0.2ms


class CAN_Scheduler:
    def __init__(self, p_can):
        self.p_can = p_can
        self.running = True
        self.lock = threading.Lock()

        # 【关键修复】恢复 id_data 属性，存储原始数据，防止外部报错
        self.id_data = {}
        # 内部优化：存储预转换的字节列表
        self.id_data_bytes = {}

        self.id_index = defaultdict(int)
        self.id_last_send = defaultdict(float)
        self.id_intervals_sec = {}

        self.buffer_usage = 0
        self.max_buffer_usage = 0

        self.send_thread = threading.Thread(target=self._sending_thread_high_perf, name="_sending_thread")
        self.send_thread.daemon = True
        self.send_thread.start()

        self.buffer_thread = threading.Thread(target=self._buffer_monitor, name="_buffer_monitor")
        self.buffer_thread.daemon = True
        self.buffer_thread.start()

    def add_id_data(self, frame_id, data_list, interval_ms=None):
        """
        添加ID和数据。
        现在同时维护 id_data (原始) 和 id_data_bytes (转换后)，兼容外部访问。
        """
        with self.lock:
            # 1. 保存原始 Hex 字符串列表 (修复 main.py 的 AttributeError)
            self.id_data[frame_id] = data_list

            # 2. 预转换数据为字节列表 (提升发送线程性能)
            processed_data = []
            for d in data_list:
                if isinstance(d, str):
                    processed_data.append(hex_str_to_byte_list(d))
                else:
                    processed_data.append(d)
            self.id_data_bytes[frame_id] = processed_data

            # 3. 重置状态
            self.id_index[frame_id] = 0
            self.id_last_send[frame_id] = 0.0

            # 4. 设置间隔
            interval = interval_ms or CUSTOM_ID_INTERVALS.get(frame_id, DEFAULT_SEND_INTERVAL_MS)
            self.id_intervals_sec[frame_id] = interval / 1000.0

    def _sending_thread_high_perf(self):
        """高性能发送循环 (保持不变)"""
        while self.running:
            loop_start = time.time()
            sent_something = False

            candidates = []
            with self.lock:
                now = loop_start
                for fid, interval in self.id_intervals_sec.items():
                    last = self.id_last_send[fid]
                    if last == 0.0 or (now - last) >= (interval - 0.0005):
                        candidates.append(fid)

            if not candidates:
                time.sleep(0.0005)
                continue

            for fid in candidates:
                with self.lock:
                    # 注意：这里从 id_data_bytes 读取数据进行发送
                    if fid not in self.id_data_bytes:
                        continue

                    data_list = self.id_data_bytes[fid]
                    if not data_list:
                        continue

                    idx = self.id_index[fid]
                    data = data_list[idx]

                    self.id_index[fid] = (idx + 1) % len(data_list)
                    self.id_last_send[fid] = time.time()

                success = send_command_blocking(self.p_can, fid, data)

                if success:
                    sent_something = True
                else:
                    if ENABLE_SMOOTHING:
                        time.sleep(0.002)

            if not sent_something:
                time.sleep(0.0001)

    def _buffer_monitor(self):
        while self.running:
            try:
                if hasattr(self.p_can, 'sendbuf'):
                    used = sum(1 for f in self.p_can.sendbuf if f.ID != 0x0)
                    total = len(self.p_can.sendbuf)
                    self.buffer_usage = used / total if total else 0
                    self.max_buffer_usage = max(self.max_buffer_usage, self.buffer_usage)
                time.sleep(0.05)
            except Exception as e:
                time.sleep(0.1)

    def stop(self):
        self.running = False
        self.send_thread.join(1.0)
        self.buffer_thread.join(0.5)
        print(f"发送线程已停止，最大缓冲区使用率: {self.max_buffer_usage * 100:.1f}%")


# ================= 下面是你询问的完整辅助函数 =================

def read_can_data_from_excel(file_path):
    """
    读取Excel文件中的CAN数据，按帧ID分组存储
    返回格式: { frame_id: [hex_str_1, hex_str_2, ...], ... }
    """
    try:
        # 尝试读取excel，如果报错可能是缺少openpyxl库，请运行: pip install openpyxl
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"读取Excel文件失败: {e}")
        print("提示: 请确保安装了 openpyxl 库 (pip install openpyxl)")
        return {}

    # 检查必要的列是否存在
    required_columns = ['帧ID', '数据(HEX)']
    for col in required_columns:
        if col not in df.columns:
            print(f"Excel文件中缺少必要的列: '{col}'")
            print(f"当前列名: {list(df.columns)}")
            return {}

    # 使用defaultdict创建自动初始化的字典
    id_data_dict = defaultdict(list)

    # 遍历每一行数据
    for index, row in df.iterrows():
        frame_id = row['帧ID']
        hex_data = row['数据(HEX)']

        # 处理帧ID格式
        try:
            if isinstance(frame_id, str):
                frame_id = frame_id.strip()
                if frame_id.startswith('0x') or frame_id.startswith('0X'):
                    frame_id = int(frame_id[2:], 16)
                else:
                    frame_id = int(frame_id)
            elif isinstance(frame_id, int):
                pass
            elif isinstance(frame_id, float):
                # Excel有时会将整数读为浮点数 (如 123.0)
                frame_id = int(frame_id)
            else:
                print(f"跳过无效的帧ID类型: {type(frame_id)}, 值: {frame_id}")
                continue
        except Exception as e:
            print(f"转换帧ID失败: {frame_id}, 错误: {e}")
            continue

        # 添加到对应ID的列表中
        id_data_dict[frame_id].append(hex_data)

    return dict(id_data_dict)


def hex_str_to_byte_list(hex_str):
    """
    将十六进制字符串转换为字节列表
    支持格式: "A1 B2 C3", "A1B2C3", "0xA1 0xB2" 等
    """
    if not isinstance(hex_str, str):
        # 如果已经是列表，尝试转换内部元素
        if isinstance(hex_str, list):
            return [int(x) if isinstance(x, int) else int(x, 16) for x in hex_str]
        return []

    try:
        # 移除空格、0x前缀
        clean_hex = hex_str.replace(" ", "").replace("0x", "").replace("0X", "").strip()

        if len(clean_hex) == 0:
            return []

        if len(clean_hex) % 2 != 0:
            # 奇数位补0
            clean_hex = '0' + clean_hex

        byte_list = []
        for i in range(0, len(clean_hex), 2):
            byte_str = clean_hex[i:i + 2]
            byte_list.append(int(byte_str, 16))

        return byte_list
    except Exception as e:
        print(f"转换十六进制字符串失败: '{hex_str}', 错误: {e}")
        return []


def bytes_to_hex(byte_list):
    """将字节列表转换为十六进制字符串 (用于调试打印)"""
    if not byte_list:
        return ""
    return " ".join(f"{b:02X}" for b in byte_list)


# ================= 使用示例 =================
if __name__ == "__main__":
    print("此模块通常被其他脚本导入使用。")
    print("配置示例:")
    print(f"默认间隔: {DEFAULT_SEND_INTERVAL_MS}ms")
    print(f"自定义间隔配置: {CUSTOM_ID_INTERVALS}")

    # 模拟测试数据转换
    test_hex = "12 34 AB CD"
    print(f"测试转换: '{test_hex}' -> {hex_str_to_byte_list(test_hex)}")