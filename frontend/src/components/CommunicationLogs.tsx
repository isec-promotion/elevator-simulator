import React, { useEffect, useRef } from "react";
import { CommunicationLog } from "../App";
import "./CommunicationLogs.css";

interface CommunicationLogsProps {
  logs: CommunicationLog[];
}

const CommunicationLogs: React.FC<CommunicationLogsProps> = ({ logs }) => {
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 新しいログが追加されたら自動スクロール（ログコンテナ内のみ）
    if (logsEndRef.current) {
      const container = logsEndRef.current.closest(".table-body");
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [logs]);

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString("ja-JP", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return timestamp;
    }
  };

  const getLogRowClass = (log: CommunicationLog) => {
    let className = `log-row ${log.direction}`;
    if (log.result === "error") {
      className += " error";
    } else if (log.result === "timeout") {
      className += " timeout";
    }
    return className;
  };

  const getDirectionIcon = (direction: string) => {
    switch (direction) {
      case "send":
        return "📤";
      case "receive":
        return "📥";
      case "system":
        return "⚙️";
      default:
        return "📄";
    }
  };

  const getDirectionText = (direction: string) => {
    switch (direction) {
      case "send":
        return "送信";
      case "receive":
        return "受信";
      case "system":
        return "システム";
      default:
        return direction;
    }
  };

  const getResultIcon = (result: string) => {
    switch (result) {
      case "success":
        return "✅";
      case "error":
        return "❌";
      case "timeout":
        return "⏰";
      default:
        return "❓";
    }
  };

  const formatData = (data: string, direction: string) => {
    if (!data) return "--";

    // シミュレーションデータの場合
    if (data.startsWith("Simulation:")) {
      return data;
    }

    // HEXデータの場合、見やすく整形
    if (data.match(/^[0-9a-fA-F]+$/)) {
      // SEC-3000H形式のシリアル通信データを解析
      if (data.length >= 20) {
        const formatted = data
          .toUpperCase()
          .replace(/(.{2})/g, "$1 ")
          .trim();

        // ENQ + 局番号 + コマンド + データ番号 + データ + チェックサム の形式で表示
        const enq = data.substring(0, 2);
        const station = data.substring(2, 10);
        const cmd = data.substring(10, 12);
        const dataNum = data.substring(12, 20);
        const dataValue = data.substring(20, 28);
        const checksum = data.substring(28, 32);

        return `${enq} ${station} ${cmd} ${dataNum} ${dataValue} ${checksum}`;
      }

      return data
        .toUpperCase()
        .replace(/(.{2})/g, "$1 ")
        .trim();
    }

    return data;
  };

  return (
    <div className="communication-logs">
      <div className="logs-header">
        <h2>📡 通信ログ</h2>
        <div className="logs-stats">
          <span className="log-count">総件数: {logs.length}</span>
          <span className="success-count">
            成功: {logs.filter((log) => log.result === "success").length}
          </span>
          <span className="error-count">
            エラー: {logs.filter((log) => log.result === "error").length}
          </span>
        </div>
      </div>

      <div className="logs-container">
        <div className="logs-table">
          <div className="table-header">
            <div className="col-time">時刻</div>
            <div className="col-direction">方向</div>
            <div className="col-data">データ</div>
            <div className="col-result">結果</div>
            <div className="col-message">メッセージ</div>
          </div>

          <div className="table-body">
            {logs.length === 0 ? (
              <div className="no-logs">
                <span>📭 ログがありません</span>
              </div>
            ) : (
              logs.map((log, index) => (
                <div key={index} className={getLogRowClass(log)}>
                  <div className="col-time" title={log.timestamp}>
                    {formatTimestamp(log.timestamp)}
                  </div>
                  <div className="col-direction">
                    <span className="direction-icon">
                      {getDirectionIcon(log.direction)}
                    </span>
                    <span className="direction-text">
                      {getDirectionText(log.direction)}
                    </span>
                  </div>
                  <div className="col-data" title={log.data}>
                    <code>{formatData(log.data, log.direction)}</code>
                  </div>
                  <div className="col-result">
                    <span className="result-icon">
                      {getResultIcon(log.result)}
                    </span>
                    <span className="result-text">{log.result}</span>
                  </div>
                  <div className="col-message">{log.message || "--"}</div>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>

      <div className="logs-footer">
        <div className="legend">
          <span className="legend-item">
            <span className="legend-icon">📤</span>
            <span>送信</span>
          </span>
          <span className="legend-item">
            <span className="legend-icon">📥</span>
            <span>受信</span>
          </span>
          <span className="legend-item">
            <span className="legend-icon">⚙️</span>
            <span>システム</span>
          </span>
          <span className="legend-item">
            <span className="legend-icon">✅</span>
            <span>成功</span>
          </span>
          <span className="legend-item">
            <span className="legend-icon">❌</span>
            <span>エラー</span>
          </span>
          <span className="legend-item">
            <span className="legend-icon">⏰</span>
            <span>タイムアウト</span>
          </span>
        </div>
      </div>
    </div>
  );
};

export default CommunicationLogs;
