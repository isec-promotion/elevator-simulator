import { WebSocketServer, WebSocket } from "ws";
import { ElevatorController } from "./elevator.js";

export interface WebSocketMessage {
  type: string;
  data?: any;
}

export class WebSocketHandler {
  private wss: WebSocketServer | null = null;
  private clients: Set<WebSocket> = new Set();
  private elevatorController: ElevatorController;
  private statusInterval: any = null;

  constructor(elevatorController: ElevatorController) {
    this.elevatorController = elevatorController;
  }

  initialize(wss: WebSocketServer): void {
    this.wss = wss;

    wss.on("connection", (ws: WebSocket) => {
      console.log("🔌 New WebSocket connection established");
      this.clients.add(ws);

      // 接続時に現在の状態を送信
      this.sendToClient(ws, {
        type: "status",
        data: this.elevatorController.getStatus(),
      });

      // メッセージハンドラー
      ws.on("message", async (message: Buffer) => {
        try {
          const data = JSON.parse(message.toString()) as WebSocketMessage;
          await this.handleMessage(ws, data);
        } catch (error) {
          console.error("❌ Error parsing WebSocket message:", error);
          this.sendToClient(ws, {
            type: "error",
            data: { message: "Invalid message format" },
          });
        }
      });

      // 切断ハンドラー
      ws.on("close", () => {
        console.log("🔌 WebSocket connection closed");
        this.clients.delete(ws);
      });

      // エラーハンドラー
      ws.on("error", (error) => {
        console.error("❌ WebSocket error:", error);
        this.clients.delete(ws);
      });
    });

    // 定期的な状態更新を開始
    this.startStatusBroadcast();
  }

  private async handleMessage(
    ws: WebSocket,
    message: WebSocketMessage
  ): Promise<void> {
    console.log("📨 Received WebSocket message:", message);

    try {
      switch (message.type) {
        case "setFloor":
          await this.handleSetFloor(ws, message.data?.floor);
          break;

        case "controlDoor":
          await this.handleControlDoor(ws, message.data?.action);
          break;

        case "getStatus":
          this.sendToClient(ws, {
            type: "status",
            data: this.elevatorController.getStatus(),
          });
          break;

        case "getLogs":
          this.sendToClient(ws, {
            type: "logs",
            data: this.elevatorController.getLogs(),
          });
          break;

        case "setWeight":
          await this.handleSetWeight(ws, message.data?.weight);
          break;

        case "updateConfig":
          await this.handleUpdateConfig(ws, message.data);
          break;

        case "ping":
          this.sendToClient(ws, { type: "pong" });
          break;

        default:
          this.sendToClient(ws, {
            type: "error",
            data: { message: `Unknown message type: ${message.type}` },
          });
      }
    } catch (error) {
      console.error("❌ Error handling WebSocket message:", error);
      this.sendToClient(ws, {
        type: "error",
        data: {
          message: "Internal server error",
          details: error instanceof Error ? error.message : "Unknown error",
        },
      });
    }
  }

  private async handleSetFloor(ws: WebSocket, floor: string): Promise<void> {
    if (!floor || typeof floor !== "string") {
      this.sendToClient(ws, {
        type: "error",
        data: { message: "Invalid floor parameter" },
      });
      return;
    }

    const result = await this.elevatorController.setFloor(floor);

    this.sendToClient(ws, {
      type: "floorResult",
      data: {
        success: result.success,
        floor,
        message: result.success ? `Floor set to ${floor}` : result.error,
        details: result.data,
      },
    });

    // 状態更新をブロードキャスト
    this.broadcastStatus();
  }

  private async handleControlDoor(
    ws: WebSocket,
    action: string
  ): Promise<void> {
    if (!action || !["open", "close", "stop"].includes(action)) {
      this.sendToClient(ws, {
        type: "error",
        data: { message: "Invalid door action" },
      });
      return;
    }

    const result = await this.elevatorController.controlDoor(
      action as "open" | "close" | "stop"
    );

    this.sendToClient(ws, {
      type: "doorResult",
      data: {
        success: result.success,
        action,
        message: result.success ? `Door ${action} command sent` : result.error,
        details: result.data,
      },
    });

    // 状態更新をブロードキャスト
    this.broadcastStatus();
  }

  private async handleSetWeight(ws: WebSocket, weight: number): Promise<void> {
    if (weight === undefined || typeof weight !== "number") {
      this.sendToClient(ws, {
        type: "error",
        data: { message: "Invalid weight parameter" },
      });
      return;
    }

    const result = await this.elevatorController.setWeight(weight);

    this.sendToClient(ws, {
      type: "weightResult",
      data: {
        success: result.success,
        weight,
        message: result.success ? `Weight set to ${weight}kg` : result.error,
        details: result.data,
      },
    });

    // 状態更新をブロードキャスト
    this.broadcastStatus();
  }

  private async handleUpdateConfig(ws: WebSocket, config: any): Promise<void> {
    if (!config || typeof config !== "object") {
      this.sendToClient(ws, {
        type: "error",
        data: { message: "Invalid config parameter" },
      });
      return;
    }

    const result = await this.elevatorController.updateConfig(config);

    this.sendToClient(ws, {
      type: "configResult",
      data: {
        success: result.success,
        message: result.success ? "Configuration updated" : result.error,
        config: result.data,
      },
    });
  }

  private sendToClient(ws: WebSocket, message: WebSocketMessage): void {
    if (ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify(message));
      } catch (error) {
        console.error("❌ Error sending WebSocket message:", error);
      }
    }
  }

  private broadcast(message: WebSocketMessage): void {
    this.clients.forEach((client) => {
      this.sendToClient(client, message);
    });
  }

  private broadcastStatus(): void {
    const status = this.elevatorController.getStatus();
    this.broadcast({
      type: "status",
      data: status,
    });
  }

  private broadcastLogs(): void {
    const logs = this.elevatorController.getLogs();
    this.broadcast({
      type: "logs",
      data: logs.slice(-10), // 最新10件のみ
    });
  }

  private startStatusBroadcast(): void {
    // 1秒ごとに状態をブロードキャスト（Raspberry Pi自動運転モード用に高頻度）
    this.statusInterval = setInterval(() => {
      if (this.clients.size > 0) {
        this.broadcastStatus();
        this.broadcastLogs();
      }
    }, 1000);
  }

  // 外部から状態ブロードキャストを呼び出すためのパブリックメソッド
  public triggerStatusBroadcast(): void {
    this.broadcastStatus();
    this.broadcastLogs();
  }

  private stopStatusBroadcast(): void {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
  }

  // クリーンアップ
  destroy(): void {
    this.stopStatusBroadcast();

    // 全クライアントを切断
    this.clients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.close();
      }
    });

    this.clients.clear();
    console.log("✅ WebSocket handler destroyed");
  }
}
