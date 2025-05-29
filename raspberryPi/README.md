# Raspberry Pi 4B エレベーターシリアル信号受信プログラム

このディレクトリには、エレベーター（PC）から RS422 経由で送信されるシリアル信号を受信し、ターミナルに表示するプログラムが含まれています。

## 📋 システム概要

```
PC（エレベーター） → USB-RS422 → Raspberry Pi 4B → MQTT → 監視室PC
                                    ↑ このプログラム
```

### 🎯 目的

- エレベーター（PC）から RS422 シリアル通信で送信される操作信号を受信
- 受信したシリアル信号をターミナルに表示して動作確認
- 将来的に MQTT で監視室 PC にデータ送信（後日実装予定）

## 📁 ファイル構成

```
raspberryPi/
├── README.md                    # このファイル
├── serial_receiver.py           # シリアル信号受信プログラム（メイン）
├── auto_mode_receiver.py        # 自動運転モード受信プログラム
├── auto_pilot.py               # 自動運転パイロットプログラム
├── elevator_display_streamer.py # 表示システム with RTSPストリーミング（NEW!）
├── requirements_simple.txt      # Python依存関係（シンプル版）
├── requirements_streaming.txt   # Python依存関係（ストリーミング版）
├── install_simple.sh            # シンプル版インストールスクリプト
└── install_streaming.sh         # ストリーミング版インストールスクリプト（NEW!）
```

## 🚀 セットアップ手順

### 1. Raspberry Pi OS の準備

```bash
# システムを最新に更新
sudo apt update && sudo apt upgrade -y

# Python3とpipをインストール（通常は既にインストール済み）
sudo apt install python3 python3-pip -y
```

### 2. プロジェクトファイルの配置

```bash
# ホームディレクトリにプロジェクトディレクトリを作成
mkdir -p /home/pi/elevator-serial
cd /home/pi/elevator-serial

# ファイルをコピー
# serial_receiver.py, requirements_simple.txt をコピー
```

### 3. Python 依存関係のインストール

```bash
# 依存関係をインストール
pip3 install -r requirements_simple.txt

# または直接インストール
pip3 install pyserial
```

### 4. RS422-USB 変換器の設定

```bash
# USB-シリアル変換器が認識されているか確認
lsusb
dmesg | grep tty

# シリアルポートの確認
ls -la /dev/ttyUSB*

# ユーザーをdialoutグループに追加（シリアルポートアクセス権限）
sudo usermod -a -G dialout pi

# 再ログインまたは再起動
sudo reboot
```

### 5. プログラムの設定

`serial_receiver.py`の設定を環境に合わせて調整：

```python
# 設定
SERIAL_PORT = '/dev/ttyUSB0'  # RS422-USB変換器のデバイス
BAUDRATE = 9600
DATABITS = 8
PARITY = 'E'  # Even parity
STOPBITS = 1
TIMEOUT = 1.0
```

## 🔧 使用方法

### 基本的な実行

```bash
# プログラムを実行
cd /home/pi/elevator-serial
python3 serial_receiver.py
```

### 実行例

```
🚀 Raspberry Pi 4B シリアル信号受信プログラム
================================================================================
システム構成:
PC（エレベーター） → USB-RS422 → Raspberry Pi 4B → MQTT → 監視室PC
                                    ↑ このプログラム
================================================================================
✅ シリアルポート接続成功: /dev/ttyUSB0
   設定: 9600bps, 8bit, パリティ:E, ストップビット:1
--------------------------------------------------------------------------------
📡 シリアル信号受信を開始します...
   Ctrl+C で停止
================================================================================

[2024-05-27 16:30:15.123] 受信データ (16バイト)
  HEX: 05 30 30 30 31 57 30 30 31 30 30 30 30 32 34 46
  解析: ENQ:05 局番号:0001 CMD:W 階数設定: 2F データ:0002 チェックサム:4F
  → ACK応答送信: 06 30 30 30 31
--------------------------------------------------------------------------------

[2024-05-27 16:30:18.456] 受信データ (16バイト)
  HEX: 05 30 30 30 31 57 30 30 31 31 30 30 30 31 34 45
  解析: ENQ:05 局番号:0001 CMD:W 扉制御: 開扉 データ:0001 チェックサム:45
  → ACK応答送信: 06 30 30 30 31
--------------------------------------------------------------------------------
```

