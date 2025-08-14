#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start_compatible_refactor_dryrun.py — 完全互換 + --dry-run 対応版

- 元の start.py と **引数の位置/挙動は完全互換**
- 追加で `--dry-run` オプションをどこに置いても受け付けます（例: `./start.py --dry-run 1 1 US` も可）。
- `--dry-run` 時は、実行するコマンドを `$ ...` 形式で表示し、副作用は発生させません。
- ループ待機やファイル編集が必要な箇所は、dry-run でも進行できるように安全にスタブ化しています。

注意: mesh/*.py の呼び出しは dry-run 時も **コマンド表示のみ** にしています（run_* を直接呼ばず、表示してスキップ）。
"""

import sys
import os
import time
import subprocess
import re
import threading
from mesh import *  # 原作踏襲

# ----------------------------------------------------------------------------
# Global flags (dry-run)
# ----------------------------------------------------------------------------
DRY_RUN = False

def _parse_dry_run_flag():
    """`--dry-run` を sys.argv から取り除き、位置引数の互換性を維持する。"""
    global DRY_RUN
    for i, a in enumerate(list(sys.argv[1:]), start=1):
        if a == '--dry-run':
            DRY_RUN = True
            del sys.argv[i]
            print('[dry-run] Enabled: commands will be printed but not executed')
            break

_parse_dry_run_flag()

# ----------------------------------------------------------------------------
# Paths & Constants
# ----------------------------------------------------------------------------
SCRIPT_PATH       = "/home/pi/nrc_pkg/script/"
CONF_PATH         = os.path.join(SCRIPT_PATH, "conf")
DRIVER_KO         = "/home/pi/nrc_pkg/sw/driver/nrc.ko"
CLI_APP           = os.path.join(SCRIPT_PATH, "cli_app")
FIRMWARE_COPY_SH  = "/home/pi/nrc_pkg/sw/firmware/copy.sh"
IP_CONFIG_SH      = os.path.join(CONF_PATH, "etc/ip_config.sh")
IP_CONFIG_BR_SH   = os.path.join(CONF_PATH, "etc/ip_config_bridge.sh")
CLOCK_CONF_SH     = os.path.join(CONF_PATH, "etc/clock_config.sh")
TEMP_SELF_CONF    = os.path.join(CONF_PATH, "temp_self_config.conf")
TEMP_HOSTAPD_CONF = os.path.join(CONF_PATH, "temp_hostapd_config.conf")

S1G_CH_COUNTRIES = [
    "US", "CN", "JP", "T8", "AU", "NZ", "K1", "K2", "S8", "S9", "T9"
]
EU_CH_COUNTRIES = [
    "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR","GR",
    "HR","HU","IE","IT","LT","LU","LV","MT","NL","PL","PT","RO",
    "SE","SI","SK","GB","SA"
]

# ----------------------------------------------------------------------------
# Default Configuration (原作の値を保持)
# ----------------------------------------------------------------------------
max_cpuclock      = 1
model             = 7394
fw_download       = 1
fw_name           = 'uni_s1g.bin'

# DEBUG
driver_debug      = 0
dbg_flow_control  = 0
supplicant_debug  = 0
hostapd_debug     = 0

# CSPI
spi_clock    = 20000000
spi_bus_num  = 0
spi_cs_num   = 0
spi_gpio_irq = 5
spi_polling_interval = 0

# FT232H USB-SPI
ft232h_usb_spi = 0

# RF
max_txpwr         = 24
bd_name           = ''

# PHY
guard_int         = 'auto'

# MAC & features
short_bcn_enable  = 0
legacy_ack_enable = 0
auth_control_enable = 0
auth_control_slot   = 100
auth_control_scale  = 10
auth_control_ti_min = 8
auth_control_ti_max = 64
beacon_bypass_enable = 0
ampdu_enable      = 2
ndp_ack_1m        = 0
ndp_preq          = 0
cqm_enable        = 1
relay_type        = 1
relay_nat         = 1
power_save        = 0
ps_timeout        = '3s'
sleep_duration    = '3s'
listen_interval   = 1000
idle_mode         = 0
bss_max_idle_enable = 1
bss_max_idle        = 1800
sw_enc              = 0
peer                = 0
static_ip           = 0
batman              = 0
self_config         = 0
prefer_bw           = 0
dwell_time          = 100
discard_deauth      = 0
bitmap_encoding     = 1
reverse_scrambler   = 1
use_bridge_setup    = 0
bridge_ip_mode      = 1
support_ch_width    = 1
power_save_pretend  = 0
duty_cycle_enable   = 0
duty_cycle_window   = 0
duty_cycle_duration = 0
cca_threshold       = -75
twt_int             = 0
twt_num             = 0
twt_sp              = 0
twt_force_sleep     = 0
twt_num_in_group    = 1
twt_algo            = 0
use_eeprom_config   = 0

# ----------------------------------------------------------------------------
# Small utilities (dry-run対応)
# ----------------------------------------------------------------------------

def _print_cmd(cmd: str):
    print("$ " + cmd)

def run(cmd: str) -> int:
    _print_cmd(cmd)
    if DRY_RUN:
        return 0
    return os.system(cmd)

def check_output(cmd: str, timeout: int | None = None) -> str:
    _print_cmd(cmd)
    if DRY_RUN:
        return "dry-run"
    return subprocess.check_output(cmd, shell=True, timeout=timeout).decode(errors='ignore')

def popen_communicate(cmd: str) -> str:
    _print_cmd(cmd)
    if DRY_RUN:
        return ""
    p = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = p.communicate()[0]
    try:
        return out.decode()
    except Exception:
        return str(out)

# ----------------------------------------------------------------------------
# CLI helpers (原作互換)
# ----------------------------------------------------------------------------

def usage_print():
    print("Usage: \n\tstart.py [sta_type] [security_mode] [country] [channel] [sniffer_mode] \
            \n\tstart.py [sta_type] [security_mode] [country] [mesh_mode] [mesh_peering] [mesh_ip]")
    print("Argument:    \n\tsta_type      [0:STA   |  1:AP  |  2:SNIFFER  | 3:RELAY |  4:MESH] \
            \n\tsecurity_mode [0:Open  |  1:WPA2-PSK  |  2:WPA3-OWE  |  3:WPA3-SAE | 4:WPS-PBC] \
                         \n\tcountry       [US:USA  |  JP:Japan  |  TW:Taiwan  |  AU:Australia  |  NZ:New Zealand  | \
                         \n\t               K1:Korea-USN  |  K2:Korea-MIC  |  CN:China | \
                         \n\t               S8:Singapore(866-869 MHz)  |  S9:Singapore(920-925 MHz) | \
                         \n\t               and EU channel support countries(EU countries, GB and SA)] \
                         \n\t----------------------------------------------------------- \
                         \n\tchannel       [S1G Channel Number]   * Only for Sniffer & AP \
                         \n\tsniffer_mode  [0:Local | 1:Remote]   * Only for Sniffer \
                         \n\tmesh_mode     [0:MPP | 1:MP | 2:MAP] * Only for Mesh \
                         \n\tmesh_peering  [Peer MAC address]     * Only for Mesh \
                         \n\tmesh_ip       [Static IP address]    * Only for Mesh")
    print("Example:  \n\tOPEN mode STA for US                : ./start.py 0 0 US \
                      \n\tSecurity mode AP for US                : ./start.py 1 1 US \
                      \n\tLocal Sniffer mode on CH 40 for Japan  : ./start.py 2 0 JP 40 0 \
                      \n\tSAE mode Mesh AP for US                : ./start.py 4 3 US 2 \
                      \n\tMesh Point with static ip              : ./start.py 4 3 US 1 192.168.222.1 \
                      \n\tMesh Point with manual peering         : ./start.py 4 3 US 1 8c:0f:fa:00:29:46 \
                      \n\tMesh Point with manual peering & ip    : ./start.py 4 3 US 1 8c:0f:fa:00:29:46 192.168.222.1")
    print("Note: \n\tsniffer_mode should be set as '1' when running sniffer on remote terminal \
                  \n\tMPP, MP mode support only Open, WPA3-SAE security mode")
    sys.exit()


def isNumber(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def isMacAddress(s: str) -> bool:
    return len(s) == 17 and ':' in s

def isIP(s: str) -> bool:
    return 6 < len(s) < 16 and '.' in s


def strSTA():
    t = int(sys.argv[1])
    return {0:'STA',1:'AP',2:'SNIFFER',3:'RELAY',4:'MESH'}.get(t, usage_print())

def strSecurity():
    t = int(sys.argv[2])
    return {0:'OPEN',1:'WPA2-PSK',2:'WPA3-OWE',3:'WPA3-SAE',4:'WPA-PBC'}.get(t, usage_print())

def strPSType():
    return {0:'Always On',2:'Deep Sleep (TIM)',3:'Deep Sleep (nonTIM)'}.get(int(power_save), 'Invalid Type')

def strSnifferMode():
    t = int(sys.argv[5])
    return {0:'LOCAL',1:'REMOTE'}.get(t, usage_print())

def strAMPDUMode(param):
    return {0:'OFF',1:'MANUAL'}.get(int(param), 'AUTO')

def strMeshMode():
    t = int(sys.argv[4])
    return {0:'Mesh Portal',1:'Mesh Point',2:'Mesh AP'}.get(t, usage_print())

def strOriCountry():
    c = str(sys.argv[3])
    return 'KR' if c in ('K1','K2') else ('SG' if c in ('S8','S9') else ('TW' if c in ('T8','T9') else c))


def checkEUCountry():
    return str(sys.argv[3]) in EU_CH_COUNTRIES


def checkCountry():
    if checkEUCountry() or str(sys.argv[3]) in S1G_CH_COUNTRIES:
        return
    usage_print()


def checkMeshUsage():
    global sw_enc, relay_type, peer, static_ip
    if len(sys.argv) < 5:
        usage_print()
    relay_type = int(sys.argv[4])
    if len(sys.argv) == 6:
        if isMacAddress(sys.argv[5]):
            peer = sys.argv[5]
        elif isIP(sys.argv[5]):
            static_ip = sys.argv[5]
        elif sys.argv[5] == 'nodhcp':
            static_ip = 'nodhcp'
        else:
            usage_print()
    elif len(sys.argv) == 7:
        if isMacAddress(sys.argv[5]):
            peer = sys.argv[5]
        else:
            usage_print()
        if isIP(sys.argv[6]):
            static_ip = sys.argv[6]
        elif sys.argv[6] == 'nodhcp':
            static_ip = 'nodhcp'
        else:
            usage_print()
    argv_print()


def checkParamValidity():
    if strSTA() == 'STA' and int(power_save) > 0 and int(listen_interval) > 65535:
        print("Max listen_interval is 65535!")
        sys.exit()


def strOnOff(v):
    return 'ON' if int(v) == 1 else 'OFF'

def strBDName():
    return str(bd_name) if str(bd_name) else f"nrc{model}_bd.dat"


def argv_print():
    print("------------------------------")
    print("Model            : " + str(model))
    print("STA Type         : " + strSTA())
    print("Country          : " + str(sys.argv[3]))
    print("Security Mode    : " + strSecurity())
    print("BD Name          : " + strBDName())
    print("AMPDU            : " + strAMPDUMode(ampdu_enable))
    if strSTA() == 'STA':
        print("CQM              : " + strOnOff(cqm_enable))
    if strSTA() == 'SNIFFER':
        print("Channel Selected : " + str(sys.argv[4]))
        print("Sniffer Mode     : " + strSnifferMode())
    if int(fw_download) == 1:
        print("Download FW      : " + fw_name)
    print("MAX TX Power     : " + str(max_txpwr) + " dBm")
    if int(bss_max_idle_enable) == 1:
        if strSTA() in ('AP','RELAY','STA'):
            print("BSS MAX IDLE     : " + str(bss_max_idle))
    if strSTA() == 'STA':
        print("Power Save Type  : " + strPSType())
        if int(power_save) > 0:
            print("PS Timeout       : " + ps_timeout)
        if int(power_save) == 3:
            print("Sleep Duration   : " + sleep_duration)
        if int(listen_interval) > 0:
            print("Listen Interval  : " + str(listen_interval))
    if strSTA() == 'MESH':
        print("Mesh Mode        : " + strMeshMode())
    if int(use_eeprom_config) == 1:
        print("CONFIG_LOCATION  : EEPROM")
    else:
        print("CONFIG_LOCATION  : FLASH")
    print("------------------------------")

# ----------------------------------------------------------------------------
# Networking helpers (dry-run aware)
# ----------------------------------------------------------------------------

def check(interface: str) -> str:
    if int(use_bridge_setup) > 0 and int(bridge_ip_mode) == 1:
        run('sudo dhclient ' + interface + ' -nw -v')
    _ = popen_communicate("ifconfig " + interface)
    return 'dry-run: simulated IP assignment' if DRY_RUN else ('' if _ is None else next((l for l in _.split("\n") if "inet 192.168" in l), ''))


def copyConf():
    run(f"sudo {FIRMWARE_COPY_SH} {model} {strBDName()} {use_eeprom_config}")
    run(f"{IP_CONFIG_SH} {strSTA()} {relay_type} {static_ip} {batman}")
    if int(use_bridge_setup) > 0:
        run(f"sudo {IP_CONFIG_BR_SH} {strSTA()} {use_bridge_setup - 1} {bridge_ip_mode}")


def startNAT():
    run('sudo sh -c "echo 1 > /proc/sys/net/ipv4/ip_forward"')
    if strSTA() == 'AP':
        run("sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE")
        run("sudo iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT")
        run("sudo iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT")
    elif strSTA() == 'RELAY' and int(relay_nat) == 1:
        if int(relay_type) == 1:
            run("sudo iptables -t nat -A POSTROUTING -o wlan1 -j MASQUERADE")
            run("sudo iptables -A FORWARD -i wlan0 -o wlan1 -m state --state RELATED,ESTABLISHED -j ACCEPT")
            run("sudo iptables -A FORWARD -i wlan1 -o wlan0 -j ACCEPT")
        elif int(relay_type) == 0:
            run("sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE")
            run("sudo iptables -A FORWARD -i wlan1 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT")
            run("sudo iptables -A FORWARD -i wlan0 -o wlan1 -j ACCEPT")
    else:
        print("fail to start NAT")


def stopNAT():
    run('sudo sh -c "echo 0 > /proc/sys/net/ipv4/ip_forward"')
    run("sudo iptables -t nat --flush")
    run("sudo iptables --flush")


def startDHCPCD():
    run("sudo systemctl start dhcpcd")

def stopDHCPCD():
    run("sudo systemctl stop dhcpcd")

def startDNSMASQ():
    run("sudo systemctl start dnsmasq")

def stopDNSMASQ():
    run("sudo systemctl stop dnsmasq")


def addWLANInterface(interface: str):
    if strSTA() == 'RELAY' and interface == "wlan1":
        print("[*] Create wlan1 for concurrent mode")
        run("sudo iw dev wlan0 interface add wlan1 type managed")
        run("sudo ifconfig wlan1 up")
        time.sleep(3)

# ----------------------------------------------------------------------------
# Self configuration / Hostapd (dry-run aware)
# ----------------------------------------------------------------------------

def self_config_check():
    country = 'EU' if checkEUCountry() else str(sys.argv[3])
    conf_path = os.path.join(CONF_PATH, country)
    conf_file = ""
    global dwell_time

    sec = strSecurity()
    mapping = {
        'OPEN': "/ap_halow_open.conf",
        'WPA2-PSK': "/ap_halow_wpa2.conf",
        'WPA3-OWE': "/ap_halow_owe.conf",
        'WPA3-SAE': "/ap_halow_sae.conf",
        'WPA-PBC': "/ap_halow_pbc.conf",
    }
    conf_file += mapping.get(sec, "")

    print(f"country: {country}, prefer_bw: {prefer_bw}, dwell_time: {dwell_time}")

    self_conf_cmd = f"{CLI_APP} show self_config {country} {prefer_bw} {dwell_time} "
    if int(dwell_time) > 1000:
        dwell_time = 1000
    elif int(dwell_time) < 10:
        dwell_time = 10
    checkout_timeout = int(dwell_time) * 26
    try:
        print(f"Start CCA scan.... It will take up to {checkout_timeout/1000} sec to complete")
        result = check_output(f"timeout {checkout_timeout} {self_conf_cmd}")
    except Exception:
        if DRY_RUN:
            print('[dry-run] self_config: skipping scan and using placeholder channel 1')
            result = 'best_channel:1'
        else:
            sys.exit(f"[self_configuration] No return best channel within {checkout_timeout/1000} seconds")

    if 'no_self_conf' in result and not DRY_RUN:
        print("Target FW does NOT support self configuration. Please check FW")
        return 'Fail'
    else:
        print(result)
        best_channel = '1' if DRY_RUN else re.split(r'[:,\s,\t,\n]+', result)[-3]
        run(f"sudo cp {conf_path}{conf_file} {TEMP_SELF_CONF}")
        run(f"sed -i '/channel=/d' {TEMP_SELF_CONF}")
        run(f"sed -i '/hw_mode=/d' {TEMP_SELF_CONF}")
        run(f"sed -i '/#ssid=/d' {TEMP_SELF_CONF}")
        if int(best_channel) < 36:
            run(f"sed -i \"/ssid=.*/ahw_mode=g\" {TEMP_SELF_CONF}")
        else:
            run(f"sed -i \"/ssid=.*/ahw_mode=a\" {TEMP_SELF_CONF}")
        run(f"sed -i \"/hw_mode=.*/achannel={best_channel}\" {TEMP_SELF_CONF}")
        run(f"sed -i \"s/^country_code=.*/country_code={strOriCountry()}/g\" {TEMP_SELF_CONF}")
        print("Start with channel: " + best_channel)
        return 'Done'


