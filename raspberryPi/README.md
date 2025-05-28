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
├── requirements_simple.txt      # Python依存関係（シンプル版）
└── install_simple.sh            # シンプル版インストールスクリプト
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
