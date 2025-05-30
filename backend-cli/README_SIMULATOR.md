# SEC-3000H Elevator Simulator System

PC と Raspberry Pi 4 で SEC-3000H 仕様に準拠したエレベーターシミュレーションシステムです。

## 概要

- **目的**: SEC-3000H 構成資料に基づく完全な双方向通信システム
- **通信**: RS422 準拠のシリアル通信（9600bps, 偶数パリティ）
- **役割分担**: PC がエレベーター側、Raspberry Pi 4 が自動運転装置側
- **表示**: Raspberry Pi 4 で RTSP ストリーミング映像生成

## システム構成

```
┌─────────────────┐    シリアル通信    ┌─────────────────┐
│   Windows PC    │ ◄─────────────► │ Raspberry Pi 4  │
│  エレベーター側   │   RS422/USB     │  自動運転装置側   │
│   局番号: 0002   │                │   局番号: 0001   │
│                 │                │                 │
│ 定期送信:       │                │ 受信・表示:      │
│ ・現在階数(0001) │                │ ・エレベーター状態 │
│ ・行先階(0002)   │                │ ・RTSP配信       │
│ ・荷重(0003)     │                │                 │
│                 │                │ 送信:           │
│ 受信・処理:      │                │ ・階数設定(0010) │
│ ・階数設定       │                │ ・扉制御(0011)   │
│ ・扉制御         │                │                 │
└─────────────────┘                └─────────────────┘
```

## 通信プロトコル

### エレベーター → 自動運転装置（定期送信）

```
ENQ(05) 0001 W 0001 FFFF [チェックサム]  # 現在階数: B1F
ENQ(05) 0001 W 0002 0003 [チェックサム]  # 行先階: 3F
ENQ(05) 0001 W 0003 074E [チェックサム]  # 荷重: 1870kg
```

### 自動運転装置 → エレベーター（指令送信）

```
ENQ(05) 0002 W 0010 0005 [チェックサム]  # 階数設定: 5F
ENQ(05) 0002 W 0011 0001 [チェックサム]  # 扉制御: 開扉
```

### ACK 応答

```
ACK(06) 0002  # エレベーター側からの応答
ACK(06) 0001  # 自動運転装置側からの応答
```

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

### 1. エレベーターシミュレーター起動 (Windows PC)

```bash
cd backend-cli
python elevator_simulator.py
```

#### オプション

```bash
# シリアルポート指定
python elevator_simulator.py --port COM27

# 初期荷重設定
python elevator_simulator.py --load 1500
```

### 2. 自動運転装置受信機起動 (Raspberry Pi 4)

```bash
cd raspberryPi
python3 auto_pilot_receiver.py
```

#### オプション

```bash
# シリアルポート指定
python3 auto_pilot_receiver.py --port /dev/ttyUSB0

# RTSPサーバーなしで起動
python3 auto_pilot_receiver.py --no-rtsp
```

### 3. RTSP 映像表示

```
rtsp://192.168.40.239:8554/elevator
```

## データ仕様

### エレベーター側送信データ

| データ番号 | 内容     | データ例 | 説明             |
| ---------- | -------- | -------- | ---------------- |
| 0001       | 現在階数 | FFFF     | B1F（地下 1 階） |
| 0001       | 現在階数 | 0003     | 3F（3 階）       |
| 0002       | 行先階   | 0000     | なし             |
| 0002       | 行先階   | 0005     | 5F（5 階）       |
| 0003       | 荷重     | 074E     | 1870kg           |

### 自動運転装置側送信データ

| データ番号 | 内容     | データ例 | 説明                   |
| ---------- | -------- | -------- | ---------------------- |
| 0010       | 階数設定 | 0003     | 3F（3 階）に移動       |
| 0010       | 階数設定 | FFFF     | B1F（地下 1 階）に移動 |
| 0011       | 扉制御   | 0001     | 開扉                   |
| 0011       | 扉制御   | 0002     | 閉扉                   |
| 0011       | 扉制御   | 0000     | 停止                   |

## ログ出力例

### エレベーターシミュレーター (Windows PC)