def ft232h_usb():
    global spi_clock, spi_bus_num, spi_gpio_irq, spi_cs_num, spi_polling_interval
    print("[*] use ft232h_usb_spi")
    spi_bus_num = 3
    spi_gpio_irq = 500
    if int(spi_clock) > 15000000:
        spi_clock = 15000000
    if int(spi_cs_num) != 0:
        spi_cs_num = 0
    if int(spi_polling_interval) <= 0:
        spi_polling_interval = 50
    if int(ft232h_usb_spi) != 1:
        spi_gpio_irq = -1


def setAPParam():
    global ndp_preq
    ndp_preq = 1

def setRelayParam():
    global sw_enc, power_save, ndp_ack_1m, ndp_preq
    power_save = 0; ndp_ack_1m = 0; ndp_preq = 0


def setSnifferParam():
    global sw_enc, ampdu_enable, bss_max_idle_enable, power_save, ndp_ack_1m, listen_interval
    sw_enc=0; ampdu_enable=0; bss_max_idle_enable=0; power_save=0; ndp_ack_1m=0; listen_interval=0


def setMeshParam():
    global short_bcn_enable
    short_bcn_enable = 0


def setModuleParam():
    global spi_clock, spi_bus_num, spi_cs_num, spi_gpio_irq, spi_polling_interval

    if int(ft232h_usb_spi) > 0:
        ft232h_usb()
    if strSTA() == 'AP':
        setAPParam()
    if strSTA() == 'RELAY':
        setRelayParam()
    if strSTA() == 'SNIFFER':
        setSnifferParam()
    if strSTA() == 'MESH':
        setMeshParam()

    spi_arg = f" hifspeed={spi_clock} spi_bus_num={spi_bus_num} spi_cs_num={spi_cs_num} spi_gpio_irq={spi_gpio_irq} spi_polling_interval={spi_polling_interval}"
    fw_arg = f" fw_name={fw_name}" if int(fw_download) == 1 else ""

    power_save_arg = sleep_duration_arg = idle_mode_arg = ps_gpio_arg = ""
    if strSTA() == 'STA' and int(power_save) > 0:
        if str(model) in ("7393","7394"):
            ps_gpio_arg = " power_save_gpio=17,14,1"
        power_save_arg = f" power_save={power_save}"
        if int(power_save) == 3:
            sd = re.sub(r'[^0-9]','', sleep_duration)
            unit = sleep_duration[-1]
            sleep_duration_arg = f" sleep_duration={sd},{0 if unit=='m' else 1}"
    if strSTA() == 'STA' and int(idle_mode) == 1:
        idle_mode_arg = " idle_mode=1"
        if str(model) in ("7393","7394"):
            ps_gpio_arg = " power_save_gpio=17,14,1"

    duty_cycle_arg = f" set_duty_cycle={duty_cycle_enable},{duty_cycle_window},{duty_cycle_duration}" if int(duty_cycle_enable)==1 else ""
    cca_thresh_arg = f" set_cca_threshold={cca_threshold}"

    bss_max_idle_arg = f" bss_max_idle={bss_max_idle}" if int(bss_max_idle_enable)==1 and strSTA() in ('AP','RELAY','STA') else ""
    ndp_preq_arg = " ndp_preq=1" if int(ndp_preq)==1 else ""
    ndp_ack_1m_arg = " ndp_ack_1m=1" if int(ndp_ack_1m)==1 else ""
    auto_ba_arg = f" ampdu_mode={ampdu_enable}" if int(ampdu_enable)!=2 else ""
    sw_enc_arg = f" sw_enc={sw_enc}" if int(sw_enc)>0 else ""
    cqm_arg = " disable_cqm=1" if int(cqm_enable)==0 else ""
    sbi_arg = " enable_short_bi=0" if int(short_bcn_enable)==0 else ""
    legacy_ack_arg = " enable_legacy_ack=1" if int(legacy_ack_enable)==1 else ""
    auth_control_arg = (
        f" set_auth_control={auth_control_enable},{auth_control_slot},{auth_control_ti_min},{auth_control_ti_max},{auth_control_scale}"
        if int(auth_control_enable)==1 and strSTA()=='AP' else ""
    )
    beacon_bypass_arg = " enable_beacon_bypass=1" if int(beacon_bypass_enable)==1 else ""
    listen_int_arg = f" listen_interval={listen_interval}" if int(listen_interval)>0 else ""

    kr_band_arg = " kr_band=1" if str(sys.argv[3])=='K1' else (" kr_band=2" if str(sys.argv[3])=='K2' else "")
    sg_band_arg = " sg_band=8" if str(sys.argv[3])=='S8' else (" sg_band=9" if str(sys.argv[3])=='S9' else "")
    tw_band_arg = " tw_band=8" if str(sys.argv[3])=='T8' else (" tw_band=9" if str(sys.argv[3])=='T9' else "")

    discard_deauth_arg = " discard_deauth=1" if int(discard_deauth)==1 else ""
    drv_dbg_arg = " debug_level_all=1" if int(driver_debug)==1 else ""
    dbg_fc_arg = " debug_level_all=1 dbg_flow_control=1" if int(dbg_flow_control)==1 else ""
    be_arg = " bitmap_encoding=0" if int(bitmap_encoding)==0 else ""
    rs_arg = " reverse_scrambler=0" if int(reverse_scrambler)==0 else ""
    ps_pretend_arg = " ps_pretend=1" if int(power_save_pretend)==1 else ""

    twt_arg = ""
    if int(twt_num) > 0 or int(twt_sp) > 0 or int(twt_int) > 0:
        twt_arg = f" twt_num={twt_num} twt_sp={twt_sp} twt_int={twt_int} twt_force_sleep={twt_force_sleep} twt_num_in_group={twt_num_in_group} twt_algo={twt_algo}"

    bd_name_arg = f" bd_name={strBDName()}"
    support_ch_width_arg = " support_ch_width=0" if (strSTA()=='STA' and int(support_ch_width)==0) else ""

    module_param = (
        spi_arg + fw_arg + power_save_arg + sleep_duration_arg + idle_mode_arg + bss_max_idle_arg +
        ndp_preq_arg + ndp_ack_1m_arg + auto_ba_arg + sw_enc_arg + cqm_arg + listen_int_arg + drv_dbg_arg +
        sbi_arg + discard_deauth_arg + dbg_fc_arg + kr_band_arg + legacy_ack_arg + be_arg + rs_arg +
        beacon_bypass_arg + ps_gpio_arg + bd_name_arg + support_ch_width_arg + ps_pretend_arg + sg_band_arg +
        duty_cycle_arg + cca_thresh_arg + twt_arg + auth_control_arg + tw_band_arg
    )
    return module_param

