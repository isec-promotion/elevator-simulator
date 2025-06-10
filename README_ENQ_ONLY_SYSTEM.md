# エレベーター ENQ 専用システム

エレベーターからの ENQ メッセージのみを送受信するシンプルなシステムです。

## システム構成

### PC 側（エレベーター）

- **ファイル**: `backend-cli/elevator_enq_only_simulator.py`
- **機能**: 指定された仕様に従って ENQ メッセージのみを送信
- **通信**: RS422 で COM27 に送信

### Raspberry Pi 側

- **ファイル**: `raspberryPi/elevator_enq_rtsp_receiver.py`
- **機能**: ENQ メッセージを受信して RTSP 映像で配信
- **通信**: RS422 で/dev/ttyUSB0 から受信（ACK 応答なし）

## 通信仕様

### ENQ 送信シーケンス

1. **現在階送信** (ENQ 0002 W 0001 XXXX)
2. **行先階送信** (ENQ 0002 W 0002 XXXX)
3. **乗客降客送信** (ENQ 0002 W 0003 074E)
4. **10 秒待機**
5. **着床送信** (ENQ 0002 W 0002 0000)

- ① ～ ③ は 1 秒間隔で送信
- XXXX は階数（B1F=FFFF, 1F=0001, 2F=0002, 3F=0003）
- 074E は 1870kg（固定値）

## 使用方法

### 1. PC 側（エレベーター）の起動

```bash
cd backend-cli
python elevator_enq_only_simulator.py --port COM27 --start-floor 1
```

**オプション:**

- `--port`: シリアルポート（デフォルト: COM27）
- `--start-floor`: 開始階数（-1:B1F, 1:1F, 2:2F, 3:3F）

**実行例:**

```bash
# 1Fから開始
python elevator_enq_only_simulator.py --port COM27 --start-floor 1

# B1Fから開始
python elevator_enq_only_simulator.py --port COM27 --start-floor -1
```

### 2. Raspberry Pi 側の起動

```bash
cd raspberryPi
python3 elevator_enq_rtsp_receiver.py --port /dev/ttyUSB0
```

**オプション:**

- `--port`: シリアルポート（デフォルト: /dev/ttyUSB0）
- `--rtsp-port`: RTSP ポート番号（デフォルト: 8554）
- `--debug`: デバッグモード

**実行例:**

```bash
# 基本起動
python3 elevator_enq_rtsp_receiver.py

# デバッグモード
python3 elevator_enq_rtsp_receiver.py --debug

# カスタムポート
python3 elevator_enq_rtsp_receiver.py --port /dev/ttyUSB1 --rtsp-port 8555
```

### 3. RTSP 映像の視聴

VLC メディアプレイヤーで以下の URL を開く：

```
rtsp://[Raspberry PiのIP]:8554/elevator
```

例: `rtsp://192.168.1.100:8554/elevator`

## ログ出力例

### PC 側（エレベーター）

```
2025-05-30 15:21:42,123 - INFO - 🏢 エレベーターENQ専用シミュレーター初期化
2025-05-30 15:21:42,124 - INFO - ✅ シリアルポート COM27 接続成功
2025-05-30 15:21:42,125 - INFO - 🚀 エレベーターENQ専用シミュレーション開始
2025-05-30 15:21:42,126 - INFO - 🎯 新しい移動シナリオ: 1F → 3F
2025-05-30 15:21:42,127 - INFO - [2025年05月30日 15:21:42] 📤 ENQ送信: 現在階: 1F (局番号:0002 データ:0001 チェックサム:9A)
2025-05-30 15:21:43,128 - INFO - [2025年05月30日 15:21:43] 📤 ENQ送信: 行先階: 3F (局番号:0002 データ:0003 チェックサム:9C)
2025-05-30 15:21:44,129 - INFO - [2025年05月30日 15:21:44] 📤 ENQ送信: 乗客降客: 1870kg (局番号:0002 データ:074E チェックサム:B1)
2025-05-30 15:21:44,130 - INFO - ⏰ 10秒待機中...
2025-05-30 15:21:54,131 - INFO - [2025年05月30日 15:21:54] 📤 ENQ送信: 着床: 行先階クリア (局番号:0002 データ:0000 チェックサム:97)
2025-05-30 15:21:54,132 - INFO - 🏁 着床完了: 3F
```

