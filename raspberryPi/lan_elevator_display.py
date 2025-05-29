#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEC-3000H Elevator Display - LAN Network Connection
PCとRaspberry Pi 4をLAN経由で通信してエレベーター案内ディスプレイ
"""

import socket
import time
import json
import logging
import threading
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional

from PIL import Image, ImageDraw, ImageFont
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

# ── 設定 ───────────────────────────────────
WIDTH, HEIGHT, FPS = 640, 360, 15
COMMUNICATION_PORT = 8888
DISCOVERY_PORT = 8889
FONT_PATH = "/usr/share/fonts/truetype/ipafont-mincho/ipam.ttf"

# ── ログ設定 ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── LAN通信受信クラス ───────────────────────
class LANElevatorReceiver:
    """LAN通信エレベーター受信クラス"""
    
    def __init__(self, port: int = COMMUNICATION_PORT, discovery_port: int = DISCOVERY_PORT):
        self.port = port
        self.discovery_port = discovery_port
        self.tcp_server: Optional[socket.socket] = None
        self.udp_server: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.running = False
        self.current_status = {
            'current_floor': '1F',
            'target_floor': None,
            'is_moving': False,
            'door_status': 'unknown',
            'load_weight': 0,
            'last_communication': None
        }
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

    def start_discovery_server(self):
        """発見サーバー開始（UDP）"""
        try:
            self.udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_server.bind(('', self.discovery_port))
            
            logger.info(f"🔍 発見サーバー開始: UDP {self.local_ip}:{self.discovery_port}")
            
            # 発見サーバースレッド開始
            threading.Thread(target=self._discovery_server_loop, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ 発見サーバー開始エラー: {e}")

    def _discovery_server_loop(self):
        """発見サーバーループ"""
        while self.running and self.udp_server:
            try:
                data, addr = self.udp_server.recvfrom(1024)
                message = json.loads(data.decode('utf-8'))
                
                if message.get("type") == "discover" and message.get("sender") == "elevator_pilot":
                    logger.info(f"🔍 発見要求を受信: {addr[0]}")
                    
                    # 応答メッセージ
                    response = {
                        "type": "discover_response",
                        "device": "raspberry_pi_elevator",
                        "ip": self.local_ip,
                        "port": self.port,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    response_data = json.dumps(response).encode('utf-8')
                    self.udp_server.sendto(response_data, addr)
                    logger.info(f"📡 発見応答を送信: {addr[0]}")
                    
            except Exception as e:
                if self.running:
                    logger.error(f"❌ 発見サーバーエラー: {e}")

    def start_tcp_server(self) -> bool:
        """TCPサーバー開始"""
        try:
            self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_server.bind(('', self.port))
            self.tcp_server.listen(1)
            
            logger.info(f"🌐 TCPサーバー開始: {self.local_ip}:{self.port}")
            logger.info("⏳ PC接続を待機中...")
            
            # 接続受付スレッド開始
            threading.Thread(target=self._accept_connections, daemon=True).start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ TCPサーバー開始エラー: {e}")
            return False

    def _accept_connections(self):
        """接続受付"""
        while self.running and self.tcp_server:
            try:
                client_socket, addr = self.tcp_server.accept()
                logger.info(f"✅ PC接続受付: {addr[0]}:{addr[1]}")
                
                # 既存の接続があれば切断
                if self.client_socket:
                    try:
                        self.client_socket.close()
                    except:
                        pass
                
                self.client_socket = client_socket
                
                # クライアント通信スレッド開始
                threading.Thread(target=self._handle_client, args=(client_socket, addr), daemon=True).start()
                
            except Exception as e:
                if self.running:
                    logger.error(f"❌ 接続受付エラー: {e}")

    def _handle_client(self, client_socket: socket.socket, addr):
        """クライアント通信処理"""
        buffer = ""
        try:
            while self.running:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    logger.warning(f"⚠️ PC接続切断: {addr[0]}")
                    break
                
                buffer += data
                
                # 改行区切りでメッセージを分割
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        self._handle_lan_command(line.strip(), client_socket)
                        
        except Exception as e:
            logger.error(f"❌ クライアント通信エラー: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            if self.client_socket == client_socket:
                self.client_socket = None

    def send_lan_message(self, message_type: str, **kwargs) -> bool:
        """LANメッセージ送信"""
        if not self.client_socket:
            return False
        
        try:
            message = {
                "type": message_type,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
            
            json_message = json.dumps(message) + '\n'
            self.client_socket.send(json_message.encode('utf-8'))
            return True
            
        except Exception as e:
            logger.error(f"❌ LAN送信エラー: {e}")
            return False

    def _handle_lan_command(self, message: str, client_socket: socket.socket):
        """LAN受信コマンド処理"""
        try:
            data = json.loads(message)
            command_type = data.get("type")
            timestamp = data.get("timestamp")
            
            logger.info(f"📨 LAN受信: {command_type}")
            
            if command_type == "set_floor":
                floor = data.get("floor")
                if floor:
                    with self.lock:
                        old_floor = self.current_status['current_floor']
                        if old_floor != floor:
                            self.current_status['target_floor'] = floor
                            self.current_status['is_moving'] = True
                            logger.info(f"🎯 移動指示: {old_floor} → {floor}")
                        else:
                            self.current_status['target_floor'] = None
                            self.current_status['is_moving'] = False
                            logger.info(f"🏢 同一階設定: {floor}")
                    
                    # ACK応答
                    self.send_lan_message("ack", command="set_floor", floor=floor)
                    
                    # 移動シミュレーション
                    if self.current_status['is_moving']:
                        threading.Thread(target=self._simulate_movement, args=(floor,), daemon=True).start()
                
            elif command_type == "door_control":
                action = data.get("action")
                if action:
                    with self.lock:
                        if action == "open":
                            self.current_status['door_status'] = 'opening'
                            # 扉開放時に移動完了
                            if self.current_status['target_floor']:
                                self.current_status['current_floor'] = self.current_status['target_floor']
                                self.current_status['target_floor'] = None
                                self.current_status['is_moving'] = False
                                logger.info(f"🏢 扉開放により到着完了: {self.current_status['current_floor']}")
                        elif action == "close":
                            self.current_status['door_status'] = 'closing'
                        else:
                            self.current_status['door_status'] = 'unknown'
                    
                    logger.info(f"🚪 扉制御: {action}")
                    
                    # ACK応答
                    self.send_lan_message("ack", command="door_control", action=action)
            
            # 状態更新を送信
            self._send_status_update()
            
        except json.JSONDecodeError:
            logger.warning(f"⚠️ 無効なJSONメッセージ: {message}")
        except Exception as e:
            logger.error(f"❌ コマンド処理エラー: {e}")
            self.send_lan_message("error", message=str(e))

    def _simulate_movement(self, target_floor: str):
        """移動シミュレーション"""
        time.sleep(3)  # 移動時間
        
        with self.lock:
            if self.current_status['is_moving'] and self.current_status['target_floor'] == target_floor:
                self.current_status['current_floor'] = target_floor
                self.current_status['target_floor'] = None
                self.current_status['is_moving'] = False
                logger.info(f"✅ 移動完了: {target_floor}")
                
        self._send_status_update()

    def _send_status_update(self):
        """状態更新送信"""
        with self.lock:
            status = self.current_status.copy()
        
        self.send_lan_message("status_update", **status)

    def start(self):
        """受信開始"""
        self.running = True
        
        # 発見サーバー開始
        self.start_discovery_server()
        
        # TCPサーバー開始
        if not self.start_tcp_server():
            return False
        
        return True

    def stop(self):
        """受信停止"""
        self.running = False
        
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        
        if self.tcp_server:
            try:
                self.tcp_server.close()
            except:
                pass
            self.tcp_server = None
        
        if self.udp_server:
            try:
                self.udp_server.close()
            except:
                pass
            self.udp_server = None
        
        logger.info("🛑 LAN受信停止")

# ── RTSP サーバー ────────────────────────────
def pil_to_gst_buffer(img: Image.Image):
    data = img.tobytes()
    buf = Gst.Buffer.new_allocate(None, len(data), None)
    buf.fill(0, data)
    buf.duration = Gst.util_uint64_scale_int(1, Gst.SECOND, FPS)
    return buf

class LANElevatorDisplayFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, receiver: LANElevatorReceiver):
        super().__init__()
        self.receiver = receiver
        self.set_shared(True)
        self.launch_str = (
            '( appsrc name=src is-live=true block=true format=time '
            f' caps=video/x-raw,format=RGB,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' do-timestamp=true ! videoconvert '
            f'! video/x-raw,format=I420,width={WIDTH},height={HEIGHT},framerate={FPS}/1 '
            ' ! x264enc tune=zerolatency bitrate=500 speed-preset=ultrafast '
            ' ! rtph264pay name=pay0 pt=96 config-interval=1 )'
        )
    
    def do_create_element(self, url):
        pipeline = Gst.parse_launch(self.launch_str)
        self.appsrc = pipeline.get_by_name('src')
        threading.Thread(target=self.push_frames, daemon=True).start()
        return pipeline
    
    def push_frames(self):
        try:
            font_large = ImageFont.truetype(FONT_PATH, 36)
            font_medium = ImageFont.truetype(FONT_PATH, 28)
            font_small = ImageFont.truetype(FONT_PATH, 20)
        except IOError:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        while True:
            img = Image.new('RGB', (WIDTH, HEIGHT), 'black')
            draw = ImageDraw.Draw(img)
            
            with self.receiver.lock:
                cur = self.receiver.current_status['current_floor']
                tgt = self.receiver.current_status['target_floor']
                is_moving = self.receiver.current_status['is_moving']
            
            # エレベーター案内ディスプレイのレイアウト
            if is_moving and tgt:
                # 移動中: 現在階と行先階を表示
                header = "移動中"
                body = f"{cur} → {tgt}"
                
                # ヘッダー（移動中）
                bb_header = draw.textbbox((0,0), header, font=font_medium)
                draw.text(((WIDTH-bb_header[2])//2, 30), header, font=font_medium, fill='yellow')
                
                # メイン表示（現在階 → 行先階）
                bb_body = draw.textbbox((0,0), body, font=font_large)
                draw.text(((WIDTH-bb_body[2])//2, 100), body, font=font_large, fill='white')
                
                # 矢印アニメーション
                arrow_y = 160
                arrow_x = WIDTH // 2
                # 簡単な点滅効果
                if int(time.time() * 2) % 2:
                    draw.text((arrow_x - 10, arrow_y), "▶", font=font_medium, fill='green')
                
            else:
                # 停止中: 現在階のみ表示
                header = "現在階"
                body = cur
                
                # ヘッダー（現在階）
                bb_header = draw.textbbox((0,0), header, font=font_medium)
                draw.text(((WIDTH-bb_header[2])//2, 50), header, font=font_medium, fill='lightblue')
                
                # メイン表示（現在階）
                bb_body = draw.textbbox((0,0), body, font=font_large)
                draw.text(((WIDTH-bb_body[2])//2, 120), body, font=font_large, fill='white')
            
            # LAN接続状態表示
            connection_status = "LAN接続" if self.receiver.client_socket else "LAN待機"
            connection_color = 'green' if self.receiver.client_socket else 'orange'
            draw.text((10, 10), connection_status, font=font_small, fill=connection_color)
            
            # IPアドレス表示
            ip_text = f"IP: {self.receiver.local_ip}"
            draw.text((10, 35), ip_text, font=font_small, fill='gray')
            
            # 日時表示
            now = datetime.now().strftime("%Y年%-m月%-d日 %H:%M:%S")
            bb_time = draw.textbbox((0,0), now, font=font_small)
            draw.text(((WIDTH-bb_time[2])//2, HEIGHT-40), now, font=font_small, fill='gray')
            
            # フレーム送信
            buf = pil_to_gst_buffer(img)
            if self.appsrc.emit('push-buffer', buf) != Gst.FlowReturn.OK:
                break
            time.sleep(1.0/FPS)

def signal_handler(signum, frame):
    logger.info(f"🛑 シグナル {signum} 受信、停止します")
    receiver.stop()
    sys.exit(0)

if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数解析
    parser = argparse.ArgumentParser(description='SEC-3000H Elevator Display - LAN Network Connection')
    parser.add_argument('--no-rtsp', action='store_true', help='RTSPサーバーを起動しない')
    parser.add_argument('--port', type=int, default=COMMUNICATION_PORT, help='通信ポート番号')
    parser.add_argument('--discovery-port', type=int, default=DISCOVERY_PORT, help='発見ポート番号')
    args = parser.parse_args()
    
    logger.info("🏢 SEC-3000H エレベーター案内ディスプレイ起動中...")
    logger.info("🌐 LAN通信版")
    logger.info(f"🔌 通信ポート: {args.port}")
    logger.info(f"🔍 発見ポート: {args.discovery_port}")
    
    # LAN受信システム初期化
    receiver = LANElevatorReceiver(port=args.port, discovery_port=args.discovery_port)
    
    if not receiver.start():
        logger.error("❌ LAN受信システムの開始に失敗しました")
        sys.exit(1)
    
    # RTSPサーバー起動
    if not args.no_rtsp:
        Gst.init(None)
        server = GstRtspServer.RTSPServer.new()
        server.props.service = '8554'
        mount = server.get_mount_points()
        mount.add_factory('/elevator', LANElevatorDisplayFactory(receiver))
        server.attach(None)
        
        logger.info(f"✅ RTSPサーバー起動: rtsp://{receiver.local_ip}:8554/elevator")
    
    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🎯 LAN通信エレベーター案内ディスプレイ稼働中...")
    logger.info(f"📍 ローカルIP: {receiver.local_ip}")
    
    try:
        if not args.no_rtsp:
            GLib.MainLoop().run()
        else:
            # RTSPなしの場合は単純なループ
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 キーボード割り込みを受信しました")
        receiver.stop()
        sys.exit(0)
