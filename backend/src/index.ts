import { Hono } from "hono";
import { serve } from "@hono/node-server";
import { cors } from "hono/cors";
import { WebSocketServer } from "ws";
import { createServer } from "http";
import { ElevatorController } from "./elevator.js";
import { WebSocketHandler } from "./websocket.js";
import { AutoModeController } from "./autoMode.js";

const app = new Hono();

// CORS設定
app.use(
  "/*",
  cors({
    origin: ["http://localhost:5173", "http://127.0.0.1:5173"], // Viteのデフォルトポート
    credentials: true,
  })
);

// 疑似モードの判定（環境変数またはコマンドライン引数から）
const simulationMode =
  process.env.SIMULATION_MODE === "true" ||
  process.argv.includes("--simulation") ||
  process.argv.includes("--sim");

// 自動運転モードの判定
const autoMode =
  process.env.AUTO_MODE === "true" || process.argv.includes("--auto");

if (simulationMode) {
  console.log("🎭 Starting in simulation mode");
} else {
  console.log("🔌 Starting in normal mode");
}

if (autoMode) {
  console.log("🤖 Auto mode enabled");
}

// エレベーター制御インスタンス
const elevatorController = new ElevatorController(simulationMode);

// 自動運転制御インスタンス
const autoModeController = new AutoModeController(elevatorController);

// ヘルスチェック
app.get("/health", (c) => {
  return c.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    elevator: elevatorController.getStatus(),
  });
});

// エレベーター状態取得API
app.get("/api/elevator/status", (c) => {
  return c.json(elevatorController.getStatus());
});

