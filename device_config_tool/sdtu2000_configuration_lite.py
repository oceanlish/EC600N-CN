import _thread
import binascii
from ctypes.wintypes import SHORT
import os
import sys
import json
import serial
import socket
import time
import re

try:
    with open(".\\ztesttools_config.json", 'r') as f:
        ztesttools_config = json.load(f)
except Exception as e:
    print('打开配置文件错误,请确认配置文件位置:'.format(e))
    input('发生错误,点击任意键退出!!!')
    sys.exit()

print(ztesttools_config)
# global
COM = ztesttools_config["com"]
BAUD = ztesttools_config["baud"]
DEVID = ztesttools_config["device_id"]
config_flag = 0

try:
    uart = serial.Serial(COM, BAUD, timeout=0.001)
except Exception as e:
    print('开启通讯串口失败,请确认配置文件内COM口参数:'.format(e))
    input('发生错误,点击任意键退出!!!')
    sys.exit()

'''
配置数据组帧
'''
def decheng_msg_build(type, data):
    through_decheng = type
    #decheng透传帧类型
    hex_data = data
    #data 字符串 转 bytes
    conf_device_id = DEVID
    hex_device_id = binascii.unhexlify(conf_device_id)
    #网关设备号 字符串 转 bytes
    hex_data_len = len(data) + 9
    #数据长度 + 其它（帧头 + 网关设备号 + 长度高低八位+帧类型）
    hex_data_len_L8 = hex_data_len&0xFF
    #帧长度 低八位
    hex_data_len_H8 = (hex_data_len>>8)&0xFF
    #帧长度 高八位
    decheng_data_temp = bytes([0x7E]) + hex_device_id + bytes([0x7E]) + bytes([hex_data_len_L8]) + bytes([hex_data_len_H8]) + bytes([through_decheng]) + hex_data
    #打包数据（不含校验和帧尾）
    data_crc_L8 = sum(decheng_data_temp)&0xFF
    #crc 低八位
    decheng_data = decheng_data_temp + bytes([data_crc_L8]) + bytes([0x16])
    #打包数据完成
    print(binascii.hexlify(decheng_data))

    return decheng_data

def uart_recv():
    global  config_flag
    print('creat uart_recv thread')
    while True:
        data = uart.read_all()
        if data != '':
            if len(data) >= 12 and data[0] == 0x7E:
                print(binascii.hexlify(data))
                if data[9] == 0x01:
                    print_success_msg()
                    print("配置成功，即将重启设备")
                    send_con = 0x07
                    send_str = decheng_msg_build(send_con, binascii.unhexlify('{:02X}'.format(1)))
                    uart.write(send_str)
                elif data[9] == 0x00:
                    print_error_msg()

def print_error_msg():
    global  config_flag
    print("配置失败！！！")
    config_flag = 1

def print_success_msg():
    global  config_flag
    print("配置成功！")
    config_flag = 1

if __name__ == '__main__':
    _thread.start_new_thread(uart_recv, ())
    time.sleep(0.1)
    
    '''
    TEST-CONFIG
    '''
    while True:
        print("请选择配置指令：")
        print("【1】 主服务+端口配置")
        print("【2】 从服务+端口配置")
        print("【3】 设备ID号配置")
        print("【4】 心跳间隔配置(min)")
        print("【5】 RS485波特率配置")
        send_flag = 0
        config_flag = 0
        config_type = input('请输入配置信息: ')
        os.system("cls")
        if config_type == '1' or config_type == '2':
            main_server_ip = input("请输入服务ip(示例：223.5.5.232):")
            while True:
                if not re.match(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", main_server_ip):
                    main_server_ip = input("IP地址匹配失败,请重新输入服务ip(示例：223.5.5.232):")
                else:
                    break
            main_server_port = input("请输入服务port(范围：0-65535):")
            while True:
                if not re.match(r"^([0-9]|[1-9]\d{1,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$", main_server_port):
                    main_server_port = input("端口匹配失败,请重新输入服务port(示例：26021):")
                else:
                    break
            
            if config_type == '1':
                send_con = 0x03
            else:
                send_con = 0x04
            ip_hex_data = main_server_ip.split(".")
            
            # IP端口转数据传输
            litte_port = '{:04X}'.format(int(main_server_port))
            ip_hex_data = '{:02X}{:02X}{:02X}{:02X}{}{}'.format(int(ip_hex_data[0]), int(ip_hex_data[1]), int(ip_hex_data[2]), int(ip_hex_data[3]), litte_port[2:], litte_port[:2])

            print(ip_hex_data)
            # 生产发送包
            send_str = decheng_msg_build(send_con, binascii.unhexlify(ip_hex_data))
            send_flag = 1
        
        elif config_type == '3':
            send_con = 0x06
            dev_id = input("请输入设备ID(示例：FF01FF02):")
            while True:
                if not re.match(r"^([0-9A-F]{8})$", dev_id):
                    dev_id = input("设备ID匹配失败,请重新输入(示例：FF01FF02):")
                else:
                    break
            send_str = decheng_msg_build(send_con, binascii.unhexlify(dev_id))
            send_flag = 1

        elif config_type == '4':
            send_con = 0x05
            heart = input("请输入心跳间隔(min)(范围：1-255):")
            while True:
                if not re.match(r"^([1-9]|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])$", heart):
                    heart = input("心跳间隔匹配失败,请重新输入(范围：1-255):")
                else:
                    break
            send_str = decheng_msg_build(send_con, binascii.unhexlify('{:02X}'.format(int(heart))))
            send_flag = 1

        elif config_type == '5':
            send_con = 0x08
            uart_con = input("请输入串口配置(示例+默认：9600-8-n-1):") or "9600-8-n-1"
            while True:
                if not re.match(r"^((1200|2400|4800|9600|14400|19200|38400|57600|115200)-[5-8]-(n|o|e)-[1-2])$", uart_con):
                    uart_con = input("请输入正确的串口配置(示例：9600-8-n-1):") or "9600-8-n-1"
                else:
                    break

            uart_data = uart_con.split("-")
            litte_port = '{:04X}'.format(int(uart_data[0]))
            uart_data = '{}{}{:02X}{:02X}{:02X}'.format(litte_port[2:], litte_port[:2], int(uart_data[1]), ord(uart_data[2]), int(uart_data[3]))
            print(uart_data)
            send_str = decheng_msg_build(send_con, binascii.unhexlify(uart_data))
            send_flag = 1
        else:
            print("未知命令！")

        # 发送测试命令
        if send_flag == 1:
            for i in range(6):
                if config_flag != 0:
                    break
                print("发送第{}次配置命令...".format(i+1))
                uart.write(send_str)
                time.sleep(0.5)
            if i == 5:
                print("配置超时，请检查连接！！！")
            send_flag = 0

        time.sleep(0.1)
    
