#!/usr/bin/env python3
"""
Raspberry Pi 4B シリアル信号受信プログラム
エレベーター（PC）からRS422経由で送信されるシリアル信号を受信し、ターミナルに表示します。

システム構成:
PC（エレベーター） → USB-RS422 → Raspberry Pi 4B → MQTT → 監視室PC
                                    ↑ このプログラム
"""

import serial
import sys
import time
from datetime import datetime
import signal

# 設定
SERIAL_PORT = '/dev/ttyUSB0'  # RS422-USB変換器のデバイス
BAUDRATE = 9600
DATABITS = 8
PARITY = 'E'  # Even parity
STOPBITS = 1
TIMEOUT = 1.0

class SerialReceiver:
    def __init__(self):
        self.serial_connection = None
        self.running = False
        
    def connect(self):
        """シリアルポートに接続"""
        try:
            self.serial_connection = serial.Serial(
                port=SERIAL_PORT,
                baudrate=BAUDRATE,
                bytesize=DATABITS,
                parity=PARITY,
                stopbits=STOPBITS,
                timeout=TIMEOUT
            )
            print(f"✅ シリアルポート接続成功: {SERIAL_PORT}")
            print(f"   設定: {BAUDRATE}bps, {DATABITS}bit, パリティ:{PARITY}, ストップビット:{STOPBITS}")
            print("-" * 80)
            return True
        except Exception as e:
            print(f"❌ シリアルポート接続エラー: {e}")
            return False
    
    def format_hex_data(self, data):
        """バイトデータを16進数文字列に変換"""
        return ' '.join([f'{byte:02X}' for byte in data])
    
    def parse_elevator_command(self, data):
        """エレベーターコマンドを解析"""
        if len(data) < 10:
            return "不完全なデータ"
        
        try:
            # プロトコル解析
            enq = data[0]
            station = data[1:5].decode('ascii')
            command = chr(data[5])
            data_num = data[6:10].decode('ascii')
            
            if len(data) >= 14:
                command_data = data[10:14].decode('ascii')
            else:
                command_data = "N/A"
            
            if len(data) >= 16:
                checksum = data[14:16].decode('ascii')
            else:
                checksum = "N/A"
            
            # データ番号の解釈
            data_description = ""
            try:
                data_num_int = int(data_num)
                if data_num_int == 0x0010:
                    floor_value = int(command_data, 16)
                    floor_name = "B1F" if floor_value == 0xffff else f"{floor_value}F"
                    data_description = f"階数設定: {floor_name}"
                elif data_num_int == 0x0011:
                    door_value = int(command_data, 16)
                    if door_value == 0x0001:
                        data_description = "扉制御: 開扉"
                    elif door_value == 0x0002:
                        data_description = "扉制御: 閉扉"
                    elif door_value == 0x0000:
                        data_description = "扉制御: 停止"
                    else:
                        data_description = f"扉制御: 不明({door_value:04X})"
                elif data_num_int == 0x0003:
                    weight_value = int(command_data, 16)
                    data_description = f"荷重設定: {weight_value}kg"
                else:
                    data_description = f"データ番号: {data_num}"
            except ValueError:
                data_description = f"データ番号: {data_num}"
            
            return f"ENQ:{enq:02X} 局番号:{station} CMD:{command} {data_description} データ:{command_data} チェックサム:{checksum}"
            
        except Exception as e:
            return f"解析エラー: {e}"
    
    def start_receiving(self):
        """シリアル受信を開始"""
        if not self.serial_connection:
            print("❌ シリアルポートが接続されていません")
            return
        
        self.running = True
        print("📡 シリアル信号受信を開始します...")
        print("   Ctrl+C で停止")
        print("=" * 80)
        
        try:
            while self.running:
                if self.serial_connection.in_waiting > 0:
                    # データを受信
                    data = self.serial_connection.read(self.serial_connection.in_waiting)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    # 16進数表示
                    hex_data = self.format_hex_data(data)
                    
                    # コマンド解析
                    parsed_command = self.parse_elevator_command(data)
                    
                    # ターミナルに表示
                    print(f"[{timestamp}] 受信データ ({len(data)}バイト)")
                    print(f"  HEX: {hex_data}")
                    print(f"  解析: {parsed_command}")
                    print("-" * 80)
                    
                    # 応答送信（ACK）
                    if len(data) >= 5 and data[0] == 0x05:  # ENQで始まる場合
                        try:
                            station = data[1:5].decode('ascii')
                            # ACK応答を作成
                            ack_response = bytearray([0x06])  # ACK
                            ack_response.extend(station.encode('ascii'))
                            
                            self.serial_connection.write(ack_response)
                            print(f"  → ACK応答送信: {self.format_hex_data(ack_response)}")
                            print("-" * 80)
                        except Exception as e:
                            print(f"  ⚠️ ACK応答送信エラー: {e}")
                
                # 短い間隔で待機
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\n📡 受信を停止します...")
        except Exception as e:
            print(f"❌ 受信エラー: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """受信を停止"""
        self.running = False
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            print("✅ シリアルポートを閉じました")

def signal_handler(signum, frame):
    """シグナルハンドラー"""
    print(f"\n📡 シグナル {signum} を受信しました。プログラムを終了します...")
    receiver.stop()
    sys.exit(0)

def main():
    global receiver
    
    print("🚀 Raspberry Pi 4B シリアル信号受信プログラム")
    print("=" * 80)
    print("システム構成:")
    print("PC（エレベーター） → USB-RS422 → Raspberry Pi 4B → MQTT → 監視室PC")
    print("                                    ↑ このプログラム")
    print("=" * 80)
    
    # シグナルハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    receiver = SerialReceiver()
    
    # シリアルポートに接続
    if not receiver.connect():
        print("❌ シリアルポート接続に失敗しました")
        print("\n🔧 トラブルシューティング:")
        print("1. RS422-USB変換器が接続されているか確認")
        print("2. デバイスファイルの確認: ls -la /dev/ttyUSB*")
        print("3. 権限の確認: sudo usermod -a -G dialout pi")
        print("4. 再起動: sudo reboot")
        sys.exit(1)
    
    # 受信開始
    try:
        receiver.start_receiving()
    except Exception as e:
        print(f"❌ 予期しないエラー: {e}")
    finally:
        receiver.stop()

if __name__ == "__main__":
    main()
