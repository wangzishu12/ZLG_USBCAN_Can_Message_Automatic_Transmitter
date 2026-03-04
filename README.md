# ZLG_USBCAN_Can_Message_Automatic_Transmitter
调用周立功的CAN盒，可在总线上自动发送excel文件内的can报文，方便测试使用

简要使用说明：
1.配置config.ini
<img width="275" height="320" alt="image" src="https://github.com/user-attachments/assets/e874d506-811a-4dc7-a483-707fe0e48f8d" />
1>devicetype：根据你的ZLG CAN盒型号选择
<img width="870" height="1228" alt="PixPin_2024-04-28_08-35-38" src="https://github.com/user-attachments/assets/7370ee77-819a-42a9-bffb-9ef86140cacd" />
2>deviceindex：配置CAN盒序号，即第几号CAN盒设备，单CAN盒即为0，默认即可，运行软件会要求再次输入
3>canindex：ZLG CAN盒有俩个接口，默认为0
4>baudrate：波特率

2.用ZCANPRO或者CANtest截取报文，保存为xlsx格式文件，命名为“can_data.xlsx”，文件内必须得有“帧ID”和“数据(HEX)”俩列数据，其余无所谓
<img width="1752" height="426" alt="image" src="https://github.com/user-attachments/assets/e33671a1-8f41-4ee7-a37e-9409b65ffb62" />

3.配置发送间隔
在“Read_Excel_And_Send_Massage.py”内配置发送间隔，会周期发送全部ID，红框内参数为一组报文的发送周期，不建议过快，会导致电脑卡顿
<img width="838" height="692" alt="image" src="https://github.com/user-attachments/assets/1326c2cd-c838-4530-ab4b-2df003c1e0f4" />

4.运行软件
运行“main.py”，输入CAN盒的序号即可，单CAN盒输入0
<img width="1180" height="417" alt="image" src="https://github.com/user-attachments/assets/ecffcda1-4984-48f9-ae80-00596a6103b5" />
<img width="633" height="702" alt="image" src="https://github.com/user-attachments/assets/009f67f5-1261-4f8a-9001-4c9657623daa" />
如果你有多个CAN盒，打开ZCANPRO即可观察到总线上的数据是否成功发送：
<img width="938" height="715" alt="image" src="https://github.com/user-attachments/assets/9ec7672f-ea91-4a72-8a19-d810e95dd4fb" />
