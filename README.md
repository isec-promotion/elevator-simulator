# SEC-3000H エレベーターシミュレーター

SEC-3000H エレベーター制御システムのシミュレーターです。RS422 通信プロトコルを使用してエレベーターとの通信をシミュレートし、Web ベースの UI で操作・監視が可能です。

## 🏗️ システム構成

```
elevator-simulator/
├── backend/                 # Node.js + TypeScript バックエンド
│   ├── src/
│   │   ├── index.ts        # メインサーバー
│   │   ├── elevator.ts     # エレベーター制御クラス
│   │   └── websocket.ts    # WebSocket通信ハンドラー
│   ├── package.json
│   └── tsconfig.json
├── frontend/               # React + TypeScript フロントエンド
│   ├── src/
│   │   ├── components/     # Reactコンポーネント
│   │   ├── App.tsx        # メインアプリケーション
│   │   └── main.tsx       # エントリーポイント
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
└── README.md
```

## 🚀 機能

### エレベーター制御

- **階数選択**: B1F〜5F の階数選択
- **扉制御**: 開扉・閉扉・停止操作
- **状態監視**: 現在階、行先階、扉状態、移動状態、荷重の監視

### 通信機能

- **RS422 シミュレーション**: SEC-3000H 通信プロトコルの実装
- **リアルタイム通信**: WebSocket によるリアルタイム状態更新
- **通信ログ**: 送受信データの詳細ログ表示

### UI 機能

- **レスポンシブデザイン**: PC・タブレット・スマートフォン対応
- **リアルタイム更新**: 状態変化の即座な反映
- **視覚的フィードバック**: アニメーション・色分けによる状態表示

## 🛠️ 技術スタック

### バックエンド

- **Node.js** - JavaScript 実行環境
- **TypeScript** - 型安全な JavaScript
- **Hono** - Web フレームワーク
- **ws** - WebSocket 通信
- **serialport** - シリアル通信（RS422）

### フロントエンド

- **React** - UI ライブラリ
- **TypeScript** - 型安全な JavaScript
- **Vite** - 高速ビルドツール
- **CSS3** - スタイリング（グラデーション・アニメーション）

## 📋 セットアップ

### 前提条件

- Node.js 18.0.0 以上
- npm または yarn

### インストール

1. **プロジェクトのクローン**

```bash
git clone <repository-url>
cd elevator-simulator
```

2. **バックエンドのセットアップ**

```bash
cd backend
npm install
```

3. **フロントエンドのセットアップ**

```bash
cd ../frontend
npm install
```

### 開発環境での実行

1. **バックエンドサーバーの起動**

```bash
cd backend
npm run dev
```

サーバーは http://localhost:3000 で起動します。

2. **フロントエンドの起動**

```bash
cd frontend
npm run dev
```

フロントエンドは http://localhost:5173 で起動します。

### 本番環境でのビルド

1. **バックエンドのビルド**

```bash
cd backend
npm run build
npm start
```

2. **フロントエンドのビルド**

```bash
cd frontend
npm run build
npm run preview
```

## 🔧 設定

### シリアルポート設定

`backend/src/elevator.ts` でシリアルポートの設定を変更できます：

```typescript
this.config = {
  serialPort: "COM1", // Windowsの場合
  // serialPort: "/dev/ttyUSB0", // Linuxの場合
  baudRate: 9600,
  dataBits: 8,
  parity: "even",
  stopBits: 1,
  timeout: 3000,
  retryCount: 8,
};
```

### WebSocket 設定

デフォルトでは以下のポートを使用します：

- バックエンド: 3000 番ポート
- WebSocket: 3000 番ポート（HTTP 同一ポート）
- フロントエンド: 5173 番ポート

## 📡 通信プロトコル

### SEC-3000H 通信仕様

- **通信方式**: RS422
- **ボーレート**: 9600bps
- **データビット**: 8bit
- **パリティ**: Even
- **ストップビット**: 1bit

### コマンド形式

```
ENQ + 局番号(4桁) + コマンド(1文字) + データ番号(4桁) + データ(4桁HEX) + チェックサム(2桁HEX)
```

### 主要コマンド

- `0x0001`: 現在階取得
- `0x0002`: 行先階取得
- `0x0003`: 荷重取得
- `0x0010`: 階数設定
- `0x0011`: 扉制御

## 🎮 使用方法

1. **システム起動**: バックエンドとフロントエンドを起動
2. **接続確認**: WebSocket 接続状態を確認
3. **階数選択**: 操作パネルで行先階を選択
4. **扉操作**: 開扉・閉扉ボタンで扉を制御
5. **状態監視**: リアルタイムで状態変化を監視
6. **ログ確認**: 通信ログで詳細な通信内容を確認

## 🔍 トラブルシューティング

### 接続エラー

- シリアルポートの設定を確認
- ポート番号の重複をチェック
- デバイスドライバーの確認

### WebSocket 接続エラー

- ファイアウォール設定の確認
- ポート番号の競合をチェック
- ブラウザのコンソールでエラー確認

### シミュレーションモード

実際のハードウェアが接続されていない場合、自動的にシミュレーションモードで動作します。

## 📝 ライセンス

MIT License

## 🤝 貢献

プルリクエストやイシューの報告を歓迎します。

## 📞 サポート

技術的な質問やサポートが必要な場合は、イシューを作成してください。

---

**開発者**: SEC-3000H エレベーターシミュレーター開発チーム  
**バージョン**: 1.0.0  
**最終更新**: 2025 年 5 月 27 日
