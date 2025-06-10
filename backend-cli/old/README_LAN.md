# SEC-3000H Elevator Auto Pilot - LAN Network Connection

PC と Raspberry Pi 4 を LAN 経由で通信してエレベーター自動操縦を行うシステムです。

## 概要

- **目的**: PC と Raspberry Pi 4 の LAN 通信によるエレベーター制御
- **通信**: TCP/IP + JSON 形式のメッセージ通信
- **自動発見**: UDP ブロードキャストによる Raspberry Pi 4 自動検出
- **表示**: Raspberry Pi 4 で RTSP ストリーミング映像生成
- **対象**: エレベーター内モニター表示

## システム構成

```
┌─────────────────┐    LAN/WiFi     ┌─────────────────┐    RTSP    ┌─────────────┐
│   Windows PC    │ ◄─────────────► │ Raspberry Pi 4  │ ────────► │   モニター   │
│  backend-cli    │   TCP/IP        │   案内ディスプレイ │  映像配信   │             │
│ 192.168.40.184  │   JSON通信      │  192.168.40.239 │           │             │
└─────────────────┘                 └─────────────────┘           └─────────────┘
```

## 機能

### backend-cli (Windows PC)

- **自動発見**: UDP ブロードキャストによる Raspberry Pi 4 検出
- **TCP 通信**: 安定した TCP/IP 接続
- **JSON 形式**: 人間が読みやすいコマンド送信
- **リアルタイム**: 即座の状態受信と ACK 応答
- **自動運転**: B1F → 1F → 2F → 3F → 4F → 5F の循環運転

### Raspberry Pi 4

- **TCP サーバー**: PC 接続を待機・受付
- **UDP 応答**: 自動発見要求への応答
- **JSON 解析**: コマンド解析と状態管理
- **RTSP 配信**: エレベーター案内ディスプレイ映像
- **状態表示**: LAN 接続状態と IP アドレス表示

## インストール

### backend-cli (Windows PC)

```bash
cd backend-cli
# 標準ライブラリのみ使用（追加インストール不要）
```

### Raspberry Pi 4

```bash
sudo apt update
sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
sudo apt install python3-pil

# 標準ライブラリのみ使用（追加インストール不要）
```

## 使用方法

### 1. Raspberry Pi 4 起動

```bash
cd raspberryPi
python3 lan_elevator_display.py
```

#### オプション

```bash
# RTSPサーバーなしで起動
python3 lan_elevator_display.py --no-rtsp

# 通信ポート変更
python3 lan_elevator_display.py --port 9999

# 発見ポート変更
python3 lan_elevator_display.py --discovery-port 9998
```

### 2. backend-cli 起動 (Windows PC)

```bash
cd backend-cli
python elevator_lan_pilot.py
```

#### オプション

```bash
# Raspberry Pi IPアドレス指定
python elevator_lan_pilot.py --raspberry-pi-ip 192.168.40.239

# 通信ポート変更
python elevator_lan_pilot.py --port 9999

# 手動モード（自動運転しない）
python elevator_lan_pilot.py --manual
```

### 3. モニター表示

RTSP ストリームをモニターで表示：

```
rtsp://192.168.40.239:8554/elevator
```

## 通信プロトコル

### 自動発見（UDP）

#### PC → Raspberry Pi 4（ブロードキャスト）

```json
{
  "type": "discover",
  "sender": "elevator_pilot",
  "timestamp": "2025-05-29T17:15:00.123456"
}
```

#### Raspberry Pi 4 → PC（応答）

```json
{
  "type": "discover_response",
  "device": "raspberry_pi_elevator",
  "ip": "192.168.40.239",
  "port": 8888,
  "timestamp": "2025-05-29T17:15:00.123456"
}
```

### 制御通信（TCP）

#### PC → Raspberry Pi 4

**階数設定**

```json
{
  "type": "set_floor",
  "floor": "3F",
  "timestamp": "2025-05-29T17:15:00.123456"
}
```

**扉制御**

```json
{
  "type": "door_control",
  "action": "open",
  "timestamp": "2025-05-29T17:15:00.123456"
}
```

#### Raspberry Pi 4 → PC

**ACK 応答**

```json
{
  "type": "ack",
  "command": "set_floor",
  "floor": "3F",
  "timestamp": "2025-05-29T17:15:00.123456"
}
```

**状態更新**

```json
{
  "type": "status_update",
  "current_floor": "3F",
  "target_floor": null,
  "is_moving": false,
  "door_status": "opening",
  "load_weight": 0,
  "timestamp": "2025-05-29T17:15:00.123456"
}
```

## 表示内容

### 停止時

```
┌─────────────────┐
│ LAN接続         │
│ IP: 192.168.40.239
│     現在階      │
│                 │
│       3F        │
│                 │
│ 2025年5月29日   │
│   17:15:00     │
└─────────────────┘
```