```
🏢 SEC-3000H Elevator Simulator 起動中...
📡 シリアルポート設定: COM27
🏷️ 局番号: 0002 (エレベーター側)
🎯 送信先: 0001 (自動運転装置側)
✅ シリアルポート COM27 接続成功
✅ 初期化完了
🚀 連続データ送信開始
📊 送信データ: 現在階数(0001) → 行先階(0002) → 荷重(0003) → 繰り返し

[2025年05月29日 17:45:00] 📤 送信: ENQ(05) 局番号:0001 CMD:W 現在階数: 1F データ:0001 チェックサム:9C
[2025年05月29日 17:45:01] 📤 送信: ENQ(05) 局番号:0001 CMD:W 行先階: なし データ:0000 チェックサム:9A
[2025年05月29日 17:45:02] 📤 送信: ENQ(05) 局番号:0001 CMD:W 荷重: 0kg データ:0000 チェックサム:9B

🎯 階数設定受信: 3F
🚀 3Fへの移動完了（扉開放待ち）
🚪 扉制御受信: 開扉
🏢 扉開放により到着完了: 3F
```

### 自動運転装置受信機 (Raspberry Pi 4)

```
🤖 SEC-3000H Auto Pilot Receiver 起動中...
📡 シリアルポート設定: /dev/ttyUSB0
🏷️ 局番号: 0001 (自動運転装置側)
🎯 受信元: 0002 (エレベーター側)
✅ シリアルポート /dev/ttyUSB0 接続成功
✅ 初期化完了
🎧 エレベーターデータ受信開始
📊 受信データ: 現在階数(0001), 行先階(0002), 荷重(0003)
✅ RTSPサーバー起動: rtsp://192.168.40.239:8554/elevator

[2025年05月29日 17:45:00] 📨 受信: ENQ(05) 局番号:0002 CMD:W 現在階数: 1F データ:0001 チェックサム:9C
[2025年05月29日 17:45:00] 📤 ACK送信: 060030303032
[2025年05月29日 17:45:01] 📨 受信: ENQ(05) 局番号:0002 CMD:W 行先階: なし データ:0000 チェックサム:9A
[2025年05月29日 17:45:01] 📤 ACK送信: 060030303032
[2025年05月29日 17:45:02] 📨 受信: ENQ(05) 局番号:0002 CMD:W 荷重: 0kg データ:0000 チェックサム:9B
[2025年05月29日 17:45:02] 📤 ACK送信: 060030303032

[2025年05月29日 17:45:30] 📊 エレベーター状態
現在階: 1F
行先階: -
荷重: 0kg
通信状態: 正常
最終更新: 17:45:02
```

## RTSP 表示内容

### 自動運転装置画面

```
┌─────────────────────────────────┐
│ SEC-3000H 自動運転装置          │
│                                 │
│        現在階: 3F               │
│                                 │
│        行先階: 5F               │
│                                 │
│        荷重: 1500kg             │
│                                 │
│ 通信: 正常    局番号: 0001      │
│ IP: 192.168.40.239              │
│                                 │
│ 2025年5月29日 17:45:30          │
│ 最終更新: 17:45:30              │
└─────────────────────────────────┘
```

## 手動操作

### 自動運転装置からエレベーターへの指令送信

Raspberry Pi 4 の Python コンソールで：

```python
# 3Fに移動指令
receiver.set_floor("3F")

# B1Fに移動指令
receiver.set_floor("B1F")

# 扉開放指令
receiver.control_door("open")

# 扉閉鎖指令
receiver.control_door("close")
```

## トラブルシューティング

### シリアル通信エラー

- **ポート確認**: デバイスマネージャーで COM ポート番号を確認
- **権限設定**: Raspberry Pi 4 でユーザーを dialout グループに追加
- **ケーブル確認**: RS422 対応の USB-シリアル変換器を使用

```bash
# Raspberry Pi 4でのユーザー権限設定
sudo usermod -a -G dialout $USER
# 再ログインが必要
```

### 通信が確立しない

- **局番号確認**: エレベーター側(0002)と自動運転装置側(0001)の設定
- **ボーレート**: 9600bps, 偶数パリティ, 8bit, 1stopbit
- **チェックサム**: 計算方法の確認

### RTSP 映像が表示されない

- **IP アドレス**: Raspberry Pi 4 の IP アドレス確認
- **ポート**: 8554 ポートが開放されているか
- **GStreamer**: パッケージのインストール確認

## 仕様準拠

このシステムは以下の SEC-3000H 仕様に完全準拠しています：

- **通信規格**: RS422 4 線式、全二重通信
- **通信速度**: 9600bps
- **データ**: 8bit、偶数パリティ、1stopbit
- **電文フォーマット**: ENQ + 局番号 + コマンド + データ番号 + データ + チェックサム
- **データ番号**: 0001(現在階数), 0002(行先階), 0003(荷重), 0010(階数設定), 0011(扉制御)
- **応答**: ACK/NAK 応答
- **チェックサム**: バイナリデータ加算の下位・上位バイト和

## ライセンス

MIT License
