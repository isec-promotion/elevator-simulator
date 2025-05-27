import React from "react";
import { ElevatorStatus } from "../App";
import "./StatusMonitor.css";

interface StatusMonitorProps {
  status: ElevatorStatus;
  connectionStatus: "connecting" | "connected" | "disconnected" | "error";
}

const StatusMonitor: React.FC<StatusMonitorProps> = ({
  status,
  connectionStatus,
}) => {
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

  const getElevatorConnectionStatusColor = () => {
    switch (status.connectionStatus) {
      case "connected":
        return "#4CAF50";
      case "disconnected":
        return "#9E9E9E";
      case "error":
        return "#F44336";
      default:
        return "#9E9E9E";
    }
  };

  const getElevatorConnectionStatusText = () => {
    switch (status.connectionStatus) {
      case "connected":
        return "接続中";
      case "disconnected":
        return "切断";
      case "error":
        return "エラー";
      default:
        return "不明";
    }
  };

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return "--";
    try {
      return new Date(timestamp).toLocaleTimeString("ja-JP");
    } catch {
      return "--";
    }
  };

  return (
    <div className="status-monitor">
      <div className="monitor-header">
        <h2>📊 システム状態監視</h2>
      </div>

      <div className="status-section">
        <h3>WebSocket 接続</h3>
        <div className="status-item">
          <span className="label">状態:</span>
          <span
            className="status-indicator"
            style={{ backgroundColor: getConnectionStatusColor() }}
          />
          <span className="value">{getConnectionStatusText()}</span>
        </div>
      </div>

      <div className="status-section">
        <h3>エレベーター通信</h3>
        <div className="status-item">
          <span className="label">RS422 状態:</span>
          <span
            className="status-indicator"
            style={{ backgroundColor: getElevatorConnectionStatusColor() }}
          />
          <span className="value">{getElevatorConnectionStatusText()}</span>
        </div>
        <div className="status-item">
          <span className="label">最終通信:</span>
          <span className="value">
            {formatTimestamp(status.lastCommunication)}
          </span>
        </div>
      </div>

      <div className="status-section">
        <h3>エレベーター詳細状態</h3>
        <div className="status-grid">
          <div className="status-item">
            <span className="label">現在階:</span>
            <span className="value">{status.currentFloor || "--"}</span>
          </div>
          <div className="status-item">
            <span className="label">行先階:</span>
            <span className="value">{status.targetFloor || "--"}</span>
          </div>
          <div className="status-item">
            <span className="label">扉状態:</span>
            <span className={`value door-${status.doorStatus}`}>
              {status.doorStatus === "open" && "開"}
              {status.doorStatus === "closed" && "閉"}
              {status.doorStatus === "opening" && "開中"}
              {status.doorStatus === "closing" && "閉中"}
              {status.doorStatus === "unknown" && "不明"}
            </span>
          </div>
          <div className="status-item">
            <span className="label">移動状態:</span>
            <span className={`value ${status.isMoving ? "moving" : "stopped"}`}>
              {status.isMoving ? "移動中" : "停止中"}
            </span>
          </div>
          <div className="status-item">
            <span className="label">荷重:</span>
            <span className="value">
              {status.loadWeight !== null ? `${status.loadWeight}kg` : "--"}
            </span>
          </div>
        </div>
      </div>

      <div className="status-section">
        <h3>Raspberry Pi 状態</h3>
        <div className="raspberry-pi-status">
          <div className="status-item">
            <span className="label">LED 制御:</span>
            <span className="value">
              {status.connectionStatus === "connected" ? "動作中" : "停止中"}
            </span>
          </div>
          <div className="status-item">
            <span className="label">信号受信:</span>
            <span className="value">
              {status.lastCommunication ? "正常" : "未受信"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StatusMonitor;
