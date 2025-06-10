#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアル通信デバッグテスト（PySerial + termios 版）
16バイト固定受信（VMIN=16, VTIME=5 相当）
"""

import sys
import time
import signal
import termios
import serial

running = True

def handle_sigint(signum, frame):
    """Ctrl+C でループを抜ける"""
    global running
    running = False

def test_serial_ports():
    """利用可能なシリアルポートをテスト"""
    ports_to_test = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyAMA0",
        "/dev/serial0",
        "/dev/ttyS0"
    ]
    print("🔍 利用可能なシリアルポートを検索中…")
    for port in ports_to_test:
        try:
            ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"✅ {port}: 接続成功")
            ser.close()
        except Exception as e:
            print(f"❌ {port}: {e}")

def monitor_serial(port="/dev/ttyUSB0"):
    """16バイト固定受信でシリアルをモニタリング"""
    global running
    try:
        # ブロッキング読み込みにするため timeout=None
        ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=None
        )

        # termios で VMIN=16, VTIME=5 を設定
        fd = ser.fileno()
        attrs = termios.tcgetattr(fd)
        # attrs[6] は c_cc 配列
        attrs[6][termios.VMIN]  = 16   # 最低受信バイト数
        attrs[6][termios.VTIME] = 5    # 0.5秒（単位はデシ秒）
        termios.tcsetattr(fd, termios.TCSANOW, attrs)

        print(f"📡 シリアルモニタリング開始: {port}")
        print("    設定: 9600bps, 8bit, Even parity, 1 stop bit")
        print("    VMIN=16, VTIME=5 (0.5秒)")
        print("    Ctrl+C で終了\n")

        signal.signal(signal.SIGINT, handle_sigint)
        signal.signal(signal.SIGTERM, handle_sigint)

        last_activity = time.time()

        while running:
            # 16バイト読んで返ってくる（VMIN/VTIME に従う）
            data = ser.read(16)
            if data:
                ts = time.strftime("%H:%M:%S")
                hexstr = data.hex().upper()
                ascstr = ''.join(
                    chr(b) if 32 <= b <= 126 else '.' for b in data
                )
                print(f"[{ts}] 受信 ({len(data)} バイト)")
                print(f"  HEX  : {hexstr}")
                print(f"  ASCII: {ascstr}\n")
                last_activity = time.time()
            else:
                # タイムアウト（VTIME）で n == 0
                if time.time() - last_activity > 10:
                    print(f"[{time.strftime('%H:%M:%S')}] 待機中… (データなし)\n")
                    last_activity = time.time()

        print("\n🛑 モニタリング終了")

    except Exception as e:
        print(f"❌ エラー: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            test_serial_ports()
        else:
            monitor_serial(sys.argv[1])
    else:
        print("使用方法:")
        print("  python3 serial_debug_test.py test          # ポート検索")
        print("  python3 serial_debug_test.py /dev/ttyUSB0  # モニタリング\n")
        test_serial_ports()
        print()
        monitor_serial()

if __name__ == "__main__":
    main()
