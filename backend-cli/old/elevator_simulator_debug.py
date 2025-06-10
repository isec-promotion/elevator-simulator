#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Simulator (デバッグ版)
Windows側でACK受信をデバッグ
"""

import serial
import time
import threading
import logging
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum

# ── 設定 ───────────────────────────────────
SERIAL_PORT = "COM27"  # Windows の場合

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

class ElevatorSimulatorDebug:
    """SEC-3000H エレベーターシミュレーター（デバッグ版）"""
    
    def __init__(self):
        self.serial_conn: Optional[serial.Serial] = None
        self.station_id = "0002"  # エレベーター側局番号
        self.auto_pilot_station = "0001"  # 自動運転装置側局番号
        self.running = False
        self.ack_received = False

    def initialize(self):
        """初期化"""
        logger.info("🏢 SEC-3000H Elevator Simulator (デバッグ版) 起動中...")
        logger.info(f"📡 シリアルポート設定: {SERIAL_CONFIG['port']}")

        try:
            self.serial_conn = serial.Serial(**SERIAL_CONFIG)
            logger.info(f"✅ シリアルポート {SERIAL_CONFIG['port']} 接続成功")
            
            # 受信スレッド開始
            self.running = True
            threading.Thread(target=self._listen_serial, daemon=True).start()
            logger.info("🎧 受信スレッド開始")
            
            return True
        except Exception as e:
            logger.error(f"❌ 初期化失敗: {e}")
            return False

    def _listen_serial(self):
        """シリアル受信処理（デバッグ強化版）"""
        buffer = bytearray()
        
        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        # 詳細デバッグログ
                        hex_data = data.hex().upper()
                        timestamp = time.strftime("%H:%M:%S")
                        logger.info(f"[{timestamp}] 🔍 Windows受信データ: {hex_data} ({len(data)}バイト)")
                        
                        buffer.extend(data)
                        
                        # バッファ内容をログ出力
                        if len(buffer) > 0:
                            logger.info(f"📦 バッファ内容: {buffer.hex().upper()} ({len(buffer)}バイト)")
                        
                        # ACK検出処理
                        self._process_buffer(buffer)
                
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"❌ シリアル受信エラー: {e}")
                break

    def _process_buffer(self, buffer: bytearray):
        """バッファ処理"""
        while len(buffer) >= 5:
            if buffer[0] == 0x06:  # ACK
                ack_message = buffer[:5]
                del buffer[:5]
                self._handle_ack_response(ack_message)
            elif buffer[0] == 0x05:  # ENQ
                if len(buffer) >= 16:
                    enq_message = buffer[:16]
                    del buffer[:16]
                    logger.info(f"📨 ENQ受信: {enq_message.hex().upper()}")
                else:
                    break
            else:
                # 不正データを1バイトずつ破棄
                discarded = buffer[0]
                del buffer[0]
                logger.warning(f"⚠️ 不正データ破棄: {discarded:02X}")

    def _handle_ack_response(self, data: bytes):
        """ACK応答処理（デバッグ強化版）"""
        try:
            timestamp = time.strftime("%H:%M:%S")
            hex_data = data.hex().upper()
            logger.info(f"[{timestamp}] ✅ ACK検出: {hex_data}")
            
            if len(data) >= 5 and data[0] == 0x06:
                station = data[1:5].decode('ascii')
                logger.info(f"   局番号: {station}")
                logger.info(f"   期待局番号: {self.station_id} または {self.auto_pilot_station}")
                
                # エコーバック対応：両方の局番号を受け入れ
                if station == self.station_id or station == self.auto_pilot_station:
                    logger.info(f"🎉 ACK受信成功! 局番号: {station}")
                    self.ack_received = True
                else:
                    logger.warning(f"⚠️ 予期しない局番号: {station}")
            else:
                logger.error(f"❌ 無効なACKフォーマット: {hex_data}")
                
        except Exception as e:
            logger.error(f"❌ ACK処理エラー: {e}")

    def _calculate_checksum(self, data: bytes) -> str:
        """チェックサム計算"""
        total = sum(data)
        lower_byte = total & 0xFF
        upper_byte = (total >> 8) & 0xFF
        checksum = (lower_byte + upper_byte) & 0xFF
        return f"{checksum:02X}"

    def send_enq_and_wait_ack(self, data_num: int, data_value: int) -> bool:
        """ENQ送信とACK待機（デバッグ版）"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        try:
            # メッセージ作成
            message = bytearray()
            message.append(0x05)  # ENQ
            message.extend(self.auto_pilot_station.encode('ascii'))  # 0001（送信先）
            message.append(0x57)  # 'W'
            message.extend(f"{data_num:04X}".encode('ascii'))
            message.extend(f"{data_value:04X}".encode('ascii'))
            
            # チェックサム計算
            checksum_data = message[1:]
            checksum = self._calculate_checksum(checksum_data)
            message.extend(checksum.encode('ascii'))

            # ACK受信フラグをリセット
            self.ack_received = False

            # 送信
            self.serial_conn.write(message)
            timestamp = time.strftime("%H:%M:%S")
            logger.info(f"[{timestamp}] 📤 ENQ送信: {message.hex().upper()}")
            
            # データ内容表示
            if data_num == DataNumbers.CURRENT_FLOOR:
                desc = f"現在階数: {data_value}F"
            elif data_num == DataNumbers.TARGET_FLOOR:
                desc = f"行先階: {data_value}F" if data_value != 0 else "行先階: なし"
            elif data_num == DataNumbers.LOAD_WEIGHT:
                desc = f"荷重: {data_value}kg"
            else:
                desc = f"データ番号: {data_num:04X}"
            
            logger.info(f"   内容: {desc}")
            logger.info(f"   チェックサム: {checksum}")

            # ACK応答待ち（3秒）
            logger.info("⏰ ACK応答待機中...")
            start_time = time.time()
            while time.time() - start_time < 3.0:
                if self.ack_received:
                    elapsed = time.time() - start_time
                    logger.info(f"✅ ACK受信成功! ({elapsed:.2f}秒)")
                    return True
                time.sleep(0.1)

            # タイムアウト
            logger.warning(f"⏰ ACK応答タイムアウト (3秒)")
            return False

        except Exception as e:
            logger.error(f"❌ ENQ送信エラー: {e}")
            return False

    def test_communication(self):
        """通信テスト"""
        logger.info("\n" + "="*60)
        logger.info("🧪 通信テスト開始")
        logger.info("="*60)
        
        # テスト1: 現在階数
        logger.info("\n📋 テスト1: 現在階数送信")
        success1 = self.send_enq_and_wait_ack(DataNumbers.CURRENT_FLOOR, 1)
        
        time.sleep(1)
        
        # テスト2: 行先階
        logger.info("\n📋 テスト2: 行先階送信")
        success2 = self.send_enq_and_wait_ack(DataNumbers.TARGET_FLOOR, 0)
        
        time.sleep(1)
        
        # テスト3: 荷重
        logger.info("\n📋 テスト3: 荷重送信")
        success3 = self.send_enq_and_wait_ack(DataNumbers.LOAD_WEIGHT, 100)
        
        # 結果表示
        logger.info("\n" + "="*60)
        logger.info("📊 テスト結果")
        logger.info("="*60)
        logger.info(f"現在階数: {'✅ 成功' if success1 else '❌ 失敗'}")
        logger.info(f"行先階: {'✅ 成功' if success2 else '❌ 失敗'}")
        logger.info(f"荷重: {'✅ 成功' if success3 else '❌ 失敗'}")
        
        total_success = sum([success1, success2, success3])
        logger.info(f"成功率: {total_success}/3 ({total_success/3*100:.1f}%)")
        
        return total_success == 3

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        logger.info("✅ システム終了完了")

def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'simulator' in globals():
        simulator.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Simulator (デバッグ版)')
    parser.add_argument('--port', default=SERIAL_PORT, help='シリアルポート')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # シリアルポート設定を更新
    SERIAL_CONFIG['port'] = args.port
    
    # シミュレーター初期化
    global simulator
    simulator = ElevatorSimulatorDebug()
    
    try:
        if not simulator.initialize():
            sys.exit(1)
        
        time.sleep(1)  # 初期化待ち
        
        # 通信テスト実行
        simulator.test_communication()
        
        logger.info("\n✅ デバッグテスト完了")
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Ctrl+C で終了")
    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
    finally:
        simulator.shutdown()

if __name__ == "__main__":
    main()