### 停止方法

```bash
# Ctrl+C で停止
# または別のターミナルから
pkill -f serial_receiver.py
```

## 🔧 プログラムの機能

### 1. シリアル信号受信

- RS422 経由でエレベーターコマンドを受信
- リアルタイムでターミナルに表示
- 16 進数とコマンド解析の両方を表示

### 2. コマンド解析

- **階数設定**: データ番号 0x0010 → 階数指定
- **扉制御**: データ番号 0x0011 → 開扉/閉扉/停止
- **荷重設定**: データ番号 0x0003 → 荷重値

### 3. 自動応答

- 受信したコマンドに対して ACK 応答を自動送信
- エレベーター（PC）側の通信確認に使用

## 🌐 ネットワーク設定

### 固定 IP アドレスの設定

`/etc/dhcpcd.conf`を編集：

```bash
sudo nano /etc/dhcpcd.conf
```

以下を追加：

```
# 有線接続の固定IP設定
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

## 🔍 トラブルシューティング

### よくある問題と解決方法

#### 1. シリアルポートアクセス権限エラー

```bash
# エラー: Permission denied: '/dev/ttyUSB0'
# 解決方法:
sudo usermod -a -G dialout pi
sudo reboot
```

#### 2. USB-シリアル変換器が認識されない

```bash
# デバイスの確認
lsusb
dmesg | grep -i usb

# ドライバーの確認
lsmod | grep usbserial

# 必要に応じてドライバーをインストール
sudo apt install linux-modules-extra-$(uname -r)
```

#### 3. Python 依存関係エラー

```bash
# pyserialを再インストール
pip3 uninstall pyserial
pip3 install pyserial
```

#### 4. シリアルポートが見つからない

```bash
# 利用可能なシリアルポートを確認
ls -la /dev/tty*
ls -la /dev/serial/by-id/

# プログラムのSERIAL_PORTを適切なデバイスに変更
# 例: /dev/ttyUSB1, /dev/ttyACM0 など
```

## 📊 動作確認手順

### 1. エレベーター（PC）側の準備

- backend プログラムを起動
- シリアルポート設定を確認（COM1 など）
- RS422-USB 変換器を接続

### 2. Raspberry Pi 側の準備

- RS422-USB 変換器を接続
- シリアルポートデバイスを確認
- プログラムを実行

### 3. 通信テスト

1. PC 側でエレベーター操作（階数選択、扉制御など）
2. Raspberry Pi 側でシリアル信号受信を確認
3. ターミナルに表示される内容を確認

### 4. 期待される結果

- PC 側の操作が Raspberry Pi 側でリアルタイム表示
- コマンドが正しく解析されて表示
- ACK 応答が自動送信される

## 🔧 設定のカスタマイズ

### シリアルポート設定の変更

`serial_receiver.py`の冒頭で設定を変更：

```python
# 設定
SERIAL_PORT = '/dev/ttyUSB1'  # デバイスに合わせて変更
BAUDRATE = 19200              # 必要に応じて変更
DATABITS = 8
PARITY = 'E'  # Even parity
STOPBITS = 1
TIMEOUT = 1.0
```

### ログファイル出力の追加

プログラムを修正してファイルにもログを出力：

```python
# ログファイルに出力
with open('/var/log/elevator_serial.log', 'a') as f:
    f.write(f"[{timestamp}] {hex_data} | {parsed_command}\n")
