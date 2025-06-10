#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアル通信ACKテスト (Windows版)
ENQメッセージを送信してACK応答を確認
"""

import serial
import time
import sys

def calculate_checksum(data: bytes) -> str:
    """チェックサム計算"""
    total = sum(data)
    lower_byte = total & 0xFF
    upper_byte = (total >> 8) & 0xFF
    checksum = (lower_byte + upper_byte) & 0xFF
    return f"{checksum:02X}"

def send_enq_and_wait_ack(port="COM27"):
    """ENQメッセージを送信してACK応答を待機"""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_EVEN,
            stopbits=serial.STOPBITS_ONE,
            timeout=3
        )
        
        print(f"📡 シリアルACKテスト開始: {port}")
        print("設定: 9600bps, 8bit, Even parity, 1 stop bit")
        print("ENQメッセージを送信してACK応答を確認\n")
        
        # ENQメッセージ作成（現在階数データ）
        message = bytearray()
        message.append(0x05)  # ENQ
        message.extend("0001".encode('ascii'))  # 送信先局番号（自動運転装置）
        message.append(0x57)  # 'W'
        message.extend("0001".encode('ascii'))  # データ番号（現在階数）
        message.extend("0001".encode('ascii'))  # データ値（1F）
        
        # チェックサム計算
        checksum_data = message[1:]
        checksum = calculate_checksum(checksum_data)
        message.extend(checksum.encode('ascii'))
        
        print(f"📤 送信メッセージ: {message.hex().upper()}")
        print(f"   解析: ENQ(05) + 局番号(0001) + CMD(W) + データ番号(0001) + データ値(0001) + チェックサム({checksum})")
        print()
        
        # メッセージ送信
        ser.write(message)
        print(f"[{time.strftime('%H:%M:%S')}] ENQメッセージ送信完了")
        
        # ACK応答待機（3秒）
        print("ACK応答待機中...")
        start_time = time.time()
        buffer = bytearray()
        
        while time.time() - start_time < 3.0:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                if data:
                    buffer.extend(data)
                    hex_data = data.hex().upper()
                    ascii_data = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in data])
                    
                    print(f"[{time.strftime('%H:%M:%S')}] 受信 ({len(data)}バイト)")
                    print(f"  HEX: {hex_data}")
                    print(f"  ASCII: {ascii_data}")
                    
                    # ACK(06H)をチェック
                    if len(buffer) >= 5 and buffer[0] == 0x06:
                        ack_message = buffer[:5]
                        station = ack_message[1:5].decode('ascii')
                        print(f"✅ ACK受信成功!")
                        print(f"   ACKメッセージ: {ack_message.hex().upper()}")
                        print(f"   送信元局番号: {station}")
                        
                        if station == "0002":
                            print("🎉 正常なACK応答を受信しました（エレベーター側から）")
                        else:
                            print(f"⚠️ 予期しない局番号: {station}")
                        
                        ser.close()
                        return True
            
            time.sleep(0.1)
        
        # タイムアウト
        print("⏰ ACK応答タイムアウト（3秒）")
        if len(buffer) > 0:
            print(f"受信データ: {buffer.hex().upper()}")
        else:
            print("データ受信なし")
        
        ser.close()
        return False
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM27"
    
    print("=" * 60)
    print("SEC-3000H シリアル通信ACKテスト")
    print("=" * 60)
    
    # テスト実行
    success = send_enq_and_wait_ack(port)
    
    print("\n" + "=" * 60)
    if success:
        print("✅ テスト成功: ACK応答を正常に受信しました")
        print("シリアル通信の双方向接続は正常です")
    else:
        print("❌ テスト失敗: ACK応答を受信できませんでした")
        print("考えられる原因:")
        print("  1. シリアルケーブルの受信線（RX）接続不良")
        print("  2. Raspberry Pi側の受信機が動作していない")
        print("  3. RS422接続の送信・受信線の配線問題")
    print("=" * 60)

if __name__ == "__main__":
    main()
