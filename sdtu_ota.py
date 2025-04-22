import log
import utime
import ujson, request
import fota, app_fota
from misc import Power

# 设置日志输出级别
log.basicConfig(level=log.INFO)
zxin_log = log.getLogger("ZXIN-SDTU")

def result(args):
    print('download status:',args[0],'download process:',args[1])
    if args[0] == -1:
        zxin_log.error("httpDownload error")
    elif args[0] == 0:
        zxin_log.info("wait httpDownload update...")

'''
FOTA请求
'''
def fota_request(host, version, imei, iccid, module_type, csq, deviceid):
    # 获取access token
    access_token = module_type
    print("access_token:", access_token)

    # 升级包下载地址的请求
    download_url = host + "/api/v2/fota/fw"
    headers = {"access_token": access_token, "Content-Type": "application/json"}
    acquire_data = {
        "version": version,
        "imei": imei,
        "iccid": iccid,
        "moduleType": module_type,
        "csq": csq,
        "deviceid": deviceid
    }
    resp = request.post(download_url, data=ujson.dumps(acquire_data), headers=headers)
    json_data = ""
    for i in resp.content:
        json_data += i.decode()
    json_data = ujson.loads(json_data)
    if json_data["code"] == 200:
        targetVersion = json_data["targetVersion"]
        update_mode = json_data["upMode"]
        url_zip = json_data["url"]
        fileMd5 = json_data["fileMd5"]
        action = json_data["action"]
        
        print("fileMD5: ", fileMd5)
        print("targetVersion: ", targetVersion)
    else:
        action = json_data["action"]
        msg = json_data["msg"]
        code = json_data["code"]
        zxin_log.info(msg)

    if action:
        print("Please do not send instructions during the upgrade...")
        if update_mode == 'app':
            # 替换py文件模式
            fota_obj = app_fota.new()
            res = fota_obj.bulk_download(info=url_zip)
            if res != None:
                print("update download error .... : %s" % res)
            else:
                print("update download success.... : %s" % res)
                fota_obj.set_update_flag()
                utime.sleep(1)
                Power.powerRestart()  # 重启模块
        elif update_mode == 'bin':
            # fota模式
            try:
                r = request.get(url_zip, sizeof=4096)
            except Exception as e:
                zxin_log.error("http get error")
                return -1
            if r.status_code == 200 or r.status_code == 206:
                file_size = int(r.headers['Content-Length'])
                fota_obj = fota()
                count = 0
                try:
                    while True:
                        c = next(r.content)
                        length = len(c)
                        for i in range(0, length, 4096):
                            count += len(c[i:i + 4096])
                            fota_obj.write(c[i:i + 4096], file_size)
                except StopIteration:
                    r.close()
                except Exception as e:
                    r.close()
                    zxin_log.error("fota write error")
                    return -1
                else:
                    r.close()
                res = fota_obj.verify()
                if res != 0:
                    zxin_log.error("fota verify error")
                    return -1
                zxin_log.info("power_reset...")
                utime.sleep(2)
                Power.powerRestart()   # 重启模块
                return 0
            else:
                return -1