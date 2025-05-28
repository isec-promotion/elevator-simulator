import React, { useState, useEffect } from "react";
import ElevatorPanel from "./components/ElevatorPanel";
import StatusMonitor from "./components/StatusMonitor";
import CommunicationLogs from "./components/CommunicationLogs";
import ElevatorAnimation from "./components/ElevatorAnimation";
import AutoModePanel, {
  AutoModeStatus,
  AutoModeLog,
  AutoModeConfig,
} from "./components/AutoModePanel";
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

  // 自動運転モード関連の状態
  const [autoModeStatus, setAutoModeStatus] = useState<AutoModeStatus | null>(
    null
  );
  const [autoModeLogs, setAutoModeLogs] = useState<AutoModeLog[]>([]);
  const [isAutoModeEnabled, setIsAutoModeEnabled] = useState<boolean>(false);

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

          // 自動運転モードの状態を確認
          checkAutoModeStatus();
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

  // 自動運転モード関連の関数
  const checkAutoModeStatus = async () => {
    try {
      const response = await fetch("http://localhost:3000/api/auto/status");
      if (response.ok) {
        const data = await response.json();
        setAutoModeStatus(data.autoMode);
        setIsAutoModeEnabled(true);

        // 自動運転ログも取得
        const logsResponse = await fetch("http://localhost:3000/api/auto/logs");
        if (logsResponse.ok) {
          const logsData = await logsResponse.json();
          setAutoModeLogs(logsData);
        }
      } else {
        setIsAutoModeEnabled(false);
      }
    } catch (error) {
      console.log("Auto mode not available:", error);
      setIsAutoModeEnabled(false);
    }
  };

  const handleStartAutoMode = async () => {
    try {
      const response = await fetch("http://localhost:3000/api/auto/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        setAutoModeStatus(data.data);
        console.log("Auto mode started:", data.message);
      } else {
        const errorData = await response.json();
        console.error("Failed to start auto mode:", errorData.error);
        alert(
          `自動運転開始に失敗しました: ${errorData.message || errorData.error}`
        );
      }
    } catch (error) {
      console.error("Error starting auto mode:", error);
      alert("自動運転開始中にエラーが発生しました");
    }
  };

  const handleStopAutoMode = async () => {
    try {
      const response = await fetch("http://localhost:3000/api/auto/stop", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        setAutoModeStatus(data.data);
        console.log("Auto mode stopped:", data.message);
      } else {
        const errorData = await response.json();
        console.error("Failed to stop auto mode:", errorData.error);
        alert(`自動運転停止に失敗しました: ${errorData.error}`);
      }
    } catch (error) {
      console.error("Error stopping auto mode:", error);
      alert("自動運転停止中にエラーが発生しました");
    }
  };

  const handleUpdateAutoConfig = async (config: Partial<AutoModeConfig>) => {
    try {
      const response = await fetch("http://localhost:3000/api/auto/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(config),
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Auto mode config updated:", data.message);
        // 設定更新後、状態を再取得
        await checkAutoModeStatus();
      } else {
        const errorData = await response.json();
        console.error("Failed to update auto mode config:", errorData.error);
        alert(`設定更新に失敗しました: ${errorData.error}`);
      }
    } catch (error) {
      console.error("Error updating auto mode config:", error);
      alert("設定更新中にエラーが発生しました");
    }
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
            <AutoModePanel
              autoModeStatus={autoModeStatus}
              autoModeLogs={autoModeLogs}
              onStartAutoMode={handleStartAutoMode}
              onStopAutoMode={handleStopAutoMode}
              onUpdateConfig={handleUpdateAutoConfig}
              isAutoModeEnabled={isAutoModeEnabled}
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
