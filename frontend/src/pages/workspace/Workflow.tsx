import type { CSSProperties, KeyboardEvent } from "react";
import type { Workspace } from "../../core";
import type { GatewayHealth, GatewayState } from "../../core/gateway";
import {
  stages,
  stageMetric,
  GRAPH_WIDTH,
  GRAPH_HEIGHT,
} from "./workflow-model";
import Icon from "../../shared/Icon";

const GATEWAY_COPY: Record<
  GatewayState,
  { dot: string; hint: string; cta: string; pulse: boolean }
> = {
  unavailable: {
    dot: "gateway-dot grey",
    hint: "网关未启用",
    cta: "了解网关",
    pulse: false,
  },
  disconnected: {
    dot: "gateway-dot amber",
    hint: "未连接邮箱",
    cta: "连接邮箱",
    pulse: true,
  },
  mismatch: {
    dot: "gateway-dot amber",
    hint: "连接了其他邮箱",
    cta: "查看连接",
    pulse: true,
  },
  connected: {
    dot: "gateway-dot green",
    hint: "网关已连接",
    cta: "管理",
    pulse: false,
  },
};

const solidEdges = [
  "M255 102H295",
  "M495 102H535",
  "M395 144V168H155V213",
  "M635 144V186H395V213",
  "M255 255H295",
  "M495 255H535",
  "M735 255H775",
  "M975 255H1040",
  "M1140 297V360",
  "M420 297V340H580V505",
  "M155 297V462H535V505",
  "M875 297V318H1005V547H1040",
  "M775 547H735",
  "M1140 589V625H690V589",
  "M635 589V610H400V297",
  "M1240 402H1248V636H635V688",
  "M875 636V688",
];

const dashedEdges = [
  "M320 297V300H210V297",
  "M875 772V790H42V176H345V213",
];

export default function Workflow({
  data,
  selected,
  onSelect,
  onManageGateway,
  gateway,
  scale,
}: {
  data: Workspace | null;
  selected: string;
  onSelect: (id: string) => void;
  /** Open the Mailbox Gateway management panel. */
  onManageGateway: () => void;
  /** Live gateway health for the selected Student. */
  gateway?: GatewayHealth;
  scale: number;
}) {
  const gatewayCopy = gateway ? GATEWAY_COPY[gateway.state] : null;
  return (
    <div
      className="graph-size"
      style={
        {
          width: GRAPH_WIDTH * scale,
          height: GRAPH_HEIGHT * scale,
        } as CSSProperties
      }
    >
      <div
        className="graph-scale"
        style={{ transform: `scale(${scale})` } as CSSProperties}
      >
        <div className="graph">
        <div className="lane intake-lane">
          <span>00 / 读取 · 入库 · 来源任务</span>
        </div>
        <div className="lane green-lane">
          <span>01 / PREPARE &amp; AUTHORIZE</span>
        </div>
        <div className="lane rose-lane">
          <span>02 / RESOLVE &amp; RECONCILE</span>
        </div>
        <div className="lane purple-lane">
          <span>03 / REPLY &amp; FOLLOW UP</span>
        </div>
        <svg
          className="connections"
          viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
          aria-hidden="true"
        >
          <defs>
            <marker
              id="arrow"
              markerWidth="7"
              markerHeight="7"
              refX="6"
              refY="3.5"
              orient="auto"
            >
              <path d="M0 0L7 3.5L0 7" fill="none" stroke="#99a9bf" />
            </marker>
          </defs>
          {solidEdges.map((d) => (
            <path key={d} d={d} markerEnd="url(#arrow)" />
          ))}
          {dashedEdges.map((d) => (
            <path key={d} d={d} className="dashed" markerEnd="url(#arrow)" />
          ))}
        </svg>
        <span className="edge-label ready-label">ready</span>
        <span className="edge-label blocked-label">needs attention</span>
        <span className="edge-label external-label">confirmed execution</span>
        {stages.map((stage) => {
          const metric = stageMetric(stage.id, data);
          const isGateway = stage.id === "mailbox" && gateway && gatewayCopy;
          const positionStyle = {
            left: stage.x,
            top: stage.y,
            "--node-color": `var(--${stage.color})`,
          } as CSSProperties;
          const inner = (
            <>
              <span className={`node-icon ${stage.color}`}>
                <Icon name={stage.icon} size={24} />
              </span>
              <span className="node-copy">
                <strong>{stage.label}</strong>
                <small>{isGateway ? gatewayCopy.hint : stage.caption}</small>
                <span className="node-count">
                  <i />
                  {metric.count} {metric.unit}
                </span>
              </span>
              {isGateway && (
                <>
                  <span
                    className={gatewayCopy.pulse ? `${gatewayCopy.dot} pulse` : gatewayCopy.dot}
                    aria-label={`Gateway ${gateway.state}`}
                    title={`Mailbox gateway: ${gateway.state}`}
                  />
                  <span className="gateway-cta">
                    <Icon
                      name={gateway.state === "connected" ? "chevron" : "plus"}
                      size={11}
                    />
                    {gatewayCopy.cta}
                  </span>
                </>
              )}
              <span className="port in" />
              <span className="port out" />
            </>
          );
          if (isGateway) {
            const activate = () => {
              onSelect(stage.id);
              onManageGateway();
            };
            return (
              <div
                key={stage.id}
                role="button"
                tabIndex={0}
                title={stage.description}
                aria-label={`${stage.label}：${gatewayCopy.hint}。打开网关管理`}
                className={`workflow-node gateway-node ${selected === stage.id ? "selected" : ""}`}
                style={positionStyle}
                onClick={activate}
                onKeyDown={(event: KeyboardEvent) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    activate();
                  }
                }}
              >
                {inner}
              </div>
            );
          }
          return (
            <button
              key={stage.id}
              title={stage.description}
              className={`workflow-node ${selected === stage.id ? "selected" : ""}`}
              style={positionStyle}
              onClick={() => onSelect(stage.id)}
              aria-pressed={selected === stage.id}
            >
              {inner}
            </button>
          );
        })}
        <div className="graph-note">
          <Icon name="shield" size={15} /> Every external action requires an
          exact-content confirmation.
        </div>
        </div>
      </div>
    </div>
  );
}
