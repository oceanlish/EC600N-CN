import usocket, utime, _thread, ujson, ql_fs, checkNet, modem, ubinascii, sim, net
from machine import UART, Pin
from misc import Power
from usr.sdtu_ota import fota_request
from umqtt import MQTTClient

CONFIG = {
    "config_dir": "/usr",
    "config_path": "/usr/aptu_config.json",
    "backup_path": "/usr/aptu_config.json.bak",
    "config_default_path": "/usr/aptu_config_default.json"
}

class singleton(object):
    _instance_lock = _thread.allocate_lock()

    def __init__(self, *args, **kwargs):
        pass

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance_dict'):
            singleton.instance_dict = {}

        if str(cls) not in singleton.instance_dict.keys():
            with singleton._instance_lock:
                _instance = super().__new__(cls)
                singleton.instance_dict[str(cls)] = _instance

        return singleton.instance_dict[str(cls)]

error_reboot = 0
class led_control(object):
    def __init__(self):
        self.gpio58 = Pin(Pin.GPIO11, Pin.OUT, Pin.PULL_DISABLE, 0)
        self.gpio59 = Pin(Pin.GPIO12, Pin.OUT, Pin.PULL_DISABLE, 0)
        self.gpio60 = Pin(Pin.GPIO13, Pin.OUT, Pin.PULL_DISABLE, 0)
        self.reset_key = Pin(Pin.GPIO14, Pin.IN, Pin.PULL_DISABLE, 0)
    
    def led_shine(self, led, delay_ms):
        global error_reboot
        while True:
            if led == 1:
                led = self.gpio58
            elif led == 2:
                led = self.gpio59
            elif led == 3:
                led = self.gpio60
            led.write(1)
            utime.sleep_ms(delay_ms)
            led.write(0)
            utime.sleep_ms(delay_ms)
            if delay_ms == 200:
                if error_reboot <= 600: # 600 * 200 ms 约120秒后重启
                    error_reboot += 1
                else:
                    #当sim卡，注册异常，重启
                    error_reboot = 0
                    led.write(0)
                    print("------powerRestart------")
                    utime.sleep_ms(1000)
                    Power.powerRestart()

    def led_shine_onece(self, led, delay_ms):
        if led == 1:
            led = self.gpio58
        elif led == 2:
            led = self.gpio59
        elif led == 3:
            led = self.gpio60
        led.write(1)
        utime.sleep_ms(delay_ms)
        led.write(0)
        utime.sleep_ms(delay_ms)
    
    def led_off(self, led):
        if led == 1:
            led = self.gpio58
        elif led == 2:
            led = self.gpio59
        elif led == 3:
            led = self.gpio60
        led.write(0)
    
    def led_on(self, led):
        if led == 1:
            led = self.gpio58
        elif led == 2:
            led = self.gpio59
        elif led == 3:
            led = self.gpio60
        led.write(1)

    def key_state(self):
        key = self.reset_key
        return key.read()