```

## 🤖 自動運転パイロット（NEW!）

### auto_pilot.py - 完全自動運転システム

Raspberry Pi が自律的にエレベーターを制御する高度な自動運転システムです。

#### 🎯 機能概要

- **完全自動運転**: 人間の介入なしでエレベーターを自動制御
- **インテリジェントシナリオ**: 時間帯に応じた運転パターン
- **乗客シミュレーション**: リアルな乗客の出入りをシミュレート
- **動的負荷調整**: 乗客数に応じた荷重制御

#### 🚀 使用方法

```bash
# 自動運転パイロットを実行
cd /home/pi/elevator-serial
python3 auto_pilot.py
```

#### 📊 運転シナリオ

1. **朝の通勤ラッシュ (7:00-9:00)**

   - 乗客率: 80%
   - 主要目標階: 2F, 3F, 4F, 5F
   - 1 階からの乗車が多い

2. **昼間の軽い利用 (9:00-17:00)**

   - 乗客率: 30%
   - 全階均等利用
   - バランスの取れた運転

3. **夕方の帰宅ラッシュ (17:00-19:00)**

   - 乗客率: 70%
   - 主要目標階: 1F
   - 上階からの降車が多い

4. **深夜の軽い利用 (22:00-6:00)**
   - 乗客率: 10%
   - 低層階中心の運転

#### ⚙️ 設定パラメータ

```python
config = {
    'passenger_weight': 60,      # 1人あたりの重量（kg）
    'max_passengers': 10,        # 最大乗客数
    'min_floor': 1,              # 最低階
    'max_floor': 5,              # 最高階
    'operation_interval': 15,    # 運転間隔（秒）
    'door_open_time': 8,         # ドア開放時間（秒）
    'travel_time_per_floor': 3,  # 1階あたりの移動時間（秒）
    'passenger_boarding_time': 2, # 乗客乗降時間（秒）
}
```

#### 📈 実行例

```
🏢 SEC-3000H エレベーターシミュレーター
🤖 自動運転パイロットシステム v1.0
==================================================
✅ シリアルポート /dev/ttyUSB0 に接続しました
🎯 目標階数を設定: 1F
⚖️ 荷重を設定: 0kg (0人)
🤖 自動運転パイロットを有効にしました
🚀 エレベーター自動運転パイロットシステムを開始しました

🚀 自動運転開始: 1F → 3F
🚪 扉を開いています...
🏢 1F: 乗車 4人, 降車 0人 → 総乗客数 4人 (240kg)
⚖️ 荷重を設定: 240kg (4人)
🚪 扉を閉じています...
🎯 目標階数を設定: 3F
🏃 移動中... 予想時間: 6秒
✅ 3F に到着しました
🚪 扉を開いています...
🏢 3F: 乗車 1人, 降車 2人 → 総乗客数 3人 (180kg)
⚖️ 荷重を設定: 180kg (3人)
🚪 扉を閉じています...
🏁 運転完了: 現在 3F, 乗客 3人
⏰ 次の運転まで 17秒待機...
```

#### 🎭 シナリオ自動切替

システムは現在時刻に基づいて自動的にシナリオを切り替えます：

```python
def change_scenario(self):
    current_hour = datetime.now().hour

    if 7 <= current_hour <= 9:
        self.current_scenario = self.scenarios[0]  # 朝の通勤ラッシュ
    elif 17 <= current_hour <= 19:
        self.current_scenario = self.scenarios[2]  # 夕方の帰宅ラッシュ
    elif 22 <= current_hour or current_hour <= 6:
        self.current_scenario = self.scenarios[3]  # 深夜の軽い利用
    else:
        self.current_scenario = self.scenarios[1]  # 昼間の軽い利用
```

### auto_mode_receiver.py - 受信専用モード

PC 側からの信号を受信して状態を監視するプログラムです。

#### 使用方法

```bash
# 自動運転モード受信プログラムを実行
python3 auto_mode_receiver.py
```

#### 機能

- PC 側からのエレベーター制御信号を受信
- 階数、荷重、扉状態の監視
- 乗客数の自動計算
- 通信ログの記録

## 📺 エレベーター表示システム with RTSP ストリーミング（NEW!）

### elevator_display_streamer.py - 高度な表示システム

エレベーターの状態を視覚的に表示し、RTSP ストリーミングで配信する高度なシステムです。

#### 🎯 機能概要

- **リアルタイム画像生成**: エレベーターの状態に応じて 1920x1080 の高解像度画像を生成
- **RTSP ストリーミング**: ネットワーク経由でリアルタイム映像配信
- **インテリジェント表示**: 移動中は「現在階 ⇒ 行先階」、停止中は「現在階」のみ表示
- **ストレージ効率**: 画像ファイルを上書きしてストレージを節約
- **遠距離視認性**: 大きなフォントサイズで遠くからでも判別可能

#### 🚀 セットアップ手順

```bash
# ストリーミング版の依存関係をインストール
cd /home/pi/elevator-serial
chmod +x install_streaming.sh
./install_streaming.sh
```

#### 📋 システム要件

- **Raspberry Pi 4B** (推奨: 4GB RAM 以上)
- **Python 3.7+**
- **OpenCV with GStreamer サポート**
- **十分なネットワーク帯域** (RTSP ストリーミング用)

#### 🔧 使用方法

```bash
# 手動実行
source ~/elevator_env/bin/activate
python3 elevator_display_streamer.py

