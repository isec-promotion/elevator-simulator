#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアル通信デバッグテスト
Raspberry Pi側でシリアルデータの受信状況を確認
"""

import serial
import time
import sys

def test_serial_ports():
    """利用可能なシリアルポートをテスト"""
    ports_to_test = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1", 
        "/dev/ttyAMA0",
        "/dev/serial0",
        "/dev/ttyS0"
    ]
    
    print("🔍 利用可能なシリアルポートを検索中...")
    
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
    """シリアルデータをモニタリング"""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        
        print(f"📡 シリアルモニタリング開始: {port}")
        print("設定: 9600bps, 8bit, Even parity, 1 stop bit")
        print("Ctrl+C で終了\n")
        
        last_activity = time.time()
        
        while True:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    timestamp = time.strftime("%H:%M:%S")
                    hex_data = data.hex().upper()
                    ascii_data = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in data])
                    
                    print(f"[{timestamp}] 受信 ({len(data)}バイト)")
                    print(f"  HEX: {hex_data}")
                    print(f"  ASCII: {ascii_data}")
                    print()
                    
                    last_activity = time.time()
            else:
                # 10秒間データがない場合、待機中メッセージ
                if time.time() - last_activity > 10:
                    print(f"[{time.strftime('%H:%M:%S')}] 待機中... (データなし)")
                    last_activity = time.time()
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
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
        print("  python3 serial_debug_test.py /dev/ttyUSB0  # モニタリング")
        print()
        test_serial_ports()
        print()
        monitor_serial()

if __name__ == "__main__":
    main()