class gc500_modbus(object):
    # modbus CRC-16
    def calc_crc_modbus(self, string_byte):  # 生成CRC
        crc = 0xFFFF
        for pos in string_byte:
            crc ^= pos
            for i in range(8):
                if (crc & 1) != 0:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc
    
    # 垃圾桶状态请求
    def rub_stat_req_msg(self, device_address):
        # 垃圾桶状态请求命令 02 43 01 00 01 44 D8
        data = ubinascii.unhexlify(device_address) + bytes([0x43, 0x01, 0x00, 0x01])
        data_crc = "{:04x}".format(self.calc_crc_modbus(self, data))
        data_msg = data + ubinascii.unhexlify(data_crc)
        return data_msg
 
    # 垃圾桶状态请求---线程
    def uart_stat_req_thread(self, req_check_time, device_address):
        while True:
            try:
                data = self.rub_stat_req_msg(self, device_address)
                print("uart send stat req: [{}]:".format(req_check_time), ubinascii.hexlify(data))
                aptu_cls.uart.write(data)
            except Exception as e:
                print("aptu_cls.uart in stat_req_thread error!!!: ", e)
            else:
                utime.sleep(req_check_time)
            utime.sleep_ms(10)

    # 垃圾桶状态上报
    def rub_stat_send_server_msg(self, imei, door1, door2, fumes, overflow):
        data = {
            "method": "thing.event.property.post",
            "id": "0",
            "version": "1.0.0",
            "params":{
                "type": 4,
                "info": [{
                            "sn": imei,
                            "door1": door1,
                            "door2": door2,
                            "fumes": fumes,
                            "overflow": overflow
                        }]
            }
        }
        return ujson.dumps(data)

    # gc500数据接收解析
    def uart_parse(self, imei, device_address, recv_data, overflow_limit, overflow_num):
        # overflow_limit = aptu_cls.config["DeviceInfo"]["overflowLimit"]
        # overflow_num = aptu_cls.config["DeviceInfo"]["overflowNumber"]
        if len(recv_data) >= 18 and recv_data[0] == int(device_address): #判定数据帧至少18bytes
            if recv_data[1] == 0x43: #接收到控制板状态回复帧
                print('recv 0x43 data:', recv_data)
                #门判定
                if recv_data[5] == 0x10:
                    door1 = 0 # 关门
                elif recv_data[5] == 0x11:
                    door1 = 1 # 开门
                if recv_data[6] == 0x10:
                    door2 = 0
                elif recv_data[6] == 0x11:
                    door2 = 1
                #烟雾判定
                if recv_data[7] == 0x10:
                    fumes = 0
                elif recv_data[7] == 0x11:
                    fumes = 1
                #满溢判定
                overflow_data1 = recv_data[8] + (recv_data[9] << 8)
                overflow_data2 = recv_data[10] + (recv_data[11] << 8)
                overflow_data3 = recv_data[12] + (recv_data[13] << 8)
                overflow_data4 = recv_data[14] + (recv_data[15] << 8)
                print("满溢参数: {},{},{},{}".format(overflow_data1, overflow_data2, overflow_data3, overflow_data4))
                if overflow_num == 4 \
                   and (overflow_data1 <= overflow_limit) \
                   and (overflow_data2 <= overflow_limit) \
                   and (overflow_data3 <= overflow_limit) \
                   and (overflow_data4 <= overflow_limit) :
                    overflow = 1
                elif overflow_num == 3 \
                   and (overflow_data1 <= overflow_limit) \
                   and (overflow_data2 <= overflow_limit) \
                   and (overflow_data3 <= overflow_limit) :
                    overflow = 1
                elif overflow_num == 2 \
                   and (overflow_data1 <= overflow_limit) \
                   and (overflow_data2 <= overflow_limit) :
                    overflow = 1
                elif overflow_num == 1 \
                   and (overflow_data1 <= overflow_limit) :
                    overflow = 1
                else:
                    overflow = 0
                return self.rub_stat_send_server_msg(self, imei, door1, door2, fumes, overflow)

            else:
                print('recv no 0x43 data:', recv_data)
                return False
        else:
            print('recv unknow data:', recv_data)
            return False
            