# systemdサービスとして実行
sudo systemctl start elevator-display
sudo systemctl status elevator-display

# ログ確認
journalctl -u elevator-display -f
```

#### 📺 RTSP ストリーミング接続

```bash
# VLCプレイヤーで視聴
vlc rtsp://[RaspberryPi_IP]:8554/

# FFmpegで録画
ffmpeg -i rtsp://[RaspberryPi_IP]:8554/ -c copy output.mp4

# ブラウザで視聴（WebRTC対応プレイヤー使用）
# 例: http://[監視PC]/player?stream=rtsp://[RaspberryPi_IP]:8554/
```

#### 🎨 表示仕様

- **解像度**: 1920x1080 (Full HD)
- **背景色**: #b2ffff (ライトシアン)
- **文字色**: #000000 (黒)
- **フォントサイズ**: 200px (遠距離視認対応)
- **更新頻度**: リアルタイム（状態変更時即座に更新）

#### 📊 表示パターン

1. **移動中の表示**

   ```
   1F ⇒ 5F
   ```

2. **停止中の表示**

   ```
   3F
   ```

3. **初期状態**
   ```
   ---
   ```

#### 📈 実行例

```
🏢 SEC-3000H エレベーターシミュレーター 表示システム
📺 RTSPストリーミング対応 v1.0
============================================================
🖼️ 表示画像を更新: ---
📺 RTSPストリーミングを開始しました (ポート: 8554)
📺 接続URL: rtsp://[RaspberryPi_IP]:8554/
✅ シリアルポート /dev/ttyUSB0 に接続しました
🤖 自動運転モードを有効にしました
🚀 エレベーター表示システム with RTSPストリーミングを開始しました
📺 RTSP URL: rtsp://192.168.1.100:8554/
🖼️ 画像ファイル: /tmp/elevator_display.jpg

📨 受信: ENQ(05) 局番号:0001 CMD:W 現在階数: 1F データ:0001 チェックサム:4F
🏢 現在階数を更新: 1F (データ値: 0001)
🖼️ 表示画像を更新: 1F

📨 受信: ENQ(05) 局番号:0001 CMD:W 行先階: 3F データ:0003 チェックサム:51
🎯 行先階を更新: 3F (データ値: 0003)
🖼️ 表示画像を更新: 1F ⇒ 3F

📨 受信: ENQ(05) 局番号:0001 CMD:W 現在階数: 3F データ:0003 チェックサム:53
🏢 現在階数を更新: 3F (データ値: 0003)
🖼️ 表示画像を更新: 3F

📊 現在の状態: 3F (停止中), 乗客数=2人, 荷重=120kg
```

#### ⚙️ 設定パラメータ

```python
# 画像設定
image_width = 1920          # 画像幅
image_height = 1080         # 画像高さ
background_color = '#b2ffff' # 背景色
text_color = '#000000'      # 文字色
font_size = 200             # フォントサイズ

# RTSPストリーミング設定
rtsp_port = 8554            # RTSPポート
frame_rate = 30             # フレームレート (FPS)
bitrate = 2000              # ビットレート (kbps)

# ファイル設定
image_path = '/tmp/elevator_display.jpg'  # 画像保存パス（上書き）
```

#### 🔧 トラブルシューティング

##### RTSP ストリーミングが開始できない

```bash
# GStreamerの確認
gst-inspect-1.0 --version
gst-inspect-1.0 x264enc

