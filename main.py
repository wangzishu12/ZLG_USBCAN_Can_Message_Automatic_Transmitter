import threading

from Read_Excel_And_Send_Massage import read_can_data_from_excel, hex_str_to_byte_list, CAN_Scheduler, \
    DEFAULT_SEND_INTERVAL_MS
from Storage import *
import msvcrt
import configparser
from ControlCAN import *


########################################################################################################################
def CAN_init():
    cf = configparser.ConfigParser()
    #从config读取CAN参数
    cf.read('./config.ini')
    can_devtype = cf.getint("can", "devicetype")
    can_devindex = cf.getint("can", "deviceindex")
    can_canindex = cf.getint("can", "canindex")
    can_baudrate = cf.getint("can", "baudrate")
    can_acccode = int(cf.get("can", "acceptcode"), 16)
    can_accmask = int(cf.get("can", "acceptmask"), 16)
    # db_ip = cf.get("db", "ip")
    # db_user = cf.get("db", "username")
    # db_pass = cf.get("db", "password")
    # db_schema = cf.get("db", "schema")
    # db_rtable = cf.get("db", "rawtable")
    # db_ttable = cf.get("db", "turetable")
    # db_buffersize = cf.getint("db", "buffersize")
    print('读取配置成功')

    # sql = StorageToSQL(db_ip, db_user, db_pass, db_schema, db_rtable, db_ttable, db_buffersize)
    # sql.createtable()
    can_devindex = int(input("请输入CAN设备的ID："))
    p_can = ControlCAN(can_devtype, can_devindex, can_canindex, can_baudrate, can_acccode, can_accmask)
    p_can.opendevice()
    p_can.initcan()
    p_can.startcan()

        # sql.copy(can.receivebuf, can.receivenum, can.timeinterval)
        # sql.storage()
        # sql.commit()
    # del sql

    return p_can
########################################################################################################################

def main():
    # 1. 初始化CAN控制器 - 使用外部CAN_init()函数
    print("初始化CAN控制器...")
    can_handle = CAN_init()  # 外部CAN初始化函数

    # 2. 读取Excel文件
    excel_file = "can_data.xlsx"  # 替换为您的Excel文件路径
    print(f"读取Excel文件: {excel_file}")
    id_hex_dict = read_can_data_from_excel(excel_file)

    if not id_hex_dict:
        print("没有读取到有效数据，程序退出")
        return

    print(f"成功读取 {len(id_hex_dict)} 个不同的CAN ID")

    # 3. 转换数据格式
    id_data_dict = {}
    for frame_id, hex_list in id_hex_dict.items():
        data_list = [hex_str_to_byte_list(hex_str) for hex_str in hex_list]
        # 过滤空数据
        valid_data = [data for data in data_list if data]
        if valid_data:
            id_data_dict[frame_id] = valid_data
            print(f"ID 0x{frame_id:04X}: {len(valid_data)} 条消息")

    if not id_data_dict:
        print("没有有效的CAN数据，程序退出")
        return

    # 4. 创建调度器并传入can_handle
    print("创建CAN调度器...")
    scheduler = CAN_Scheduler(can_handle)  # 传入外部初始化的can_handle

    # 5. 添加所有ID数据
    for frame_id, data_list in id_data_dict.items():
        scheduler.add_id_data(frame_id, data_list)

    # 打印信息方便调试
    cf = configparser.ConfigParser()
    cf.read('./config.ini')
    can_baudrate = cf.getint("can", "baudrate")
    print(f"相同ID间隔: {DEFAULT_SEND_INTERVAL_MS}ms | 不同ID间隔: ~1ms | 波特率: {can_baudrate}")

    # 6. 主循环
    try:
        while True:
            time.sleep(5)
            # 显示状态信息
            with scheduler.lock:
                active_ids = len(scheduler.id_data)
                total_msgs = sum(len(data) for data in scheduler.id_data.values())
                print(
                    f"运行中... 活动ID: {active_ids}, 总消息: {total_msgs}, 缓冲区使用: {scheduler.buffer_usage * 100:.1f}%")
    except KeyboardInterrupt:
        print("\n收到中断信号，停止发送...")
        scheduler.stop()
        print("程序已退出")


if __name__ == "__main__":
    main()