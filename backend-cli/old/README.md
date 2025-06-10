# SEC-3000H Elevator Auto Pilot CLI

シリアル通信専用のエレベーター自動操縦プログラムです。フロントエンドとの通信を排除し、Raspberry Pi 4 との安定したシリアル通信に特化しています。

## 概要

- **目的**: エレベーター内案内ディスプレイシステム
- **通信**: SEC-3000H 仕様準拠の RS-422 シリアル通信
- **表示**: Raspberry Pi 4 で RTSP ストリーミング映像生成
- **対象**: エレベーター内モニター表示

## システム構成

```
┌─────────────────┐    RS-422     ┌─────────────────┐    RTSP    ┌─────────────┐
│   backend-cli   │ ◄──────────► │ Raspberry Pi 4  │ ────────► │   モニター   │
│  (Windows PC)   │   シリアル通信  │   案内ディスプレイ │  映像配信   │             │
└─────────────────┘              └─────────────────┘           └─────────────┘
```

## 機能

### backend-cli (Windows PC)

- SEC-3000H 準拠の自動運転制御
- B1F → 1F → 2F → 3F → 4F → 5F の循環運転
- エレベーターとの双方向シリアル通信
- 階数設定・扉制御コマンド送信
- 現在階・行先階・荷重情報受信

### Raspberry Pi 4

- シリアル通信受信・ACK 応答
- エレベーター状態の解析・管理
- RTSP ストリーミング映像生成
- 案内ディスプレイ表示制御

## インストール

### backend-cli (Windows PC)

#### TypeScript 版

```bash
cd backend-cli
npm install
```

#### Python 版

```bash
cd backend-cli
pip install -r requirements.txt
```

### Raspberry Pi 4

必要なパッケージをインストール：

```bash
sudo apt update
sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0
sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good
sudo apt install gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav
sudo apt install python3-pil

pip3 install pyserial
```

## 使用方法

### 1. backend-cli 起動 (Windows PC)

#### TypeScript 版

```bash
cd backend-cli
npm run dev
```

#### Python 版

```bash
cd backend-cli
python elevator_auto_pilot.py
```

### 2. Raspberry Pi 4 起動

```bash
python3 rtsp_elevator_display.py
```

### 3. モニター表示

RTSP ストリームをモニターで表示：

```
rtsp://[Raspberry_Pi_IP]:8554/elevator
```

## 表示内容

### 停止時

```
┌─────────────────┐
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
│     移動中      │
│                 │
│   3F → 5F      │
│       ▶        │
│                 │
│ 2025年5月29日   │
│   15:30:45     │
└─────────────────┘
```

## 設定

### シリアルポート設定

**backend-cli/src/index.ts**

```typescript
const SERIAL_PORT = "COM27"; // Windowsの場合
// const SERIAL_PORT = "/dev/ttyUSB0"; // Linuxの場合
```

**raspberryPi/rtsp_elevator_display.py**

```python
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 9600
```

### 自動運転シーケンス

**backend-cli/src/index.ts**

```typescript
const AUTO_SEQUENCE = ["B1F", "1F", "2F", "3F", "4F", "5F"];
```

## ログ出力例

### backend-cli

```
🚀 SEC-3000H Elevator Auto Pilot CLI 起動中...
✅ シリアルポート COM27 接続成功
🚀 自動運転開始
🏢 運転シーケンス: B1F → 1F → 2F → 3F → 4F → 5F

🎯 次の目標階: 2F (現在: 1F)
🚪 扉を閉めています...
📤 送信: ENQ(05) 局番号:0001 CMD:W 扉制御: 閉扉 データ:0002 チェックサム:9C
✅ ACK受信
🚀 2Fに移動中...
📤 送信: ENQ(05) 局番号:0001 CMD:W 階数設定: 2F データ:0002 チェックサム:A3
✅ ACK受信
```

### Raspberry Pi 4

```
🏢 SEC-3000H エレベーター案内ディスプレイ起動中...
✅ シリアルポート /dev/ttyUSB0 に接続
📨 受信: ENQ(05) 局番号:0001 CMD:W 扉制御: 閉扉 データ:0002 チェックサム:9C
📤 送信: ACK(06) 局番号:0001 | HEX: 0630303031
📨 受信: ENQ(05) 局番号:0001 CMD:W 階数設定: 2F データ:0002 チェックサム:A3
🎯 移動開始: 1F → 2F
===== Status: 現在階=1F 行先階=2F 状態=移動中 =====
✅ RTSPサーバー起動: rtsp://192.168.40.239:8554/elevator
```

## トラブルシューティング

### シリアルポート接続エラー

- ポート名の確認 (Windows: COMx, Linux: /dev/ttyUSBx)
- ケーブル接続の確認
- 他のプログラムでポートが使用されていないか確認

### RTSP 映像が表示されない

- Raspberry Pi 4 の IP アドレス確認
- ファイアウォール設定確認
- GStreamer パッケージのインストール確認

### 通信エラー

- ボーレート設定確認 (9600bps)
- パリティ設定確認 (偶数パリティ)
- RS-422 配線確認

## SEC-3000H 通信仕様

### データ番号

- `0x0001`: 現在階数
- `0x0002`: 行先階
- `0x0003`: 荷重
- `0x0010`: 階数設定
- `0x0011`: 扉制御

### 扉制御コマンド

- `0x0000`: 停止
- `0x0001`: 開扉
- `0x0002`: 閉扉

### 通信設定

- **通信規格**: RS-422 4 線式、全二重通信
- **通信速度**: 9600bps
- **データ**: 8bit
- **パリティ**: 偶数（even）
- **ストップ**: 1bit

## ライセンス

MIT License
