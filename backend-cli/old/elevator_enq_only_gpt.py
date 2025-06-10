#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS-422 定周期送信スクリプト（COM27）

時系列（1 周期 = 32 秒）
 t =  0 s : ① ENQ 0002 W 0001 XXXX
 t =  1 s : ② ENQ 0002 W 0002 XXXX
 t =  2 s : ③ ENQ 05H 0002 W 0003 074E
 t = 12 s : ④ ENQ 0002 W 0002 0000   （③送信後 10 秒）
 t = 32 s : ① に戻り繰り返し

①と②の XXXX は B1F～3F の 4 種から毎回ランダムに 2 つ重複しないよう選択。
"""

import time
import random
import serial

# ==== シリアル設定 ====
SERIAL_PORT = "COM27"          # ご使用の RS-422 アダプタに合わせて変更
BAUDRATE    = 9600
BYTESIZE    = serial.EIGHTBITS
PARITY      = serial.PARITY_NONE
STOPBITS    = serial.STOPBITS_ONE
TIMEOUT     = 1.0              # 受信を行わないなら任意

# ==== 階コード（XXXX 値） ====
FLOORS = {
    "B1F": "FFFF",
    "1F" : "0001",
    "2F" : "0002",
    "3F" : "0003",
}

# --------------------------------------------------------------------------- #
def build_cmd(cmd: str) -> bytes:
    """コマンド文字列を CR+LF 終端のバイト列へ整形"""
    return (cmd + "\r\n").encode("ascii")

def choose_two_distinct_codes():
    """XXXX 用コードを重複なしで 2 件取得"""
    return random.sample(list(FLOORS.values()), 2)

def main():
    with serial.Serial(
        port     = SERIAL_PORT,
        baudrate = BAUDRATE,
        bytesize = BYTESIZE,
        parity   = PARITY,
        stopbits = STOPBITS,
        timeout  = TIMEOUT,
    ) as ser:
        print(f"✅ {SERIAL_PORT} オープン ― 送信開始")
        while True:
            # ----------------- ① 送信 -----------------
            xxxx1, xxxx2 = choose_two_distinct_codes()
            cmd1 = f"ENQ 0002 W 0001 {xxxx1}"
            ser.write(build_cmd(cmd1))
            print(f"[{time.strftime('%H:%M:%S')}] → {cmd1}")
            time.sleep(1)

            # ----------------- ② 送信 -----------------
            cmd2 = f"ENQ 0002 W 0002 {xxxx2}"
            ser.write(build_cmd(cmd2))
            print(f"[{time.strftime('%H:%M:%S')}] → {cmd2}")
            time.sleep(1)

            # ----------------- ③ 送信 -----------------
            cmd3_header = bytes([0x05])             # 05H (ENQ)
            cmd3_body   = b" 0002 W 0003 074E\r\n"
            ser.write(cmd3_header + cmd3_body)
            print(f"[{time.strftime('%H:%M:%S')}] → 05H 0002 W 0003 074E")
            time.sleep(10)                          # ③後 10 秒

            # ----------------- ④ 送信 -----------------
            cmd4 = "ENQ 0002 W 0002 0000"
            ser.write(build_cmd(cmd4))
            print(f"[{time.strftime('%H:%M:%S')}] → {cmd4}")

            # 32 秒周期に合わせ残り 20 秒待機
            time.sleep(20)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 送信を停止しました")