### Raspberry Pi 側

```
2025-05-30 15:21:42,200 - INFO - 📡 シリアルENQ受信専用システム初期化
2025-05-30 15:21:42,201 - INFO - ✅ シリアルポート /dev/ttyUSB0 接続成功
2025-05-30 15:21:42,202 - INFO - 📺 RTSP映像配信サーバー起動中...
2025-05-30 15:21:42,300 - INFO - ✅ RTSP配信開始: rtsp://192.168.1.100:8554/elevator
2025-05-30 15:21:42,301 - INFO - 🔍 シリアルENQ受信開始（受信専用モード）
2025-05-30 15:21:42,350 - INFO - [2025年05月30日 15:21:42] 📤 エレベーター→ENQ: 現在階数: 1F
2025-05-30 15:21:43,351 - INFO - 🚀 移動開始: 1F → 3F
2025-05-30 15:21:43,352 - INFO - [2025年05月30日 15:21:43] 📤 エレベーター→ENQ: 行先階: 3F
2025-05-30 15:21:44,353 - INFO - ⚖️ 荷重変更: 0kg → 1870kg
2025-05-30 15:21:44,354 - INFO - [2025年05月30日 15:21:44] 📤 エレベーター→ENQ: 荷重: 1870kg
2025-05-30 15:21:54,355 - INFO - 🏁 着床検出: 1F (行先階クリア)
2025-05-30 15:21:54,356 - INFO - [2025年05月30日 15:21:54] 📤 エレベーター→ENQ: 行先階: なし
```

## RTSP 映像の表示内容

### 停止中（緑色背景）

```
現在階: 1F
```

### 移動中（黄色背景）

```
1F ⇒ 3F
```

### 詳細情報

- 荷重: XXXkg
- 最終更新: HH:MM:SS
- 最終着床: HH:MM:SS（着床後に表示）

### 通信ログ

最新 6 件の ENQ 受信ログを表示

## 特徴

### PC 側（エレベーター）

- ✅ **ENQ 専用送信**: ACK 受信なし、送信のみに特化
- ✅ **仕様準拠**: 指定されたシーケンス通りに送信
- ✅ **ランダム移動**: B1F ～ 3F の範囲でランダムな移動シナリオ
- ✅ **チェックサム計算**: 正確なチェックサム自動計算
- ✅ **階数対応**: B1F（FFFF）、1F ～ 3F（0001 ～ 0003）

### Raspberry Pi 側

- ✅ **ENQ 専用受信**: ACK 応答なし、受信のみに特化
- ✅ **着床検出**: 行先階クリア（0000）による着床検出
- ✅ **RTSP 配信**: リアルタイム映像配信
- ✅ **自動復帰**: シリアル切断時の自動再接続
- ✅ **状態表示**: 停止中（緑）/移動中（黄）の視覚的表示

## トラブルシューティング

### シリアル接続エラー

```bash
# ポート確認（Windows）
mode

# ポート確認（Linux）
ls /dev/ttyUSB*

# 権限確認（Linux）
sudo chmod 666 /dev/ttyUSB0
```

### RTSP 接続エラー

```bash
# ファイアウォール確認
sudo ufw allow 8554

# ポート使用状況確認
netstat -an | grep 8554
```

### 依存関係インストール

```bash
# Raspberry Pi
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 gir1.2-gst-rtsp-server-1.0
pip3 install pyserial pillow

# Windows
pip install pyserial
```

## システム停止

両方のプログラムは `Ctrl+C` で安全に停止できます。

```bash
# 停止時のログ例
^C
2025-05-30 15:25:00,123 - INFO - 🛑 Ctrl+C が押されました
2025-05-30 15:25:00,124 - INFO - 🛑 シミュレーション停止
2025-05-30 15:25:00,125 - INFO - 📡 シリアルポート切断完了
```