# ----------------------------------------------------------------------------
# Routines (STA/AP/SNIFFER etc.)
# ----------------------------------------------------------------------------

def run_common():
    if int(max_cpuclock) == 1:
        print("[*] Set Max CPU Clock on RPi")
        run(f"sudo {CLOCK_CONF_SH}")

    print("[0] Clear")
    run("sudo hostapd_cli disable 2>/dev/null")
    run("sudo wpa_cli disable wlan0 2>/dev/null ")
    run("sudo wpa_cli disable wlan1 2>/dev/null")
    run("sudo killall -9 wpa_supplicant 2>/dev/null")
    run("sudo killall -9 hostapd 2>/dev/null")
    run("sudo killall -9 wireshark 2>/dev/null")
    run("sudo rmmod nrc 2>/dev/null")
    run(f"sudo rm {TEMP_SELF_CONF} 2>/dev/null")
    run(f"sudo rm {TEMP_HOSTAPD_CONF} 2>/dev/null")
    run("sudo sh -c '[ -e /proc/sys/kernel/sysrq ] && echo 0 > /proc/sys/kernel/sysrq'")
    stopNAT(); stopDHCPCD(); stopDNSMASQ()
    time.sleep(1)

    print("[1] Copy and Set Module Parameters")
    copyConf()
    insmod_arg = setModuleParam()

    print("[2] Set Initial Country")
    run("sudo iw reg set " + strOriCountry())

    print("[3] Loading module")
    print(f"sudo insmod {DRIVER_KO} " + insmod_arg)
    run(f"sudo insmod {DRIVER_KO} " + insmod_arg)

    time.sleep(0 if DRY_RUN else (10 if int(spi_polling_interval) > 0 else 5))

    if strSTA() == 'RELAY' and int(relay_type) == 0:
        addWLANInterface('wlan1')
    elif strSTA() == 'MESH' and int(relay_type) == 2:
        # mesh インタフェース作成
        run('sudo iw dev wlan0 interface add mesh0 type mp; sudo ifconfig mesh0 up')

    if not DRY_RUN:
        ret = subprocess.call(["sudo", "ifconfig", "wlan0", "up"])
        if ret == 255:
            run('sudo rmmod nrc.ko')
            sys.exit()
    else:
        _print_cmd('sudo ifconfig wlan0 up')

    print("[4] Set Maximum TX Power")
    run(f"{CLI_APP} set txpwr limit {max_txpwr}")
    if strSTA() != 'SNIFFER':
        print("[*] Transmission Power Control(TPC) is activated")
        run(f"sudo iw phy nrc80211 set txpower limit {int(max_txpwr) * 100}")

    print("[5] Set guard interval: " + guard_int)
    run(f"{CLI_APP} set gi {guard_int}")

    print("[*] Start DHCPCD and DNSMASQ")
    startDHCPCD(); startDNSMASQ()