class aptu_cls(singleton):
    config_file = "/usr/aptu_config.json"

    daemon_sem = None
    uart_inited = 0
    event_noted = 0

    class Error(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    class ErrCode(object):
        NOTA = 1
        OK = 0
        ECONF = -1
        ENET = -2
        ESOCKBUILD = -3
        ESOCKOPT = -4
        ESOCKCONN = -5
        EDNS = -6
        EUART = -7
        ESYS = -8
        EALIYUNBUILD = -9
        EALIYUNOPT = -10
        EALIYUNCONN = -11
        ESTOPRUN = -128

    error_map = {
        ErrCode.NOTA: 'OTA plain comes',
        ErrCode.OK: 'OK',
        ErrCode.ECONF: 'config error',
        ErrCode.ENET: 'net error',
        ErrCode.ESOCKBUILD: 'socket create error',
        ErrCode.ESOCKOPT: 'socket option set error',
        ErrCode.ESOCKCONN: 'socket connect error',
        ErrCode.EDNS: 'DNS error',
        ErrCode.EUART: 'UART error',
        ErrCode.ESYS: 'sys error',
        ErrCode.ESTOPRUN: 'stop running',
        ErrCode.EALIYUNBUILD: 'aliyun create error',
        ErrCode.EALIYUNOPT: 'aliyun option error',
        ErrCode.EALIYUNCONN: 'aliyun connect error',
    }

    @classmethod
    def __notification_send(cls, err_code, data={}):
        if (not cls.uart_inited) or cls.event_noted:
            return
        if not isinstance(data, dict):
            return
        if err_code not in cls.error_map:
            return

        cls.event_noted = 1

        result = dict()
        result['code'] = err_code
        result['desc'] = cls.error_map[err_code]

        notification = dict()
        notification['result'] = result
        if data:
            notification['data'] = data

        cls.uart.write(ujson.dumps(notification))

    @classmethod
    def __exception_handler(cls, err_str):
        print('event_noted', cls.event_noted, err_str)
        for k, v in cls.error_map.items():
            if v == err_str:
                cls.__notification_send(k)
                if not k == cls.error_map[cls.ErrCode.ESOCKCONN]:
                    raise cls.Error(cls.error_map[cls.ErrCode.ESTOPRUN])
                break

    @classmethod
    def __read_config(cls):
        if ql_fs.path_exists(cls.config_file):
            try:
                with open(cls.config_file, 'r', encoding='utf-8') as f:
                    return ujson.load(f)
            except:
                raise cls.Error(cls.error_map[cls.ErrCode.ECONF])

            print('config loading ...')
        else:
            raise cls.Error(cls.error_map[cls.ErrCode.ECONF])

    @classmethod
    def __server_filter(cls):
        if 'serverProtocol' in cls.config['Transaction']:
            transaction = cls.config['Transaction']['serverProtocol']
        else:
            transaction = None
        if transaction:
            server_list = [x for x in cls.config['Server'] if x['protocol'] == transaction]
            server = server_list[0] if server_list else cls.config['Server'][0]
        else:
            server = cls.config['Server'][0]
        return server

    @classmethod
    def __check_necessary_config(cls):
        if ('UART' in cls.config) and ('Server' in cls.config):
            if ('No' not in cls.config['UART']) or ('baudRate' not in cls.config['UART']):
                raise cls.Error(cls.error_map[cls.ErrCode.ECONF])
            for config in cls.config['Server']:
                if config['protocol'].lower() == "ALIYUN".lower():
                    if ('deviceInfo' not in config) or ('topic' not in config):
                        raise cls.Error(cls.error_map[cls.ErrCode.ECONF])
                else:
                    if ('domain' not in config) or ('port' not in config):
                        raise cls.Error(cls.error_map[cls.ErrCode.ECONF])
        else:
            raise cls.Error(cls.error_map[cls.ErrCode.ECONF])

    @classmethod
    def __uart_init(cls):
        cls.uart_inited = 0

        uart_no = cls.config['UART']['No']
        if uart_no == 0:
            UARTn = UART.UART0
        elif uart_no == 1:
            UARTn = UART.UART1
        elif uart_no == 2:
            UARTn = UART.UART2
        elif uart_no == 3:
            UARTn = UART.UART3
        else:
            raise cls.Error(cls.error_map[cls.ErrCode.ECONF])

        uart_baudRate = cls.config['UART']['baudRate']

        if 'dataBitsLen' in cls.config['UART']:
            uart_dataBitsLen = cls.config['UART']['dataBitsLen']
        else:
            uart_dataBitsLen = 8

        if 'parity' in cls.config['UART']:
            uart_parity = cls.config['UART']['parity']
        else:
            uart_parity = 'None'
        if uart_parity.lower() == 'None'.lower():
            uart_parity = 0
        elif uart_parity.lower() == 'Even'.lower():
            uart_parity = 1
        elif uart_parity.lower() == 'Odd'.lower():
            uart_parity = 2
        else:
            raise cls.Error(cls.error_map[cls.ErrCode.ECONF])

        if 'stopBitsLen' in cls.config['UART']:
            uart_stopBitsLen = cls.config['UART']['stopBitsLen']
        else:
            uart_stopBitsLen = 1

        if 'flowCtrl' in cls.config['UART']:
            uart_flowCtrl = cls.config['UART']['flowCtrl']
        else:
            uart_flowCtrl = 'disable'
        if uart_flowCtrl.lower() == 'enable'.lower():
            uart_flowCtrl = 1
        else:
            uart_flowCtrl = 0

        try:
            print("UART init parameters:", UARTn, uart_baudRate, uart_dataBitsLen, uart_parity, uart_stopBitsLen,
                  uart_flowCtrl)
            cls.uart = UART(UARTn, uart_baudRate, uart_dataBitsLen, uart_parity, uart_stopBitsLen, uart_flowCtrl)
            cls.uart_inited = 1
        except:
            raise cls.Error(cls.error_map[cls.ErrCode.EUART])

        print('UART init done')

    @classmethod
    def __data_call_check(cls):
        checknet = checkNet.CheckNetwork(cls.PROJECT_NAME, cls.PROJECT_VERSION)
        gpio_d = led_control()
        
        if ('Network' in cls.config) and ('timeWaitForOK' in cls.config['Network']):
            timeWaitForOK = cls.config['Network']['timeWaitForOK']
        else:
            timeWaitForOK = 30
        stagecode, subcode = checknet.wait_network_connected(timeWaitForOK)
        if stagecode == 3 and subcode == 1:
            net_stat_thread_id = _thread.start_new_thread(gpio_d.led_shine, (2, 1000,))
            ota_thread_id = _thread.start_new_thread(cls.__fota_check, (cls.PROJECT_VERSION, modem.getDevImei(), sim.getIccid(), cls.PROJECT_NAME))
            stat_thread_id = _thread.start_new_thread(gc500_modbus.uart_stat_req_thread, (gc500_modbus, cls.config['DeviceInfo']['checkTime'], cls.config['DeviceInfo']['deviceId']))
            print("start thread...")
            checknet.poweron_print_once()
        elif stagecode == 3:
            if subcode == 0:
                err_msg = '当前已经拨号过了,请确认是否关闭了开机自动拨号或者是首次调用该接口等'
                print(err_msg)
                gpio_d.led_shine(1, 200)
            else:
                print('已经尝试了所有的apn,都拨号失败')
                gpio_d.led_shine(1, 200)
            
            raise cls.Error(cls.error_map[cls.ErrCode.ENET])
        elif stagecode == 1:
            if subcode == 0:
                err_msg = '请确认是否插入SIM卡,或者卡槽是否松动'
                print(err_msg)
                gpio_d.led_shine(2, 200)
            else:
                print('SIM 卡状态异常(状态值：{}),请确认是否欠费等'.format(subcode))
                gpio_d.led_shine(2, 200)
            
            raise cls.Error(cls.error_map[cls.ErrCode.ENET])
        else:
            if subcode == -1:
                print('获取注网状态失败了')
                gpio_d.led_shine(3, 200)
            else:
                print('设备注网异常,注网状态值：{}'.format(subcode))
                gpio_d.led_shine(3, 200)

            raise cls.Error(cls.error_map[cls.ErrCode.ENET])
        print('datacall done')

    '''
    FOTA 升级线程
    '''
    @classmethod
    def __fota_check(cls, version, imei, iccid, module_type):
        print('creat fota_check thread')
        if ('DeviceInfo' in cls.config) and ('OTA' in cls.config):
            if 'host' in cls.config['DeviceInfo']:
                host = cls.config['DeviceInfo']['host']
            else:
                print("config error: havet host config")
            check_time = cls.config['OTA']['checkTime']
        else:
            print("config error: havet DeviceInfo config")
        
        deviceid = cls.config['DeviceInfo']['deviceId']
        
        retry_times = 0
        while True:
            try:
                if retry_times <= 4:
                    try:
                        fota_request(host, version, imei, iccid, module_type, net.csqQueryPoll(), deviceid)
                    except Exception as e:
                        print("httpDownload error: {}".format(e, retry_times))
                        retry_times = retry_times + 1 # 累计失败次数
                        continue
                    else:
                        retry_times = 99 # 可以通过的情况下下次不再进入try:
                else:
                    retry_times = 0
                    utime.sleep(check_time)
            except Exception as e:
                print("get sock noemal error: {}".format(e, retry_times))
                continue
            utime.sleep(5)

    @staticmethod
    def __daemon_thread(argv):
        cls = argv
        error_exit_flag = 0
        error_exit_time = utime.time()
        if cls.config['Transaction']['serverProtocol'].lower() == "MQTT".lower():
            run_cls = mqtt_client
        # else:
        #     run_cls = aptu_client
        # 复位按键监听
        run_cls.restart_config_start(mqtt_client)
        while True:
            if error_exit_flag >= 10:
                print("will reboot")
                error_exit_flag = 0
                Power.powerRestart()
            elif (utime.time() - error_exit_time) > 60: # 累计指定秒内只能触发一次flag增加
                error_exit_time = utime.time()
                error_exit_flag += 1
            try:
                aptu_cli = run_cls()
                aptu_cli.server_connect()
                aptu_cli.transaction_start()
            except Exception as e:
                cls.__exception_handler(e.args[0])
                continue
            cls.daemon_sem.acquire()
            aptu_cli.transaction_stop()
            utime.sleep_ms(20)

    @classmethod
    def start(cls):
        try:
            cls.daemon_sem = _thread.allocate_lock()
            cls.daemon_sem.acquire()
            _thread.start_new_thread(cls.__daemon_thread, (cls,))
        except:
            raise cls.Error(cls.error_map[cls.ErrCode.ESYS])

    @classmethod
    def __init__(cls, projectName="SDTU2100-YN", projectVersion="V2.2.3"):
        try:
            cls.PROJECT_NAME = projectName
            cls.PROJECT_VERSION = projectVersion
            cls.config = cls.__read_config()
            cls.server = cls.__server_filter()
            cls.__check_necessary_config()
            cls.__uart_init()
            cls.__data_call_check()
        except Exception as e:
            cls.__exception_handler(e.args[0])
            raise

class mqtt_client(aptu_cls):
    def __callback(self, topic, msg):
        try:
            print('CallBack Msg >>>> ', topic, msg)
        except:
            print('down transaction thread exit ...')

    def server_connect(self, err_callback=None):
        if 'protocol' not in self.server or self.server['protocol'].lower() != 'MQTT'.lower():
            self.Error(self.error_map[self.ErrCode.ECONF])
        print("connecting to MQTT server...")
        try:
            self.umqtt_conn = self._mqtt_connect()
            print("set mqtt config...")
        except Exception as e:
            raise self.Error(self.error_map[self.ErrCode.EALIYUNBUILD])
        try:
            self.umqtt_conn.set_callback(self.__callback)
            print("set callback...")
            if err_callback:
                self.umqtt_conn.error_register_cb(err_callback)
        except:
            raise self.Error(self.error_map[self.ErrCode.EALIYUNOPT])
        try:
            self.subscribe = "/sys/" + self.server['deviceInfo']['productKey'] + "/" + modem.getDevImei() +"/thing/service/property/set"
            self.publish = "/sys/" + self.server['deviceInfo']['productKey'] + "/" + modem.getDevImei() +"/thing/event/property/post"

            print("publish : ",self.publish)
            print("subscribe : ",self.subscribe)
            if 'qos' in self.server:
                self.qos_subscribe = self.server['qos'].get("subscribe", 0)
                self.qos_publish = self.server['qos'].get("publish", 0)
            else:
                self.qos_subscribe = 0
                self.qos_publish = 0
            print("set subscribe and publish")
        except:
            raise self.Error(self.error_map[self.ErrCode.EALIYUNOPT])
        try:
            self.umqtt_conn.connect()
            print("mqtt connect success")
        except:
            raise self.Error(self.error_map[self.ErrCode.EALIYUNCONN])
        print("MQTT server connect succeed")

    def _mqtt_connect(self):
        client_id = modem.getDevImei()
        server = self.server['domain']
        port = self.server['port']
        user=None
        password=None
        keepalive = self.server['parameters']['keepAlive']
        return MQTTClient(client_id, server, port, user, password, keepalive, ssl=False, ssl_params={},reconn=True,version=4)

    def restart_config_start(self):
        try:
            self.reset_config_thread = _thread.start_new_thread(self.__reset_config_thread, (1, 10))
        except:
            raise self.Error(self.error_map[self.ErrCode.ESYS])

    @staticmethod
    def __reset_config_thread(stats, daley):  #恢复出厂设置
        key_restart = led_control()
        while stats:
            utime.sleep_ms(20)
            key_stats = key_restart.key_state()
            if key_stats==0:
                counter=0
                utime.sleep_ms(daley) 
                if(key_stats==0):
                    while(key_stats==0):
                        counter+=1
                        utime.sleep_ms(daley) 
                        if(counter>1000):
                            #长按10s 回复配置文件
                            mqtt_client.reset_json_data()
                            print("start powerRestart")
                            counter=0
                            Power.powerRestart()
                        elif(key_restart.key_state()==1):
                            counter=0
                            #按键松开 标志归零
                            break

    @staticmethod
    def __up_transaction_thread(argv):
        self = argv
        note_data = dict()
        note_data['IMEI'] = modem.getDevImei()
        note_data['SN'] = modem.getDevSN()
        self.__notification_send(self.ErrCode.OK, note_data)
        self.uart.write(ujson.dumps(note_data))

        imei = modem.getDevImei()
        device_address = self.config['DeviceInfo']['deviceId']
        overflow_limit = self.config['DeviceInfo']['overflowLimit']
        overflow_num = self.config['DeviceInfo']['overflowNumber']
        check_updata_time = self.config['DeviceInfo']['checkUpdataTime']

        print('mqtt up transaction thread working ...')

        send_time = utime.time()

        while True:
            try:
                data_len = self.uart.any()
                if data_len:
                    data = self.uart.read(data_len)
                    print('uart recv data: [{}]:'.format(data_len), data)
                    recv = gc500_modbus.uart_parse(gc500_modbus, imei, device_address, data, overflow_limit, overflow_num)
                    print("recv : ", recv)
                    print("self.publish [{}]:".format(self.qos_publish), self.publish)
                    if recv and (utime.time() - send_time >= check_updata_time):
                        send_time = utime.time()
                        self.umqtt_conn.publish(self.publish, recv, self.qos_publish)
                    else :
                        print("uart check failed: __up_transaction_thread")
                else:
                    utime.sleep_ms(1)
            except Exception as e:
                print(e)
                print('up transaction thread exit ...')
                self.sock_lock.acquire()
                conn_status = self.umqtt_conn.get_mqttsta()
                if conn_status in [-1, 2]:
                    print('will reconnect to server ...')
                    self.umqtt_conn.disconnect()
                    self.daemon_sem.release()
                self.sock_lock.release()
                break

    @staticmethod
    def __down_transaction_thread(argv):
        self = argv
        self.umqtt_conn.subscribe(self.subscribe, self.qos_subscribe)
        while True:
            data = self.umqtt_conn.wait_msg()
            print("data : ",data)

    def transaction_start(self):
        try:
            self.sock_lock = _thread.allocate_lock()
        except:
            raise self.Error(self.error_map[self.ErrCode.ESYS])

        try:
            self.up_transaction_thread = _thread.start_new_thread(self.__up_transaction_thread, (self,))
        except:
            raise self.Error(self.error_map[self.ErrCode.ESYS])

        try:
            self.down_transaction_thread = _thread.start_new_thread(self.__down_transaction_thread, (self,))
        except:
            raise self.Error(self.error_map[self.ErrCode.ESYS])

    def transaction_stop(self):
        try:
            _thread.stop_thread(self.up_transaction_thread)
            _thread.stop_thread(self.down_transaction_thread)
        except:
            pass

if __name__ == '__main__':
    aptu = aptu_cls()
    aptu.start()