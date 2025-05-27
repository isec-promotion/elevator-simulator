import { Hono } from "hono";
import { serve } from "@hono/node-server";
import { cors } from "hono/cors";
import { WebSocketServer } from "ws";
import { createServer } from "http";
import { ElevatorController } from "./elevator.js";
import { WebSocketHandler } from "./websocket.js";

const app = new Hono();

// CORS設定
app.use(
  "/*",
  cors({
    origin: ["http://localhost:5173", "http://127.0.0.1:5173"], // Viteのデフォルトポート
    credentials: true,
  })
);

// エレベーター制御インスタンス
const elevatorController = new ElevatorController();

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

// HTTPサーバーとWebSocketサーバーを作成
const server = createServer();
const wss = new WebSocketServer({ server });

// WebSocketハンドラーを初期化
const wsHandler = new WebSocketHandler(elevatorController);
wsHandler.initialize(wss);

// Honoアプリをサーバーにマウント
server.on(
  "request",
  serve({
    fetch: app.fetch,
    port: PORT,
  })
);

// サーバー開始
server.listen(PORT, () => {
  console.log(
    `🚀 Elevator Simulator Backend Server running on http://localhost:${PORT}`
  );
  console.log(`📡 WebSocket Server running on ws://localhost:${PORT}`);
  console.log(`🏗️  Frontend should be running on http://localhost:5173`);

  // エレベーター制御システム初期化
  elevatorController
    .initialize()
    .then(() => {
      console.log("✅ Elevator Controller initialized");
    })
    .catch((error) => {
      console.error("❌ Elevator Controller initialization failed:", error);
    });
});

// グレースフルシャットダウン
process.on("SIGINT", async () => {
  console.log("\n🛑 Shutting down server...");

  try {
    await elevatorController.disconnect();
    console.log("✅ Elevator Controller disconnected");
  } catch (error) {
    console.error("❌ Error during shutdown:", error);
  }

  server.close(() => {
    console.log("✅ Server closed");
    process.exit(0);
  });
});

process.on("SIGTERM", async () => {
  console.log("\n🛑 Received SIGTERM, shutting down gracefully...");

  try {
    await elevatorController.disconnect();
    console.log("✅ Elevator Controller disconnected");
  } catch (error) {
    console.error("❌ Error during shutdown:", error);
  }

  server.close(() => {
    console.log("✅ Server closed");
    process.exit(0);
  });
});