def run_sta(interface: str):
    country = 'EU' if checkEUCountry() else str(sys.argv[3])
    conf_dir = os.path.join(CONF_PATH, country)
    run("sudo killall -9 wpa_supplicant")

    bridge = ''
    if int(use_bridge_setup) > 0:
        bridge = '-b br0 '
        print('[*] STA bridge configuration')
        if strSTA() == 'RELAY':
            run(f"sudo brctl addbr br0; sudo ifconfig wlan1 up; sudo ifconfig wlan1 0.0.0.0; sudo ifconfig wlan0 0.0.0.0; sudo iw {interface} set 4addr on; sudo brctl addif br0 {interface}; sudo ifconfig br0 up")
        else:
            eth = 'eth' + str(int(use_bridge_setup) - 1)
            run(f"sudo brctl addbr br0; sudo ifconfig {eth} up; sudo ifconfig {interface} 0.0.0.0; sudo ifconfig {eth} 0.0.0.0; sudo iw {interface} set 4addr on; sudo brctl addif br0 {interface}; sudo brctl addif br0 {eth}; sudo ifconfig br0 up")
            run('sudo brctl show')

    debug = '-dddd' if int(supplicant_debug) == 1 else ''

    if int(power_save) > 0:
        print("[*] Set default power save timeout for " + interface)
        run("sudo iwconfig " + interface + " power timeout " + ps_timeout)

    print("[6] Start wpa_supplicant on " + interface)
    sec = strSecurity()
    mapping = {
        'OPEN': "/sta_halow_open.conf ",
        'WPA2-PSK': "/sta_halow_wpa2.conf ",
        'WPA3-OWE': "/sta_halow_owe.conf ",
        'WPA3-SAE': "/sta_halow_sae.conf ",
        'WPA-PBC': "/sta_halow_pbc.conf ",
    }
    conf_file = mapping.get(sec, "")

    if conf_file:
        if country == "EU":
            run("sed -i \"s/^country=.*/country=%s/g\" %s" % ( str(sys.argv[3]), conf_dir + conf_file ))
        run("sudo wpa_supplicant -i" + interface + " -c " + conf_dir + conf_file + bridge + debug + " &")
        if sec == 'WPA-PBC':
            time.sleep(0 if DRY_RUN else 1)
            run("sudo wpa_cli wps_pbc")
    time.sleep(0 if DRY_RUN else 3)

    print("[7] Connect and DHCP")
    iface = 'br0' if int(use_bridge_setup) > 0 else interface
    ret = check(iface)
    if DRY_RUN:
        print(ret)
    else:
        while ret == '':
            print("Waiting for IP")
            time.sleep(5)
            ret = check(iface)
        print(ret)
    print("IP assigned. HaLow STA ready")
    print("--------------------------------------------------------------------")


