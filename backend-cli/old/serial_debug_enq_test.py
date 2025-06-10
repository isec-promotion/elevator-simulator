#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアル通信ENQデバッグテスト (Windows版)
ENQコマンドを送信してACK受信をテスト
"""

import serial
import time
import sys
import threading

def calculate_checksum(data: bytes) -> str:
    """チェックサム計算"""
    total = sum(data)
    lower_byte = total & 0xFF
    upper_byte = (total >> 8) & 0xFF
    checksum = (lower_byte + upper_byte) & 0xFF
    return f"{checksum:02X}"

class SerialENQTester:
    def __init__(self, port="COM27"):
        self.port = port
        self.ser = None
        self.running = False
        self.received_data = []
        
    def connect(self):
        """シリアル接続"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"✅ シリアルポート {self.port} 接続成功")
            return True
        except Exception as e:
            print(f"❌ シリアル接続エラー: {e}")
            return False
    
    def start_receiver(self):
        """受信スレッド開始"""
        self.running = True
        threading.Thread(target=self._receive_loop, daemon=True).start()
        print("🎧 受信スレッド開始")
    
    def _receive_loop(self):
        """受信ループ"""
        buffer = bytearray()
        
        while self.running:
            try:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    if data:
                        buffer.extend(data)
                        hex_data = data.hex().upper()
                        timestamp = time.strftime("%H:%M:%S")
                        print(f"[{timestamp}] 📨 受信: {hex_data} ({len(data)}バイト)")
                        
                        # ACK検出
                        while len(buffer) >= 5:
                            if buffer[0] == 0x06:  # ACK
                                ack_msg = buffer[:5]
                                buffer = buffer[5:]
                                self._handle_ack(ack_msg)
                            else:
                                buffer = buffer[1:]  # 不正データ破棄
                
                time.sleep(0.1)
            except Exception as e:
                print(f"❌ 受信エラー: {e}")
                break
    
    def _handle_ack(self, ack_data: bytes):
        """ACK処理"""
        try:
            station = ack_data[1:5].decode('ascii')
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] ✅ ACK受信成功!")
            print(f"   データ: {ack_data.hex().upper()}")
            print(f"   局番号: {station}")
            self.received_data.append({
                'time': timestamp,
                'type': 'ACK',
                'data': ack_data.hex().upper(),
                'station': station
            })
        except Exception as e:
            print(f"❌ ACK解析エラー: {e}")
    
    def send_enq_command(self, data_num=0x0001, data_value=0x0001):
        """ENQコマンド送信"""
        if not self.ser or not self.ser.is_open:
            print("❌ シリアルポートが開いていません")
            return False
        
        try:
            # ENQメッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend("0001".encode('ascii'))  # 送信先局番号（自動運転装置）
            message.append(0x57)  # 'W'
            message.extend(f"{data_num:04X}".encode('ascii'))  # データ番号
            message.extend(f"{data_value:04X}".encode('ascii'))  # データ値
            
            # チェックサム計算
            checksum_data = message[1:]
            checksum = calculate_checksum(checksum_data)
            message.extend(checksum.encode('ascii'))
            
            # 送信
            self.ser.write(message)
            
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] 📤 ENQ送信: {message.hex().upper()}")
            
            # データ内容表示
            if data_num == 0x0001:
                desc = f"現在階数: {data_value}F"
            elif data_num == 0x0002:
                desc = f"行先階: {data_value}F" if data_value != 0 else "行先階: なし"
            elif data_num == 0x0003:
                desc = f"荷重: {data_value}kg"
            else:
                desc = f"データ番号: {data_num:04X}"
            
            print(f"   内容: {desc}")
            print(f"   チェックサム: {checksum}")
            
            return True
            
        except Exception as e:
            print(f"❌ ENQ送信エラー: {e}")
            return False
    
    def interactive_mode(self):
        """対話モード"""
        print("\n" + "="*60)
        print("SEC-3000H ENQコマンドテスト - 対話モード")
        print("="*60)
        print("コマンド:")
        print("  1 - 現在階数送信 (データ番号: 0001)")
        print("  2 - 行先階送信 (データ番号: 0002)")
        print("  3 - 荷重送信 (データ番号: 0003)")
        print("  s - 統計表示")
        print("  q - 終了")
        print("="*60)
        
        while True:
            try:
                cmd = input("\nコマンドを入力してください: ").strip().lower()
                
                if cmd == 'q':
                    break
                elif cmd == 's':
                    self._show_statistics()
                elif cmd == '1':
                    floor = input("現在階数を入力 (1-10, B1=65535): ")
                    try:
                        value = 65535 if floor.upper() == 'B1' else int(floor)
                        self.send_enq_command(0x0001, value)
                    except ValueError:
                        print("❌ 無効な階数です")
                elif cmd == '2':
                    floor = input("行先階を入力 (0=なし, 1-10, B1=65535): ")
                    try:
                        value = 65535 if floor.upper() == 'B1' else int(floor)
                        self.send_enq_command(0x0002, value)
                    except ValueError:
                        print("❌ 無効な階数です")
                elif cmd == '3':
                    weight = input("荷重を入力 (kg): ")
                    try:
                        value = int(weight)
                        self.send_enq_command(0x0003, value)
                    except ValueError:
                        print("❌ 無効な荷重です")
                else:
                    print("❌ 無効なコマンドです")
                    
            except KeyboardInterrupt:
                break
            except EOFError:
                break
    
    def _show_statistics(self):
        """統計表示"""
        print("\n" + "-"*40)
        print("📊 受信統計")
        print("-"*40)
        print(f"受信ACK数: {len(self.received_data)}")
        
        if self.received_data:
            print("\n最近の受信データ:")
            for i, data in enumerate(self.received_data[-5:], 1):
                print(f"  {i}. [{data['time']}] {data['type']} - 局番号:{data['station']} - {data['data']}")
        else:
            print("受信データなし")
        print("-"*40)
    
    def disconnect(self):
        """切断"""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        print("📡 シリアルポート切断")

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM27"
    
    print("="*60)
    print("SEC-3000H ENQコマンドテスト")
    print("="*60)
    print(f"ポート: {port}")
    print("設定: 9600bps, 8bit, Even parity, 1 stop bit")
    print("="*60)
    
    tester = SerialENQTester(port)
    
    try:
        if not tester.connect():
            sys.exit(1)
        
        tester.start_receiver()
        time.sleep(0.5)  # 受信スレッド開始待ち
        
        tester.interactive_mode()
        
    except KeyboardInterrupt:
        print("\n🛑 Ctrl+C で終了")
    finally:
        tester.disconnect()

if __name__ == "__main__":
    main()
