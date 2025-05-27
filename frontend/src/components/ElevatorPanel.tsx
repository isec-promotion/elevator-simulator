import React from "react";
import { ElevatorStatus } from "../App";
import "./ElevatorPanel.css";

interface ElevatorPanelProps {
  status: ElevatorStatus;
  onFloorSelect: (floor: string) => void;
  onDoorControl: (action: "open" | "close" | "stop") => void;
}

const ElevatorPanel: React.FC<ElevatorPanelProps> = ({
  status,
  onFloorSelect,
  onDoorControl,
}) => {
  const floors = ["B1F", "1F", "2F", "3F", "4F", "5F"];

  const getFloorButtonClass = (floor: string) => {
    let className = "floor-button";
    if (status.currentFloor === floor) {
      className += " current";
    }
    if (status.targetFloor === floor) {
      className += " target";
    }
    return className;
  };

  const getDoorStatusText = () => {
    switch (status.doorStatus) {
      case "open":
        return "開";
      case "closed":
        return "閉";
      case "opening":
        return "開中";
      case "closing":
        return "閉中";
      default:
        return "不明";
    }
  };

  const getDoorStatusClass = () => {
    return `door-status ${status.doorStatus}`;
  };

  return (
    <div className="elevator-panel">
      <div className="panel-header">
        <h2>🏢 エレベーター操作パネル</h2>
      </div>

      <div className="status-display">
        <div className="current-floor">
          <span className="label">現在階:</span>
          <span className="value">{status.currentFloor || "--"}</span>
        </div>

        <div className="target-floor">
          <span className="label">行先階:</span>
          <span className="value">{status.targetFloor || "--"}</span>
        </div>

        <div className="elevator-state">
          <span className="label">状態:</span>
          <span className={`value ${status.isMoving ? "moving" : "stopped"}`}>
            {status.isMoving ? "移動中" : "停止中"}
          </span>
        </div>
      </div>

      <div className="floor-buttons">
        <h3>階数選択</h3>
        <div className="button-grid">
          {floors.map((floor) => (
            <button
              key={floor}
              className={getFloorButtonClass(floor)}
              onClick={() => onFloorSelect(floor)}
              disabled={status.isMoving}
            >
              {floor}
            </button>
          ))}
        </div>
      </div>

      <div className="door-controls">
        <h3>扉制御</h3>
        <div className="door-status-display">
          <span className="label">扉状態:</span>
          <span className={getDoorStatusClass()}>{getDoorStatusText()}</span>
        </div>

        <div className="door-buttons">
          <button
            className="door-button open"
            onClick={() => onDoorControl("open")}
            disabled={
              status.isMoving ||
              status.doorStatus === "opening" ||
              status.doorStatus === "open"
            }
          >
            🔓 開扉
          </button>

          <button
            className="door-button close"
            onClick={() => onDoorControl("close")}
            disabled={
              status.isMoving ||
              status.doorStatus === "closing" ||
              status.doorStatus === "closed"
            }
          >
            🔒 閉扉
          </button>

          <button
            className="door-button stop"
            onClick={() => onDoorControl("stop")}
            disabled={
              status.doorStatus === "closed" || status.doorStatus === "open"
            }
          >
            ⏹️ 停止
          </button>
        </div>
      </div>

      <div className="load-display">
        <span className="label">荷重:</span>
        <span className="value">
          {status.loadWeight !== null ? `${status.loadWeight}kg` : "--"}
        </span>
      </div>
    </div>
  );
};

export default ElevatorPanel;
