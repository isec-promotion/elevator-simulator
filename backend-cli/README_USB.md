# SEC-3000H Elevator Auto Pilot - USB Direct Connection

PC と Raspberry Pi 4 を USB ケーブルで直接接続してエレベーター自動操縦を行うシステムです。

## 概要

- **目的**: PC と Raspberry Pi 4 の USB 直接通信によるエレベーター制御
- **通信**: JSON 形式のメッセージによる高速 USB 通信（115200bps）
- **表示**: Raspberry Pi 4 で RTSP ストリーミング映像生成
- **対象**: エレベーター内モニター表示

## システム構成

```
┌─────────────────┐    USB Cable    ┌─────────────────┐    RTSP    ┌─────────────┐
│   Windows PC    │ ◄─────────────► │ Raspberry Pi 4  │ ────────► │   モニター   │
│  backend-cli    │   JSON通信      │   案内ディスプレイ │  映像配信   │             │
└─────────────────┘   115200bps     └─────────────────┘           └─────────────┘
```

## 機能

### backend-cli (Windows PC)

- USB 自動検出による Raspberry Pi 4 発見
- JSON 形式のコマンド送信（階数設定・扉制御）
- リアルタイム状態受信
- B1F → 1F → 2F → 3F → 4F → 5F の循環運転

### Raspberry Pi 4

- USB 直接通信受信・JSON 解析
- エレベーター状態シミュレーション
- RTSP ストリーミング映像生成
- 案内ディスプレイ表示制御

## インストール

### backend-cli (Windows PC)

```bash
cd backend-cli
pip install pyserial
```

### Raspberry Pi 4

```bash
sudo apt update
sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
sudo apt install python3-pil

pip3 install pyserial
```

## 使用方法

### 1. Raspberry Pi 4 起動

```bash
cd raspberryPi
python3 usb_elevator_display.py
```

#### オプション

```bash
# RTSPサーバーなしで起動
python3 usb_elevator_display.py --no-rtsp

# USBデバイスパス指定
python3 usb_elevator_display.py --usb-device /dev/ttyACM1
```

### 2. backend-cli 起動 (Windows PC)

```bash
cd backend-cli
python elevator_usb_pilot.py
```

#### オプション

```bash
# 手動モード（自動運転しない）
python elevator_usb_pilot.py --manual
```

### 3. モニター表示

RTSP ストリームをモニターで表示：

```
rtsp://[Raspberry_Pi_IP]:8554/elevator
```

## 通信プロトコル

### JSON メッセージ形式

#### PC → Raspberry Pi 4

**識別要求**

```json
{
  "type": "identify",
  "timestamp": "2025-05-29T15:30:45.123456"
}
```

**階数設定**

```json
{
  "type": "set_floor",
  "floor": "3F",
  "timestamp": "2025-05-29T15:30:45.123456"
}
```

**扉制御**

```json
{
  "type": "door_control",
  "action": "open",
  "timestamp": "2025-05-29T15:30:45.123456"
}
```

#### Raspberry Pi 4 → PC

**識別応答**

```json
{
  "type": "identify_response",
  "device": "raspberry_pi_elevator",
  "version": "2.0",
  "capabilities": ["rtsp_streaming", "elevator_display"],
  "timestamp": "2025-05-29T15:30:45.123456"
}
```

**ACK 応答**

```json
{
  "type": "ack",
  "command": "set_floor",
  "floor": "3F",
  "timestamp": "2025-05-29T15:30:45.123456"
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
  "timestamp": "2025-05-29T15:30:45.123456"
}
```

## 表示内容

### 停止時

```
┌─────────────────┐
│ USB接続         │
│     現在階      │
│                 │
│       3F        │
│                 │
│ 2025年5月29日   │
│   15:30:45     │
└─────────────────┘
```

### 移動中

```
┌─────────────────┐
│ USB接続         │
│     移動中      │
│                 │
│   3F → 5F      │
│       ▶        │
│                 │
│ 2025年5月29日   │
│   15:30:45     │
└─────────────────┘
```

## ログ出力例

### backend-cli (Windows PC)

```
🚀 SEC-3000H Elevator Auto Pilot - USB Direct Connection
📱 PCとRaspberry Pi 4のUSB直接通信版
============================================================
🔍 Raspberry Pi 4を検索中...
✅ Raspberry Pi 4を発見: COM5
✅ USB接続成功: COM5
📡 通信設定: 115200bps, USB直接通信

🚀 USB直接通信自動運転開始
🏢 運転シーケンス: B1F → 1F → 2F → 3F → 4F → 5F

🎯 次の目標階: 2F (現在: 1F)
📤 USB送信: door_control - {'action': 'close'}
✅ ACK受信: door_control
📤 USB送信: set_floor - {'floor': '2F'}
✅ ACK受信: set_floor
📊 状態更新: 現在階=2F, 行先階=None
```

### Raspberry Pi 4

```
🏢 SEC-3000H エレベーター案内ディスプレイ起動中...
📱 USB直接通信版
🔌 USBデバイス: /dev/ttyACM0
✅ USB接続成功: /dev/ttyACM0
📡 通信設定: 115200bps, USB直接通信
🎧 USB受信開始...
✅ RTSPサーバー起動: rtsp://192.168.40.239:8554/elevator

📨 USB受信: identify
🔍 識別要求に応答しました
📨 USB受信: door_control
🚪 扉制御: close
📨 USB受信: set_floor
🎯 移動指示: 1F → 2F
✅ 移動完了: 2F
```

## トラブルシューティング

### USB 接続エラー

- USB ケーブルの接続確認
- Raspberry Pi 4 の電源確認
- デバイスドライバーの確認（Windows）
- `/dev/ttyACM0`の権限確認（Linux）

### 自動検出失敗

- 複数の USB ポートを試行
- Raspberry Pi 4 の再起動
- USB ケーブルの交換

### RTSP 映像が表示されない

- Raspberry Pi 4 の IP アドレス確認
- ファイアウォール設定確認
- GStreamer パッケージのインストール確認

## 通信設定

### USB 設定

- **通信速度**: 115200bps
- **データ**: 8bit
- **パリティ**: なし
- **ストップ**: 1bit
- **フロー制御**: なし

### 自動検出ポート

**Windows**

- COM3, COM4, COM5, COM6, COM7, COM8, COM9, COM10

**Linux**

- /dev/ttyACM0, /dev/ttyACM1, /dev/ttyUSB0, /dev/ttyUSB1

## 利点

1. **高速通信**: 115200bps の高速 USB 通信
2. **簡単接続**: USB ケーブル 1 本で接続
3. **自動検出**: Raspberry Pi 4 の自動発見
4. **JSON 通信**: 人間が読みやすい通信プロトコル
5. **リアルタイム**: 即座の状態同期

## ライセンス

MIT License