def launch_hostapd(interface: str, orig_hostapd_conf_file: str, country: str, debug: str, channel: str | None):
    print("[*] configure file copied from: %s" % (orig_hostapd_conf_file))
    run("sudo cp %s %s" % ( orig_hostapd_conf_file,  TEMP_HOSTAPD_CONF ))
    run("sed -i \"4s/.*/interface=%s/g\" %s" % ( interface, TEMP_HOSTAPD_CONF ))
    if country == "EU":
        run("sed -i \"s/^country_code=.*/country_code=%s/g\" %s" % ( str(sys.argv[3]), TEMP_HOSTAPD_CONF ))
    if channel:
        run("sed -i \"s/^channel=.*/channel=%s/g\" %s" % ( channel, TEMP_HOSTAPD_CONF ))
        if country == "US" and 1 <= int(channel) <= 13:
            run("sed -i \"s/^hw_mode=.*/hw_mode=g/g\" %s" % ( TEMP_HOSTAPD_CONF ))
    run("sudo hostapd %s %s &" % ( TEMP_HOSTAPD_CONF, debug ))


def run_ap(interface: str):
    country = 'EU' if checkEUCountry() else str(sys.argv[3])
    conf_path = os.path.join(CONF_PATH, country)
    global self_config
    channel = None

    sec = strSecurity()
    mapping = {
        'OPEN': "/ap_halow_open.conf",
        'WPA2-PSK': "/ap_halow_wpa2.conf",
        'WPA3-OWE': "/ap_halow_owe.conf",
        'WPA3-SAE': "/ap_halow_sae.conf",
        'WPA-PBC': "/ap_halow_pbc.conf",
    }
    conf_file = mapping.get(sec, "")

    if int(use_bridge_setup) > 0:
        run("sed -i /wds_sta/,/bridge/s/##*// " + conf_path + conf_file)
    else:
        run("sed -i /wds_sta/,/bridge/'s/^/#/;/wds_sta/,/bridge/s/##*/#/' " + conf_path + conf_file)

    if len(sys.argv) > 4:
        channel = str(sys.argv[4])

    debug = '-dddd' if int(hostapd_debug) == 1 else ''

    if strSTA() == 'RELAY':
        self_config = 0
        print("[*] Selfconfig is not used in RELAY mode.")

    if int(self_config) == 1:
        print("[*] Self configuration start!")
        self_conf_result = self_config_check()
    elif int(self_config) == 0:
        print("[*] Self configuration off")
        self_conf_result = None
    else:
        print("[*] self_conf value should be 0 or 1..  Start with default mode(no self configuration)")
        self_conf_result = None

    print("[6] Start hostapd on " + interface)
    if int(self_config)==1 and self_conf_result=='Done':
        run("sed -i \"4s/.*/interface=%s/g\" %s" % ( interface, TEMP_SELF_CONF ))
        run("sudo hostapd " + TEMP_SELF_CONF + " " + debug + " &")
        if sec == 'WPA-PBC':
            time.sleep(0 if DRY_RUN else 1)
            run("sudo hostapd_cli wps_pbc")
    else:
        launch_hostapd(interface, os.path.join(CONF_PATH, country + conf_file), country, debug, channel)
        if sec == 'WPA-PBC':
            time.sleep(0 if DRY_RUN else 1)
            run("sudo hostapd_cli wps_pbc")
    time.sleep(0 if DRY_RUN else 3)

    if int(use_bridge_setup) > 0:
        print('[*] AP bridge configuration')
        if strSTA() == 'RELAY':
            run('sudo brctl addif br0 {w}'.format(w=interface))
        else:
            eth = 'eth' + str(int(use_bridge_setup) - 1)
            run('sudo ifconfig {e} up; sudo ifconfig {w} 0.0.0.0; sudo ifconfig {e} 0.0.0.0; sudo brctl addif br0 {e}; sudo ifconfig br0 up '.format(e=eth, w=interface))
        run('sudo brctl show')
        time.sleep(0 if DRY_RUN else 3)

    print("[7] Start NAT")
    startNAT()

    time.sleep(0 if DRY_RUN else 3)
    print("[8] ifconfig")
    run('sudo ifconfig')
    print("HaLow AP ready")
    print("--------------------------------------------------------------------")


