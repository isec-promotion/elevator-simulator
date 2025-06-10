#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Auto Pilot Receiver (Working Version)
自動運転装置側受信機（局番号: 0001）
エレベーターからの状態データを受信してACK応答送信
"""

import serial
import time
import threading
import logging
import signal
import sys
import socket
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "/dev/ttyUSB0"  # Raspberry Pi の場合
# SERIAL_PORT = "COM27"  # Windows の場合

SERIAL_CONFIG = {
    'port': SERIAL_PORT,
    'baudrate': 9600,
    'bytesize': serial.EIGHTBITS,
    'parity': serial.PARITY_EVEN,
    'stopbits': serial.STOPBITS_ONE,
    'timeout': 1
}

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── SEC-3000H データ番号定義 ─────────────────
class DataNumbers(IntEnum):
    CURRENT_FLOOR = 0x0001  # 現在階数
    TARGET_FLOOR = 0x0002   # 行先階
    LOAD_WEIGHT = 0x0003    # 荷重
    FLOOR_SETTING = 0x0010  # 階数設定（送信用）
    DOOR_CONTROL = 0x0011   # 扉制御（送信用）

# ── 扉制御コマンド ─────────────────────────────
class DoorCommands(IntEnum):
    STOP = 0x0000   # 停止
    OPEN = 0x0001   # 開扉
    CLOSE = 0x0002  # 閉扉

# ── エレベーター状態 ───────────────────────────
class ElevatorStatus:
    def __init__(self):
        self.current_floor = "1F"
        self.target_floor = None
        self.load_weight = 0
        self.last_update = None
        self.communication_active = False

class AutoPilotReceiver:
    """SEC-3000H 自動運転装置受信機"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.status = ElevatorStatus()
        self.station_id = "0001"  # 自動運転装置側局番号
        self.elevator_station = "0002"  # エレベーター側局番号
        self.running = False
        self.lock = threading.Lock()
        self.local_ip = self._get_local_ip()

    def _get_local_ip(self) -> str:
        """ローカルIPアドレスを取得"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def initialize(self):
        """初期化"""
        logger.info("🤖 SEC-3000H Auto Pilot Receiver 起動中...")
        logger.info(f"📡 シリアルポート設定: {SERIAL_PORT}")
        logger.info(f"🏷️ 局番号: {self.station_id} (自動運転装置側)")
        logger.info(f"🎯 受信元: {self.elevator_station} (エレベーター側)")

        try:
            self._connect_serial()
            logger.info("✅ 初期化完了")
            return True
        except Exception as e:
            logger.error(f"❌ 初期化失敗: {e}")
            return False

    def _connect_serial(self):
        """シリアルポート接続"""
        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            logger.info(f"✅ シリアルポート {SERIAL_PORT} 接続成功")
            
        except Exception as e:
            logger.error(f"❌ シリアルポートエラー: {e}")
            raise

    def _listen_serial(self):
        """シリアル受信処理（エレベーターからのデータ受信）"""
        buffer = bytearray()
        
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        # デバッグログ
                        hex_data = data.hex().upper()
                        logger.info(f"🔍 受信データ: {hex_data} ({len(data)}バイト)")
                        buffer.extend(data)
                    
                    # ENQ(05H)で始まるメッセージを検索
                    while len(buffer) >= 16:
                        enq_pos = buffer.find(0x05)
                        if enq_pos == -1:
                            # ENQが見つからない場合、バッファをクリア
                            if len(buffer) > 0:
                                logger.warning(f"⚠️ ENQなしデータ破棄: {buffer.hex().upper()}")
                            buffer.clear()
                            break
                        
                        if enq_pos > 0:
                            # ENQ前のデータを破棄
                            discarded = buffer[:enq_pos]
                            logger.warning(f"⚠️ ENQ前データ破棄: {discarded.hex().upper()}")
                            buffer = buffer[enq_pos:]
                        
                        if len(buffer) >= 16:
                            message = buffer[:16]
                            buffer = buffer[16:]
                            # デバッグログ
                            hex_msg = message.hex().upper()
                            logger.info(f"📦 メッセージ処理: {hex_msg}")
                            self._handle_received_data(message)
                        else:
                            break
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _handle_received_data(self, data: bytes):
        """受信データ処理（エレベーターからの状態データ）"""
        try:
            if len(data) < 16 or data[0] != 0x05:
                logger.warning(f"⚠️ 無効なメッセージ: {data.hex().upper()}")
                return

            # メッセージ解析
            try:
                station = data[1:5].decode('ascii')
                command = chr(data[5])
                data_num_str = data[6:10].decode('ascii')
                data_value_str = data[10:14].decode('ascii')
                checksum = data[14:16].decode('ascii')
            except UnicodeDecodeError as e:
                logger.error(f"❌ デコードエラー: {e}, データ: {data.hex().upper()}")
                return

            logger.info(f"🔍 解析結果: 局番号={station}, CMD={command}, データ番号={data_num_str}, データ値={data_value_str}, チェックサム={checksum}")

            # 自分宛のメッセージかチェック
            if station != self.station_id:
                logger.info(f"ℹ️ 他局宛メッセージ: {station} (自分: {self.station_id})")
                return

            try:
                data_num = int(data_num_str, 16)
                data_value = int(data_value_str, 16)
            except ValueError as e:
                logger.error(f"❌ 数値変換エラー: {e}, データ番号={data_num_str}, データ値={data_value_str}")
                return

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

            # データ処理
            with self.lock:
                self.status.last_update = datetime.now()
                self.status.communication_active = True

                if data_num == DataNumbers.CURRENT_FLOOR:
                    # 現在階数
                    current_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                    self.status.current_floor = current_floor
                    description = f"現在階数: {current_floor}"
                    
                elif data_num == DataNumbers.TARGET_FLOOR:
                    # 行先階
                    if data_value == 0x0000:
                        self.status.target_floor = None
                        description = "行先階: なし"
                    else:
                        target_floor = "B1F" if data_value == 0xFFFF else f"{data_value}F"
                        self.status.target_floor = target_floor
                        description = f"行先階: {target_floor}"
                    
                elif data_num == DataNumbers.LOAD_WEIGHT:
                    # 荷重
                    self.status.load_weight = data_value
                    description = f"荷重: {data_value}kg"
                else:
                    description = f"データ番号: {data_num:04X}"

            logger.info(
                f"[{timestamp}] 📨 受信: ENQ(05) 局番号:{self.elevator_station} CMD:{command} "
                f"{description} データ:{data_value_str} チェックサム:{checksum}"
            )

            # ACK応答送信
            self._send_ack_response()

        except Exception as e:
            logger.error(f"❌ 受信データ処理エラー: {e}, データ: {data.hex().upper()}")

    def _send_ack_response(self):
        """ACK応答送信"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            response = bytearray([0x06])  # ACK
            response.extend(self.elevator_station.encode('ascii'))  # 0002

            self.serial_conn.write(response)

            timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            hex_data = response.hex().upper()
            logger.info(f"[{timestamp}] 📤 ACK送信: {hex_data}")

        except Exception as e:
            logger.error(f"❌ ACK送信エラー: {e}")

    def start_receiver(self):
        """受信開始"""
        if self.running:
            logger.info("⚠️ 受信は既に実行中です")
            return

        logger.info("🎧 エレベーターデータ受信開始")
        logger.info(f"📊 受信データ: 現在階数(0001), 行先階(0002), 荷重(0003)")
        self.running = True

        # 受信スレッド開始
        threading.Thread(target=self._listen_serial, daemon=True).start()

    def stop_receiver(self):
        """受信停止"""
        logger.info("🛑 データ受信停止")
        self.running = False

    def _display_status(self):
        """状態表示"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

        with self.lock:
            current_floor = self.status.current_floor
            target_floor = self.status.target_floor or "-"
            load_weight = self.status.load_weight
            last_update = self.status.last_update
            communication_active = self.status.communication_active

        # 通信状態チェック
        if last_update:
            time_diff = (datetime.now() - last_update).total_seconds()
            comm_status = "正常" if time_diff < 10 else "タイムアウト"
        else:
            comm_status = "未受信"

        logger.info(f"\n[{timestamp}] 📊 エレベーター状態")
        logger.info(f"現在階: {current_floor}")
        logger.info(f"行先階: {target_floor}")
        logger.info(f"荷重: {load_weight}kg")
        logger.info(f"通信状態: {comm_status}")
        if last_update:
            logger.info(f"最終更新: {last_update.strftime('%H:%M:%S')}")

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.running:
                self._display_status()
                threading.Timer(30.0, _status_timer).start()

        _status_timer()

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")

        self.stop_receiver()

        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("📡 シリアルポート切断完了")

        logger.info("✅ システム終了完了")

# ── メイン処理 ─────────────────────────────────
def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'receiver' in globals():
        receiver.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Auto Pilot Receiver (Working)')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定を更新
    SERIAL_CONFIG['port'] = args.port
    
    # 自動運転装置受信機初期化
    global receiver
    receiver = AutoPilotReceiver()
    
    try:
        # 初期化
        if not receiver.initialize():
            sys.exit(1)
        
        # 受信開始
        receiver.start_receiver()
        
        # 定期状態表示開始
        receiver.start_status_display()
        
        logger.info("\n✅ 自動運転装置受信機稼働中 (Ctrl+C で終了)")
        
        # メインループ
        while receiver.running:
            time.sleep(1)

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        receiver.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