// 階数設定API
app.post("/api/elevator/floor", async (c) => {
  try {
    // 自動運転モードが有効な場合は手動操作を拒否
    if (autoModeController.isEnabled()) {
      return c.json(
        {
          error: "Manual operation is disabled during auto mode",
          message: "自動運転モード中は手動操作できません",
        },
        403
      );
    }

    const { floor } = await c.req.json();

    if (!floor || typeof floor !== "string") {
      return c.json({ error: "Invalid floor parameter" }, 400);
    }

    const result = await elevatorController.setFloor(floor);

    if (result.success) {
      return c.json({
        success: true,
        message: `Floor set to ${floor}`,
        data: result.data,
      });
    } else {
      return c.json(
        {
          success: false,
          error: result.error,
        },
        500
      );
    }
  } catch (error) {
    console.error("Floor setting error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 扉制御API
app.post("/api/elevator/door", async (c) => {
  try {
    // 自動運転モードが有効な場合は手動操作を拒否
    if (autoModeController.isEnabled()) {
      return c.json(
        {
          error: "Manual operation is disabled during auto mode",
          message: "自動運転モード中は手動操作できません",
        },
        403
      );
    }

    const { action } = await c.req.json();

    if (!action || !["open", "close", "stop"].includes(action)) {
      return c.json({ error: "Invalid door action" }, 400);
    }

    const result = await elevatorController.controlDoor(action);

    if (result.success) {
      return c.json({
        success: true,
        message: `Door ${action} command sent`,
        data: result.data,
      });
    } else {
      return c.json(
        {
          success: false,
          error: result.error,
        },
        500
      );
    }
  } catch (error) {
    console.error("Door control error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 通信ログ取得API
app.get("/api/elevator/logs", (c) => {
  return c.json(elevatorController.getLogs());
});

// 荷重設定API
app.post("/api/elevator/weight", async (c) => {
  try {
    const { weight } = await c.req.json();

    if (weight === undefined || typeof weight !== "number" || weight < 0) {
      return c.json({ error: "Invalid weight parameter" }, 400);
    }

    const result = await elevatorController.setWeight(weight);

    if (result.success) {
      return c.json({
        success: true,
        message: `Weight set to ${weight}kg`,
        data: result.data,
      });
    } else {
      return c.json(
        {
          success: false,
          error: result.error,
        },
        500
      );
    }
  } catch (error) {
    console.error("Weight setting error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 通信設定API
app.post("/api/elevator/config", async (c) => {
  try {
    const config = await c.req.json();
    const result = await elevatorController.updateConfig(config);

    if (result.success) {
      return c.json({
        success: true,
        message: "Configuration updated",
        data: result.data,
      });
    } else {
      return c.json(
        {
          success: false,
          error: result.error,
        },
        500
      );
    }
  } catch (error) {
    console.error("Config update error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 自動運転モード状態取得API
app.get("/api/auto/status", (c) => {
  return c.json({
    autoMode: autoModeController.getStatus(),
    elevator: elevatorController.getStatus(),
  });
});

// 自動運転モード開始API
app.post("/api/auto/start", async (c) => {
  try {
    // 自動運転モードが有効でない場合は手動操作を無効化
    if (autoModeController.isEnabled()) {
      return c.json({ error: "Auto mode is already running" }, 400);
    }

    await autoModeController.start();

    return c.json({
      success: true,
      message: "Auto mode started",
      data: autoModeController.getStatus(),
    });
  } catch (error) {
    console.error("Auto mode start error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 自動運転モード停止API
app.post("/api/auto/stop", async (c) => {
  try {
    await autoModeController.stop();

    return c.json({
      success: true,
      message: "Auto mode stopped",
      data: autoModeController.getStatus(),
    });
  } catch (error) {
    console.error("Auto mode stop error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 自動運転ログ取得API
app.get("/api/auto/logs", (c) => {
  return c.json(autoModeController.getAutoLogs());
});

// 自動運転設定更新API
app.post("/api/auto/config", async (c) => {
  try {
    const config = await c.req.json();
    autoModeController.updateConfig(config);

    return c.json({
      success: true,
      message: "Auto mode configuration updated",
      data: autoModeController.getConfig(),
    });
  } catch (error) {
    console.error("Auto mode config update error:", error);
    return c.json({ error: "Internal server error" }, 500);
  }
});

// 404ハンドラー
app.notFound((c) => {
  return c.json({ error: "Not Found" }, 404);
});

// エラーハンドラー
app.onError((err, c) => {
  console.error("Server error:", err);
  return c.json({ error: "Internal Server Error" }, 500);
});

const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;

// Honoサーバーを起動
const server = serve({
  fetch: app.fetch,
  port: PORT,
});

// WebSocketサーバーを別ポートで作成
const wsPort = PORT + 1;
const wss = new WebSocketServer({ port: wsPort });

// WebSocketハンドラーを初期化
const wsHandler = new WebSocketHandler(elevatorController);
wsHandler.initialize(wss);

// エレベーターコントローラーにWebSocketハンドラーを設定
elevatorController.setWebSocketHandler(wsHandler);

console.log(
  `🚀 Elevator Simulator Backend Server running on http://localhost:${PORT}`
);
console.log(`📡 WebSocket Server running on ws://localhost:${wsPort}`);
console.log(`🏗️  Frontend should be running on http://localhost:5173`);

// エレベーター制御システム初期化
elevatorController
  .initialize()
  .then(async () => {
    console.log("✅ Elevator Controller initialized");

    // 自動運転モードが有効な場合は自動開始
    if (autoMode) {
      console.log("🤖 Starting auto mode automatically...");
      try {
        await autoModeController.start();
        console.log("✅ Auto mode started automatically");
      } catch (error) {
        console.error("❌ Failed to start auto mode:", error);
      }
    }
  })
  .catch((error) => {
    console.error("❌ Elevator Controller initialization failed:", error);
  });

// グレースフルシャットダウン
const gracefulShutdown = async (signal: string) => {
  console.log(`\n🛑 Received ${signal}, shutting down gracefully...`);

  try {
    // 自動運転モードを停止
    if (autoModeController.isEnabled()) {
      console.log("🛑 Stopping auto mode...");
      await autoModeController.stop();
      console.log("✅ Auto mode stopped");
    }

    // エレベーターコントローラーを切断
    console.log("🛑 Disconnecting elevator controller...");
    await elevatorController.disconnect();
    console.log("✅ Elevator Controller disconnected");

    // WebSocketサーバーを閉じる
    console.log("🛑 Closing WebSocket server...");
    wss.close(() => {
      console.log("✅ WebSocket server closed");
    });

    // HTTPサーバーを閉じる（Honoのserveは直接close()メソッドを持たない場合があるため）
    console.log("🛑 Closing HTTP server...");
    try {
      if (server && typeof server.close === "function") {
        server.close(() => {
          console.log("✅ HTTP server closed");
          console.log("👋 Goodbye!");
          process.exit(0);
        });
      } else {
        console.log("✅ HTTP server shutdown initiated");
        console.log("👋 Goodbye!");
        process.exit(0);
      }
    } catch (error) {
      console.log("✅ HTTP server shutdown completed");
      console.log("👋 Goodbye!");
      process.exit(0);
    }

    // 強制終了のタイムアウト（5秒）
    setTimeout(() => {
      console.error("❌ Forced shutdown after timeout");
      process.exit(1);
    }, 5000);
  } catch (error) {
    console.error("❌ Error during shutdown:", error);
    process.exit(1);
  }
};

process.on("SIGINT", () => gracefulShutdown("SIGINT"));
process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));

// 未処理の例外をキャッチ
process.on("uncaughtException", (error) => {
  console.error("❌ Uncaught Exception:", error);
  gracefulShutdown("uncaughtException");
});

process.on("unhandledRejection", (reason, promise) => {
  console.error("❌ Unhandled Rejection at:", promise, "reason:", reason);
  gracefulShutdown("unhandledRejection");
});