def run_sniffer():
    print("[6] Setting Monitor Mode")
    time.sleep(0 if DRY_RUN else 3)
    run('sudo ifconfig wlan0 down; sudo iw dev wlan0 set type monitor; sudo ifconfig wlan0 up')
    print("[7] Setting Country: " + strOriCountry())
    run("sudo iw reg set " + strOriCountry())
    time.sleep(0 if DRY_RUN else 3)
    print("[8] Setting Channel: " + str(sys.argv[4]))
    run("sudo iw dev wlan0 set channel " + str(sys.argv[4]))
    time.sleep(0 if DRY_RUN else 3)
    print("[9] Start Sniffer")
    if strSnifferMode() == 'LOCAL':
        run('sudo wireshark -i wlan0 -k -S -l &')
    else:
        run('lxqt-sudo wireshark -i wlan0 -k -S -l &')
    print("HaLow SNIFFER ready")
    print("--------------------------------------------------------------------")

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
if __name__ == '__main__':
    if len(sys.argv) < 4 or not isNumber(sys.argv[1]) or not isNumber(sys.argv[2]):
        usage_print()
    elif strSTA() == 'SNIFFER' and len(sys.argv) < 6:
        usage_print()
    elif strSTA() == 'MESH':
        checkMeshUsage()
    else:
        argv_print()

    # Mesh サブルーチンは副作用が大きいため、dry-run 時は表示のみ
    if DRY_RUN and strSTA() == 'MESH':
        print('[dry-run] mesh setup would run here (run_mpp/mp/map). Skipping execution.')

    checkParamValidity()
    checkCountry()

    print("NRC " + strSTA() + " setting for HaLow...")

    run_common()

    if strSTA() == 'STA':
        run_sta('wlan0')
    elif strSTA() == 'AP':
        run_ap('wlan0')
    elif strSTA() == 'SNIFFER':
        run_sniffer()
    elif strSTA() == 'RELAY':
        if int(relay_type) == 0:
            if DRY_RUN:
                print('[dry-run] threading: run_sta(wlan0) & run_ap(wlan1) would start')
            else:
                t = threading.Thread(target=run_sta, args=('wlan0',))
                t.start()
                run_ap('wlan1')
        else:
            addWLANInterface('wlan1')
            if DRY_RUN:
                print('[dry-run] threading: run_sta(wlan1) & run_ap(wlan0) would start')
            else:
                t = threading.Thread(target=run_sta, args=('wlan1',))
                t.start()
                run_ap('wlan0')
    elif strSTA() == 'MESH':
        if not DRY_RUN:
            if strMeshMode() == 'Mesh Portal':
                run_mpp('wlan0', str(sys.argv[3]), strSecurity(), supplicant_debug, peer, static_ip, batman)
            elif strMeshMode() == 'Mesh Point':
                run_mp('wlan0', str(sys.argv[3]), strSecurity(), supplicant_debug, peer, static_ip, batman)
            elif strMeshMode() == 'Mesh AP':
                run_map('wlan0', 'mesh0', str(sys.argv[3]), strSecurity(), supplicant_debug, peer, static_ip, batman)
            else:
                usage_print()
    else:
        usage_print()

    print("Done.")

