# Pin使用示例

from machine import Pin
import utime


'''
下面两个全局变量是必须有的，用户可以根据自己的实际项目修改下面两个全局变量的值
'''
PROJECT_NAME = "QuecPython_Pin_example"
PROJECT_VERSION = "1.0.0"


'''
GPIO介绍：https://python.quectel.com/wiki/#/zh-cn/api/QuecPythonClasslib?id=pin
'''
gpio58 = Pin(Pin.GPIO11, Pin.OUT, Pin.PULL_DISABLE, 0)
gpio59 = Pin(Pin.GPIO12, Pin.OUT, Pin.PULL_DISABLE, 0)
gpio60 = Pin(Pin.GPIO13, Pin.OUT, Pin.PULL_DISABLE, 0)


gpio61 = Pin(Pin.GPIO14, Pin.IN, Pin.PULL_DISABLE, 0)

if __name__ == '__main__':
    while True:
#        gpio58.write(1) # 设置 gpio1 输出高电平
        val = gpio58.read() # 获取 gpio1 的当前高低状态
        print('val58 = {}'.format(val))
#        gpio59.write(1) # 设置 gpio1 输出高电平
        val = gpio59.read() # 获取 gpio1 的当前高低状态
        print('gpio59 = {}'.format(val))
        gpio60.write(1) # 设置 gpio1 输出高电平
        val = gpio60.read() # 获取 gpio1 的当前高低状态
        print('gpio60 = {}'.format(val))

        utime.sleep(1)
#        gpio58.write(0) # 设置 gpio1 输出高电平
        val = gpio58.read() # 获取 gpio1 的当前高低状态
        print('val59 = {}'.format(val))

#        gpio59.write(0) # 设置 gpio1 输出高电平
        val = gpio59.read() # 获取 gpio1 的当前高低状态
        print('gpio59 = {}'.format(val))

        gpio60.write(0) # 设置 gpio1 输出高电平
        val = gpio60.read() # 获取 gpio1 的当前高低状态
        print('gpio60 = {}'.format(val))

        val = gpio61.read() # 获取 gpio1 的当前高低状态
        print('gpio61 reset = {}'.format(val))
        
        utime.sleep(1)


