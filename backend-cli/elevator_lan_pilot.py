#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Auto Pilot - LAN Network Connection
PCとRaspberry Pi 4をLAN経由で通信してエレベーター自動操縦
"""

import socket
import time
import logging
import threading
import signal
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any
from enum import IntEnum

# ── 設定 ───────────────────────────────────
# LAN接続設定
PC_IP = "192.168.40.184"
RASPBERRY_PI_IP = "192.168.40.239"
COMMUNICATION_PORT = 8888
DISCOVERY_PORT = 8889

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
    FLOOR_SETTING = 0x0010  # 階数設定
    DOOR_CONTROL = 0x0011   # 扉制御

# ── 扉制御コマンド ─────────────────────────────
class DoorCommands(IntEnum):
    STOP = 0x0000   # 停止
    OPEN = 0x0001   # 開扉
    CLOSE = 0x0002  # 閉扉

# ── エレベーター状態 ───────────────────────────
class ElevatorState:
    def __init__(self):
        self.current_floor = "1F"
        self.target_floor = None
        self.load_weight = 0
        self.is_moving = False
        self.door_status = "unknown"

# ── 自動運転シーケンス ─────────────────────────
AUTO_SEQUENCE = ["B1F", "1F", "2F", "3F", "4F", "5F"]

class ElevatorLANPilot:
    """LAN通信エレベーター自動操縦クラス"""
    
    def __init__(self, raspberry_pi_ip: str = RASPBERRY_PI_IP):
        self.raspberry_pi_ip = raspberry_pi_ip
        self.communication_port = COMMUNICATION_PORT
        self.discovery_port = DISCOVERY_PORT
        
        self.tcp_socket: Optional[socket.socket] = None
        self.state = ElevatorState()
        self.sequence_index = 0
        self.is_running = False
        self.status_broadcast_timer: Optional[threading.Timer] = None
        self.operation_timer: Optional[threading.Timer] = None
        self.lock = threading.Lock()
        self.connected = False

    def discover_raspberry_pi(self) -> Optional[str]:
        """Raspberry Pi 4をネットワーク上で自動発見"""
        logger.info("🔍 ネットワーク上でRaspberry Pi 4を検索中...")
        
        try:
            # UDP ブロードキャストで発見
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_socket.settimeout(3.0)
            
            # 発見メッセージを送信
            discovery_message = {
                "type": "discover",
                "sender": "elevator_pilot",
                "timestamp": datetime.now().isoformat()
            }
            
            message_data = json.dumps(discovery_message).encode('utf-8')
            
            # ブロードキャスト送信
            broadcast_address = "192.168.40.255"  # ネットワークに応じて調整
            udp_socket.sendto(message_data, (broadcast_address, self.discovery_port))
            logger.info(f"📡 発見メッセージをブロードキャスト: {broadcast_address}:{self.discovery_port}")
            
            # 応答を待機
            try:
                response_data, addr = udp_socket.recvfrom(1024)
                response = json.loads(response_data.decode('utf-8'))
                
                if response.get("type") == "discover_response" and response.get("device") == "raspberry_pi_elevator":
                    discovered_ip = addr[0]
                    logger.info(f"✅ Raspberry Pi 4を発見: {discovered_ip}")
                    udp_socket.close()
                    return discovered_ip
                    
            except socket.timeout:
                logger.warning("⚠️ 発見タイムアウト、指定IPアドレスを使用します")
            
            udp_socket.close()
            
        except Exception as e:
            logger.error(f"❌ 自動発見エラー: {e}")
        
        # 自動発見に失敗した場合、指定IPを返す
        logger.info(f"📍 指定IPアドレスを使用: {self.raspberry_pi_ip}")
        return self.raspberry_pi_ip

    def connect_lan(self) -> bool:
        """LAN接続"""
        try:
            # Raspberry Pi 4を発見
            target_ip = self.discover_raspberry_pi()
            if not target_ip:
                return False
            
            # TCP接続
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5.0)
            
            logger.info(f"🔌 {target_ip}:{self.communication_port} に接続中...")
            self.tcp_socket.connect((target_ip, self.communication_port))
            
            logger.info(f"✅ LAN接続成功: {target_ip}:{self.communication_port}")
            logger.info(f"📡 通信設定: TCP/IP, JSON形式")
            
            self.connected = True
            
            # 受信スレッド開始
            threading.Thread(target=self._listen_lan, daemon=True).start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ LAN接続エラー: {e}")
            return False

    def _listen_lan(self):
        """LAN受信処理"""
        buffer = ""
        while self.connected and self.tcp_socket:
            try:
                self.tcp_socket.settimeout(5.0)  # タイムアウト設定
                data = self.tcp_socket.recv(1024).decode('utf-8')
                if not data:
                    logger.warning("⚠️ 接続が切断されました")
                    self.connected = False
                    break
                
                buffer += data
                
                # 改行区切りでメッセージを分割
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self._handle_lan_message(line.strip())
                
            except socket.timeout:
                # タイムアウトは正常（ハートビート的な動作）
                continue
            except Exception as e:
                logger.error(f"❌ LAN受信エラー: {e}")
                self.connected = False
                break

    def _handle_lan_message(self, message: str):
        """LAN受信メッセージ処理"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "status_update":
                # Raspberry Pi 4からの状態更新
                with self.lock:
                    if "current_floor" in data:
                        self.state.current_floor = data["current_floor"]
                    if "target_floor" in data:
                        self.state.target_floor = data["target_floor"]
                    if "load_weight" in data:
                        self.state.load_weight = data["load_weight"]
                    if "is_moving" in data:
                        self.state.is_moving = data["is_moving"]
                
                logger.info(f"📊 状態更新: 現在階={self.state.current_floor}, 行先階={self.state.target_floor}")
                
            elif msg_type == "ack":
                logger.info(f"✅ ACK受信: {data.get('command', 'unknown')}")
                
            elif msg_type == "error":
                logger.error(f"❌ エラー受信: {data.get('message', 'unknown error')}")
                
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ 無効なJSONメッセージ: {message}")

    def send_lan_command(self, command_type: str, **kwargs) -> bool:
        """LANコマンド送信"""
        if not self.connected or not self.tcp_socket:
            logger.error("❌ LAN接続が確立されていません")
            return False
        
        try:
            message = {
                "type": command_type,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
            
            json_message = json.dumps(message) + '\n'
            self.tcp_socket.send(json_message.encode('utf-8'))
            
            logger.info(f"📤 LAN送信: {command_type} - {kwargs}")
            return True
            
        except Exception as e:
            logger.error(f"❌ LAN送信エラー: {e}")
            self.connected = False
            return False

    def set_floor(self, floor: str) -> bool:
        """階数設定"""
        return self.send_lan_command("set_floor", floor=floor)

    def control_door(self, action: str) -> bool:
        """扉制御"""
        return self.send_lan_command("door_control", action=action)

    def start_auto_pilot(self):
        """自動運転開始"""
        if self.is_running:
            logger.info("⚠️ 自動運転は既に実行中です")
            return

        logger.info("🚀 LAN通信自動運転開始")
        logger.info(f"🏢 運転シーケンス: {' → '.join(AUTO_SEQUENCE)}")
        logger.info(f"🌐 通信先: {self.raspberry_pi_ip}:{self.communication_port}")
        self.is_running = True

        # 初期位置を1Fに設定
        logger.info("🏢 初期位置を1Fに設定中...")
        self.set_floor("1F")
        time.sleep(2)

        # 自動運転ループ開始
        self._execute_auto_pilot_loop()

    def _execute_auto_pilot_loop(self):
        """自動運転ループ"""
        if not self.is_running or not self.connected:
            return

        try:
            target_floor = AUTO_SEQUENCE[self.sequence_index]

            with self.lock:
                current_floor = self.state.current_floor

            logger.info(f"\n🎯 次の目標階: {target_floor} (現在: {current_floor})")

            # 1. 扉を閉める
            logger.info("🚪 扉を閉めています...")
            self.control_door("close")
            time.sleep(3)

            # 2. 目標階に移動
            logger.info(f"🚀 {target_floor}に移動中...")
            with self.lock:
                self.state.is_moving = True
            self.set_floor(target_floor)
            time.sleep(5)  # 移動時間

            # 3. 到着
            logger.info(f"✅ {target_floor}に到着")
            with self.lock:
                self.state.current_floor = target_floor
                self.state.is_moving = False

            # 4. 扉を開ける
            logger.info("🚪 扉を開いています...")
            self.control_door("open")
            time.sleep(3)

            # 5. 乗客の出入り時間
            logger.info("👥 乗客の出入り中...")
            time.sleep(5)

            # 次の階へ
            self.sequence_index = (self.sequence_index + 1) % len(AUTO_SEQUENCE)

            # 次のサイクルをスケジュール
            if self.is_running and self.connected:
                self.operation_timer = threading.Timer(2.0, self._execute_auto_pilot_loop)
                self.operation_timer.start()

        except Exception as e:
            logger.error(f"❌ 自動運転エラー: {e}")
            # エラー時は少し待ってから再試行
            if self.is_running and self.connected:
                self.operation_timer = threading.Timer(5.0, self._execute_auto_pilot_loop)
                self.operation_timer.start()

    def stop_auto_pilot(self):
        """自動運転停止"""
        logger.info("🛑 自動運転停止")
        self.is_running = False

        if self.operation_timer:
            self.operation_timer.cancel()
            self.operation_timer = None

    def _display_status(self):
        """状態表示"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

        with self.lock:
            current_floor = self.state.current_floor
            target_floor = self.state.target_floor or "-"
            load_weight = self.state.load_weight
            is_moving = "はい" if self.state.is_moving else "いいえ"
            door_status = self.state.door_status

        logger.info(f"\n[{timestamp}] 📊 エレベーター状態")
        logger.info(f"現在階: {current_floor}")
        logger.info(f"行先階: {target_floor}")
        logger.info(f"荷重: {load_weight}kg")
        logger.info(f"移動中: {is_moving}")
        logger.info(f"扉状態: {door_status}")
        logger.info(f"LAN接続: {'接続中' if self.connected else '切断'}")
        logger.info(f"通信先: {self.raspberry_pi_ip}:{self.communication_port}")

    def start_status_display(self):
        """定期状態表示開始"""
        def _status_timer():
            if self.is_running:
                self._display_status()
                self.status_broadcast_timer = threading.Timer(30.0, _status_timer)
                self.status_broadcast_timer.start()

        _status_timer()

    def disconnect_lan(self):
        """LAN切断"""
        self.connected = False
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None
        logger.info("📡 LAN接続を切断しました")

    def shutdown(self):
        """終了処理"""
        logger.info("🛑 システム終了中...")

        self.stop_auto_pilot()

        if self.status_broadcast_timer:
            self.status_broadcast_timer.cancel()

        self.disconnect_lan()
        logger.info("✅ システム終了完了")

# ── メイン処理 ─────────────────────────────────
def signal_handler(signum, frame):
    """シグナルハンドラー"""
    logger.info(f"\n🛑 シグナル {signum} を受信しました")
    if 'pilot' in globals():
        pilot.shutdown()
    sys.exit(0)

def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Auto Pilot - LAN Network Connection')
    parser.add_argument('--raspberry-pi-ip', default=RASPBERRY_PI_IP, help='Raspberry Pi 4のIPアドレス')
    parser.add_argument('--port', type=int, default=COMMUNICATION_PORT, help='通信ポート番号')
    parser.add_argument('--manual', action='store_true', help='手動モード（自動運転しない）')
    args = parser.parse_args()
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🚀 SEC-3000H Elevator Auto Pilot - LAN Network Connection")
    logger.info("🌐 PCとRaspberry Pi 4のLAN通信版")
    logger.info("=" * 60)
    logger.info(f"🖥️ PC IP: {PC_IP}")
    logger.info(f"🍓 Raspberry Pi IP: {args.raspberry_pi_ip}")
    logger.info(f"🔌 通信ポート: {args.port}")
    logger.info("=" * 60)
    
    # LAN操縦システム初期化
    global pilot
    pilot = ElevatorLANPilot(raspberry_pi_ip=args.raspberry_pi_ip)
    pilot.communication_port = args.port
    
    try:
        # LAN接続
        if not pilot.connect_lan():
            logger.error("❌ Raspberry Pi 4との接続に失敗しました")
            sys.exit(1)
        
        if not args.manual:
            # 定期状態表示開始
            pilot.start_status_display()
            
            # 自動運転開始
            pilot.start_auto_pilot()
            
            logger.info("\n✅ 自動運転システム稼働中 (Ctrl+C で終了)")
        else:
            logger.info("\n✅ 手動モードで待機中 (Ctrl+C で終了)")
        
        # メインループ（再接続機能付き）
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        reconnect_delay = 5  # 秒
        
        while pilot.is_running:
            if pilot.connected:
                reconnect_attempts = 0  # 接続成功時はカウンターリセット
                time.sleep(1)
            else:
                # 接続が切断された場合の再接続処理
                if reconnect_attempts < max_reconnect_attempts:
                    reconnect_attempts += 1
                    logger.warning(f"🔄 再接続試行 {reconnect_attempts}/{max_reconnect_attempts}")
                    logger.info(f"⏳ {reconnect_delay}秒後に再接続します...")
                    time.sleep(reconnect_delay)
                    
                    # 再接続試行
                    if pilot.connect_lan():
                        logger.info("✅ 再接続成功")
                        # 自動運転が停止していた場合は再開
                        if not args.manual and not pilot.is_running:
                            pilot.start_auto_pilot()
                    else:
                        logger.error(f"❌ 再接続失敗 ({reconnect_attempts}/{max_reconnect_attempts})")
                        # 再接続間隔を徐々に延長
                        reconnect_delay = min(reconnect_delay * 1.5, 30)
                else:
                    logger.error("❌ 最大再接続試行回数に達しました")
                    break
        
        if not pilot.connected:
            logger.error("❌ 接続が切断されました")

    except Exception as e:
        logger.error(f"❌ システムエラー: {e}")
        pilot.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