### 移動中

```
┌─────────────────┐
│ LAN接続         │
│ IP: 192.168.40.239
│     移動中      │
│                 │
│   3F → 5F      │
│       ▶        │
│                 │
│ 2025年5月29日   │
│   17:15:00     │
└─────────────────┘
```

## ログ出力例

### backend-cli (Windows PC)

```
🚀 SEC-3000H Elevator Auto Pilot - LAN Network Connection
🌐 PCとRaspberry Pi 4のLAN通信版
============================================================
🖥️ PC IP: 192.168.40.184
🍓 Raspberry Pi IP: 192.168.40.239
🔌 通信ポート: 8888
============================================================
🔍 ネットワーク上でRaspberry Pi 4を検索中...
📡 発見メッセージをブロードキャスト: 192.168.40.255:8889
✅ Raspberry Pi 4を発見: 192.168.40.239
🔌 192.168.40.239:8888 に接続中...
✅ LAN接続成功: 192.168.40.239:8888
📡 通信設定: TCP/IP, JSON形式

🚀 LAN通信自動運転開始
🏢 運転シーケンス: B1F → 1F → 2F → 3F → 4F → 5F
🌐 通信先: 192.168.40.239:8888

🎯 次の目標階: 2F (現在: 1F)
📤 LAN送信: door_control - {'action': 'close'}
✅ ACK受信: door_control
📤 LAN送信: set_floor - {'floor': '2F'}
✅ ACK受信: set_floor
📊 状態更新: 現在階=2F, 行先階=None
```

### Raspberry Pi 4

```
🏢 SEC-3000H エレベーター案内ディスプレイ起動中...
🌐 LAN通信版
🔌 通信ポート: 8888
🔍 発見ポート: 8889
🔍 発見サーバー開始: UDP 192.168.40.239:8889
🌐 TCPサーバー開始: 192.168.40.239:8888
⏳ PC接続を待機中...
✅ RTSPサーバー起動: rtsp://192.168.40.239:8554/elevator
🎯 LAN通信エレベーター案内ディスプレイ稼働中...
📍 ローカルIP: 192.168.40.239

🔍 発見要求を受信: 192.168.40.184
📡 発見応答を送信: 192.168.40.184
✅ PC接続受付: 192.168.40.184:52341
📨 LAN受信: door_control
🚪 扉制御: close
📨 LAN受信: set_floor
🎯 移動指示: 1F → 2F
✅ 移動完了: 2F
```

## ネットワーク設定

### ポート設定

- **通信ポート**: 8888 (TCP)
- **発見ポート**: 8889 (UDP)
- **RTSP ポート**: 8554 (TCP)

### ファイアウォール設定

**Windows PC**

```cmd
# 発信許可（通常は自動で許可される）
netsh advfirewall firewall add rule name="Elevator LAN Client" dir=out action=allow protocol=TCP localport=any remoteport=8888
```

**Raspberry Pi 4**

```bash
# 着信許可
sudo ufw allow 8888/tcp
sudo ufw allow 8889/udp
sudo ufw allow 8554/tcp
```

## トラブルシューティング

### 自動発見失敗

- **ネットワーク確認**: 同一ネットワークに接続されているか
- **ファイアウォール**: UDP 8889 ポートが開放されているか
- **ブロードキャストアドレス**: ネットワークに応じて調整
- **手動指定**: `--raspberry-pi-ip`オプションで直接指定

### TCP 接続エラー

- **ポート確認**: TCP 8888 ポートが使用可能か
- **IP アドレス**: Raspberry Pi 4 の IP アドレスが正しいか
- **ネットワーク**: ping 疎通確認
- **プロセス**: 他のプログラムがポートを使用していないか

### RTSP 映像が表示されない

- **IP アドレス**: Raspberry Pi 4 の IP アドレス確認
- **ポート**: TCP 8554 ポートが開放されているか
- **GStreamer**: パッケージのインストール確認
- **ネットワーク帯域**: 映像配信に十分な帯域があるか

## 利点

1. **ネットワーク通信**: 物理的なケーブル接続不要
2. **自動発見**: IP アドレス変更に自動対応
3. **TCP 信頼性**: パケット損失のない安定通信
4. **JSON 可読性**: 人間が読みやすい通信プロトコル
5. **スケーラビリティ**: 複数デバイスへの拡張が容易
6. **リモート制御**: ネットワーク経由での遠隔操作

## セキュリティ考慮事項

- **ローカルネットワーク**: 信頼できるネットワーク内での使用を推奨
- **認証なし**: 現在の実装では認証機能なし
- **暗号化なし**: 平文での JSON 通信
- **ファイアウォール**: 必要なポートのみ開放

## ライセンス

MIT License
