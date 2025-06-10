#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
エレベーター信号スヌーピング＆RTSP映像配信システム テストスクリプト
"""

import subprocess
import time
import sys
import os
import signal
import threading
from datetime import datetime

def print_header(title):
    """ヘッダー表示"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def print_step(step, description):
    """ステップ表示"""
    print(f"\n📋 Step {step}: {description}")
    print("-" * 40)

def check_dependencies():
    """依存関係チェック"""
    print_header("依存関係チェック")
    
    # Python バージョンチェック
    python_version = sys.version_info
    print(f"🐍 Python バージョン: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 7):
        print("❌ Python 3.7以上が必要です")
        return False
    
    # 必要なモジュールチェック
    required_modules = [
        'serial',
        'PIL',
        'gi'
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} - インストール済み")
        except ImportError:
            print(f"❌ {module} - 未インストール")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"\n❌ 以下のモジュールをインストールしてください:")
        for module in missing_modules:
            if module == 'serial':
                print("   pip install pyserial")
            elif module == 'PIL':
                print("   pip install pillow")
            elif module == 'gi':
                print("   sudo apt install python3-gi python3-gi-cairo gir1.2-gstreamer-1.0")
        return False
    
    print("\n✅ 全ての依存関係が満たされています")
    return True

def check_files():
    """ファイル存在チェック"""
    print_header("ファイル存在チェック")
    
    required_files = [
        'backend-cli/elevator_serial_simulator.py',
        'raspberryPi/elevator_rtsp_snooper.py',
        'SEC-3000H構成資料.md',
        'README_ELEVATOR_SNOOPER.md'
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} - 存在")
        else:
            print(f"❌ {file_path} - 未存在")
            missing_files.append(file_path)
    
    if missing_files:
        print(f"\n❌ 以下のファイルが見つかりません:")
        for file_path in missing_files:
            print(f"   {file_path}")
        return False
    
    print("\n✅ 全ての必要ファイルが存在します")
    return True

def test_serial_simulator():
    """シリアルシミュレーターテスト"""
    print_header("シリアルシミュレーターテスト")
    
    print("🚀 エレベーターシミュレーターを5秒間実行します...")
    
    try:
        # シミュレーター起動
        process = subprocess.Popen([
            sys.executable, 
            'backend-cli/elevator_serial_simulator.py',
            '--port', 'COM99'  # 存在しないポートでテスト
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # 5秒待機
        time.sleep(5)
        
        # プロセス終了
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        
        print("📤 シミュレーター出力:")
        if stdout:
            for line in stdout.split('\n')[:10]:  # 最初の10行のみ表示
                if line.strip():
                    print(f"   {line}")
        
        if stderr and "シリアルポートエラー" in stderr:
            print("✅ 期待通りのシリアルポートエラーが発生（正常）")
            return True
        elif stdout and "シミュレーター起動" in stdout:
            print("✅ シミュレーターが正常に起動しました")
            return True
        else:
            print("❌ 予期しない動作です")
            return False
            
    except Exception as e:
        print(f"❌ テスト実行エラー: {e}")
        return False

def test_rtsp_snooper():
    """RTSPスヌーパーテスト"""
    print_header("RTSPスヌーパーテスト")
    
    print("📺 RTSPスヌーパーを5秒間実行します...")
    
    try:
        # スヌーパー起動
        process = subprocess.Popen([
            sys.executable, 
            'raspberryPi/elevator_rtsp_snooper.py',
            '--port', 'COM99'  # 存在しないポートでテスト
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # 5秒待機
        time.sleep(5)
        
        # プロセス終了
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        
        print("📤 スヌーパー出力:")
        if stdout:
            for line in stdout.split('\n')[:10]:  # 最初の10行のみ表示
                if line.strip():
                    print(f"   {line}")
        
        if stderr and "シリアル接続失敗" in stderr:
            print("✅ 期待通りのシリアル接続エラーが発生（正常）")
            return True
        elif stdout and "スヌーピングシステム起動" in stdout:
            print("✅ スヌーパーが正常に起動しました")
            return True
        else:
            print("❌ 予期しない動作です")
            return False
            
    except Exception as e:
        print(f"❌ テスト実行エラー: {e}")
        return False

def show_usage_instructions():
    """使用方法表示"""
    print_header("使用方法")
    
    print("🏢 エレベーター信号スヌーピング＆RTSP映像配信システム")
    print("\n📋 実行手順:")
    
    print("\n1️⃣ エレベーターシミュレーター起動（Windows）:")
    print("   cd backend-cli")
    print("   python elevator_serial_simulator.py --port COM27")
    
    print("\n2️⃣ RTSPスヌーパー起動（Raspberry Pi）:")
    print("   cd raspberryPi")
    print("   python3 elevator_rtsp_snooper.py --port COM27")
    
    print("\n3️⃣ RTSP映像視聴:")
    print("   VLCで以下のURLを開く:")
    print("   rtsp://[Raspberry PiのIPアドレス]:8554/elevator")
    
    print("\n📚 詳細な使用方法:")
    print("   README_ELEVATOR_SNOOPER.md を参照してください")

def show_system_info():
    """システム情報表示"""
    print_header("システム情報")
    
    print(f"🕒 テスト実行時刻: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    print(f"💻 OS: {os.name}")
    print(f"🐍 Python: {sys.version}")
    print(f"📁 作業ディレクトリ: {os.getcwd()}")
    
    # ファイル一覧
    print("\n📂 プロジェクトファイル:")
    for root, dirs, files in os.walk('.'):
        # 隠しディレクトリとファイルをスキップ
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        files = [f for f in files if not f.startswith('.')]
        
        level = root.replace('.', '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if file.endswith(('.py', '.md', '.txt')):
                print(f"{subindent}{file}")

def main():
    """メイン処理"""
    print_header("エレベーターシステム テストスクリプト")
    print("🏢 SEC-3000H仕様準拠 エレベーター信号スヌーピング＆RTSP映像配信システム")
    
    # システム情報表示
    show_system_info()
    
    # テスト実行
    tests = [
        ("依存関係チェック", check_dependencies),
        ("ファイル存在チェック", check_files),
        ("シリアルシミュレーターテスト", test_serial_simulator),
        ("RTSPスヌーパーテスト", test_rtsp_snooper)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print_step(len(results) + 1, test_name)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ テスト実行中にエラーが発生: {e}")
            results.append((test_name, False))
    
    # 結果表示
    print_header("テスト結果")
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        if result:
            print(f"✅ {test_name}: 成功")
            passed += 1
        else:
            print(f"❌ {test_name}: 失敗")
            failed += 1
    
    print(f"\n📊 テスト結果: {passed}件成功, {failed}件失敗")
    
    if failed == 0:
        print("\n🎉 全てのテストが成功しました！")
        print("システムは正常に動作する準備ができています。")
    else:
        print(f"\n⚠️ {failed}件のテストが失敗しました。")
        print("上記のエラーを修正してから再度テストしてください。")
    
    # 使用方法表示
    show_usage_instructions()
    
    return failed == 0

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n🛑 テストが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 予期しないエラーが発生しました: {e}")
        sys.exit(1)