# 必要なプラグインのインストール
sudo apt install gstreamer1.0-plugins-ugly gstreamer1.0-libav

# ポートの確認
sudo netstat -tlnp | grep 8554
```

##### 画像が生成されない

```bash
# フォントの確認
fc-list | grep -i dejavu
ls -la /usr/share/fonts/truetype/dejavu/

# Pillowの確認
python3 -c "from PIL import Image, ImageDraw, ImageFont; print('PIL OK')"
```

##### ネットワーク接続の問題

```bash
# ファイアウォール設定
sudo ufw status
sudo ufw allow 8554/tcp

# ネットワーク設定確認
ip addr show
ping [クライアントIP]
```

#### 📱 クライアント側での視聴

##### VLC Media Player

1. VLC を起動
2. メディア → ネットワークストリームを開く
3. URL: `rtsp://[RaspberryPi_IP]:8554/`
4. 再生ボタンをクリック

##### FFmpeg（録画・変換）

```bash
# ライブ録画
ffmpeg -i rtsp://192.168.1.100:8554/ -c copy elevator_$(date +%Y%m%d_%H%M%S).mp4

# リアルタイム変換（WebM形式）
ffmpeg -i rtsp://192.168.1.100:8554/ -c:v libvpx-vp9 -b:v 1M output.webm
```

##### ブラウザ視聴（WebRTC 変換が必要）

```bash
# Node.js WebRTCサーバーの例
npm install node-webrtc
# 別途WebRTCゲートウェイの設定が必要
```

#### 🔄 systemd サービス管理

```bash
# サービス開始
sudo systemctl start elevator-display

# サービス停止
sudo systemctl stop elevator-display

# サービス再起動
sudo systemctl restart elevator-display

# サービス状態確認
sudo systemctl status elevator-display

# 自動起動有効化
sudo systemctl enable elevator-display

# 自動起動無効化
sudo systemctl disable elevator-display

# ログ確認（リアルタイム）
journalctl -u elevator-display -f

# ログ確認（過去分）
journalctl -u elevator-display --since "1 hour ago"
```

#### 📊 パフォーマンス監視

```bash
# CPU使用率確認
top -p $(pgrep -f elevator_display_streamer)

# メモリ使用量確認
ps aux | grep elevator_display_streamer

# ネットワーク使用量確認
iftop -i eth0

# ディスク使用量確認
df -h /tmp
```

#### 🔒 セキュリティ設定

```bash
# RTSPアクセス制限（iptablesの例）
sudo iptables -A INPUT -p tcp --dport 8554 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8554 -j DROP

# UFWでの設定
sudo ufw allow from 192.168.1.0/24 to any port 8554
```

## 📝 次のステップ

### MQTT 送信機能の追加（後日実装予定）

1. MQTT クライアントライブラリの追加
2. 監視室 PC 向けのデータフォーマット定義
3. 受信データの MQTT 送信機能実装
4. 接続状態監視とエラーハンドリング

### 期待される拡張

```python
# 将来の実装例
import paho.mqtt.client as mqtt

# MQTT設定
MQTT_BROKER = "192.168.1.200"  # 監視室PC
MQTT_PORT = 1883
MQTT_TOPIC = "elevator/status"

# 受信データをMQTTで送信
mqtt_client.publish(MQTT_TOPIC, json.dumps({
    "timestamp": timestamp,
    "command": parsed_command,
    "raw_data": hex_data
}))
```

## 📞 サポート

### 問題報告

問題が発生した場合は、以下の情報を含めて報告してください：

1. Raspberry Pi OS のバージョン
2. Python のバージョン
3. エラーメッセージ
4. シリアルポート設定
5. ハードウェア構成

### 有用なコマンド

```bash
# システム情報
cat /etc/os-release
python3 --version
uname -a

# シリアルポート情報
ls -la /dev/ttyUSB*
dmesg | grep tty
lsusb

# プロセス確認
ps aux | grep serial_receiver
```

## 📄 ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。
