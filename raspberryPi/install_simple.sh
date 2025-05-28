#!/bin/bash

# Raspberry Pi 4B シリアル信号受信プログラム インストールスクリプト（シンプル版）
# 使用方法: chmod +x install_simple.sh && ./install_simple.sh

set -e  # エラー時に停止

# 色付きメッセージ用の関数
print_info() {
    echo -e "\033[1;34m[INFO]\033[0m $1"
}

print_success() {
    echo -e "\033[1;32m[SUCCESS]\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

print_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
}

# 設定変数
PROJECT_DIR="/home/pi/elevator-serial"
PYTHON_VERSION="python3"

print_info "🚀 Raspberry Pi 4B シリアル信号受信プログラムのインストールを開始します..."
echo "システム構成: PC（エレベーター） → USB-RS422 → Raspberry Pi 4B → MQTT → 監視室PC"
echo "                                              ↑ このプログラム"
echo

# 1. システムの更新
print_info "📦 システムパッケージを更新中..."
sudo apt update && sudo apt upgrade -y

# 2. 必要なパッケージのインストール
print_info "📦 必要なパッケージをインストール中..."
sudo apt install -y python3 python3-pip

# 3. プロジェクトディレクトリの作成
print_info "📁 プロジェクトディレクトリを作成中..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 4. 現在のディレクトリからファイルをコピー
print_info "📋 プログラムファイルをコピー中..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cp "$SCRIPT_DIR/serial_receiver.py" "$PROJECT_DIR/"
cp "$SCRIPT_DIR/requirements_simple.txt" "$PROJECT_DIR/"

# ファイルの権限設定
chmod +x "$PROJECT_DIR/serial_receiver.py"

# 5. Python依存関係のインストール
print_info "📦 Python依存関係をインストール中..."
pip3 install -r requirements_simple.txt

# 6. ユーザーをdialoutグループに追加
print_info "👤 ユーザー権限を設定中..."
sudo usermod -a -G dialout pi

# 7. シリアルポートの確認
print_info "🔌 シリアルポートを確認中..."
if ls /dev/ttyUSB* >/dev/null 2>&1; then
    print_success "シリアルポートが見つかりました:"
    ls -la /dev/ttyUSB*
else
    print_warning "シリアルポートが見つかりません。RS422-USB変換器を接続してください。"
    echo "利用可能なシリアルデバイス:"
    ls -la /dev/tty* | grep -E "(USB|ACM)" || echo "  なし"
fi

# 8. 設定ファイルの確認
print_info "⚙️ 設定を確認中..."
echo "現在の設定:"
echo "  - プロジェクトディレクトリ: $PROJECT_DIR"
echo "  - メインプログラム: serial_receiver.py"
echo "  - シリアルポート: /dev/ttyUSB0 (デフォルト)"
echo "  - ボーレート: 9600bps"
echo "  - データビット: 8bit"
echo "  - パリティ: Even"
echo "  - ストップビット: 1bit"

# 9. テスト実行の提案
echo
print_info "📋 インストール完了後の手順:"
echo "1. RS422-USB変換器を接続してください"
echo "2. 必要に応じて設定を調整してください:"
echo "   nano $PROJECT_DIR/serial_receiver.py"
echo "3. プログラムを実行してください:"
echo "   cd $PROJECT_DIR"
echo "   python3 serial_receiver.py"
echo "4. PC（エレベーター）側からシリアル信号を送信してテストしてください"

# 10. 完了メッセージ
print_success "🎉 インストールが完了しました！"
echo
echo "🔧 有用なコマンド:"
echo "  - プログラム実行: cd $PROJECT_DIR && python3 serial_receiver.py"
echo "  - シリアルポート確認: ls -la /dev/ttyUSB*"
echo "  - プロセス確認: ps aux | grep serial_receiver"
echo "  - プロセス停止: pkill -f serial_receiver.py"
echo
echo "📊 動作確認手順:"
echo "1. PC側でbackendプログラムを起動"
echo "2. Raspberry Pi側でserial_receiver.pyを実行"
echo "3. PC側でエレベーター操作を実行"
echo "4. Raspberry Pi側でシリアル信号受信を確認"
echo
echo "📞 問題が発生した場合は、README.mdのトラブルシューティングセクションを参照してください。"

# 11. 再起動の推奨
print_warning "⚠️ ユーザー権限の変更を有効にするため、システムの再起動を推奨します。"
read -p "今すぐ再起動しますか？ (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "🔄 システムを再起動中..."
    sudo reboot
else
    print_info "後で手動で再起動してください: sudo reboot"
    echo
    print_info "再起動後、以下のコマンドでプログラムを実行できます:"
    echo "cd $PROJECT_DIR && python3 serial_receiver.py"
fi
