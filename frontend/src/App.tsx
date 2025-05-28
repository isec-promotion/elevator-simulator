import React, { useState, useEffect } from "react";
import ElevatorPanel from "./components/ElevatorPanel";
import StatusMonitor from "./components/StatusMonitor";
import CommunicationLogs from "./components/CommunicationLogs";
import ElevatorAnimation from "./components/ElevatorAnimation";
import "./App.css";

// 型定義
export interface ElevatorStatus {
  currentFloor: string | null;
  targetFloor: string | null;
  doorStatus: "open" | "closed" | "opening" | "closing" | "unknown";
  isMoving: boolean;
  loadWeight: number | null;
  connectionStatus: "connected" | "disconnected" | "error" | "simulation";
  lastCommunication: string | null;
}

export interface CommunicationLog {
  timestamp: string;
  direction: "send" | "receive" | "system";
  data: string;
  result: "success" | "error" | "timeout";
  message?: string;
}

export interface WebSocketMessage {
  type: string;
  data?: any;
}

const App: React.FC = () => {
  const [status, setStatus] = useState<ElevatorStatus>({
    currentFloor: null,
    targetFloor: null,
    doorStatus: "unknown",
    isMoving: false,
    loadWeight: null,
    connectionStatus: "disconnected",
    lastCommunication: null,
  });

  const [logs, setLogs] = useState<CommunicationLog[]>([]);
  const [wsConnection, setWsConnection] = useState<WebSocket | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<
    "connecting" | "connected" | "disconnected" | "error"
  >("disconnected");

  // WebSocket接続
  useEffect(() => {
    const connectWebSocket = () => {
      try {
        setConnectionStatus("connecting");
        const ws = new WebSocket("ws://localhost:3001");

        ws.onopen = () => {
          console.log("✅ WebSocket connected");
          setConnectionStatus("connected");
          setWsConnection(ws);

          // 初期状態を要求
          ws.send(JSON.stringify({ type: "getStatus" }));
          ws.send(JSON.stringify({ type: "getLogs" }));
        };

        ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            handleWebSocketMessage(message);
          } catch (error) {
            console.error("❌ Error parsing WebSocket message:", error);
          }
        };

        ws.onclose = () => {
          console.log("🔌 WebSocket disconnected");
          setConnectionStatus("disconnected");
          setWsConnection(null);

          // 5秒後に再接続を試行
          setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = (error) => {
          console.error("❌ WebSocket error:", error);
          setConnectionStatus("error");
        };
      } catch (error) {
        console.error("❌ Failed to connect WebSocket:", error);
        setConnectionStatus("error");
        setTimeout(connectWebSocket, 5000);
      }
    };

    connectWebSocket();

    return () => {
      if (wsConnection) {
        wsConnection.close();
      }
    };
  }, []);

  const handleWebSocketMessage = (message: WebSocketMessage) => {
    switch (message.type) {
      case "status":
        setStatus(message.data);
        break;

      case "logs":
        setLogs(message.data || []);
        break;

      case "floorResult":
      case "doorResult":
      case "weightResult":
        console.log("Command result:", message.data);
        // 結果に応じてUIを更新（必要に応じて）
        break;

      case "error":
        console.error("Server error:", message.data);
        break;

      case "pong":
        // ping/pong応答
        break;

      default:
        console.log("Unknown message type:", message.type);
    }
  };

  const sendCommand = (command: WebSocketMessage) => {
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
      wsConnection.send(JSON.stringify(command));
    } else {
      console.error("❌ WebSocket not connected");
    }
  };

  const handleFloorSelect = (floor: string) => {
    sendCommand({
      type: "setFloor",
      data: { floor },
    });
  };

  const handleDoorControl = (action: "open" | "close" | "stop") => {
    sendCommand({
      type: "controlDoor",
      data: { action },
    });
  };

  const handleWeightSet = (weight: number) => {
    sendCommand({
      type: "setWeight",
      data: { weight },
    });
  };

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case "connected":
        return "#4CAF50";
      case "connecting":
        return "#FF9800";
      case "disconnected":
        return "#9E9E9E";
      case "error":
        return "#F44336";
      default:
        return "#9E9E9E";
    }
  };

  const getConnectionStatusText = () => {
    switch (connectionStatus) {
      case "connected":
        return "接続中";
      case "connecting":
        return "接続中...";
      case "disconnected":
        return "切断";
      case "error":
        return "エラー";
      default:
        return "不明";
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>🏢 SEC-3000H エレベーターシミュレーター</h1>
        <div className="connection-status">
          <span
            className="status-indicator"
            style={{ backgroundColor: getConnectionStatusColor() }}
          />
          <span>WebSocket: {getConnectionStatusText()}</span>
        </div>
      </header>

      <main className="app-main">
        <div className="top-section">
          <div className="top-left">
            <ElevatorPanel
              status={status}
              onFloorSelect={handleFloorSelect}
              onDoorControl={handleDoorControl}
              onWeightSet={handleWeightSet}
            />
          </div>

          <div className="top-right">
            <ElevatorAnimation status={status} />
          </div>
        </div>

        <div className="bottom-section">
          <div className="bottom-left">
            <StatusMonitor
              status={status}
              connectionStatus={connectionStatus}
            />
          </div>

          <div className="bottom-right">
            <CommunicationLogs logs={logs} />
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
