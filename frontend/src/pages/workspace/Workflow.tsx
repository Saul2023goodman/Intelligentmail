import type { CSSProperties } from "react";
import type { Workspace } from "../../core";
import {
  stages,
  stageMetric,
  GRAPH_WIDTH,
  GRAPH_HEIGHT,
  type Viewport,
} from "./workflow-model";
import Icon from "../../shared/Icon";

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
  view,
}: {
  data: Workspace | null;
  selected: string;
  onSelect: (id: string) => void;
  view: Viewport;
}) {
  return (
    <div
      className="graph-size"
      style={{
        width: GRAPH_WIDTH,
        height: GRAPH_HEIGHT,
        transform: `translate3d(${view.x}px, ${view.y}px, 0) scale(${view.zoom})`,
      }}
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
        {stages.map((stage) => (
          <button
            key={stage.id}
            className={`workflow-node ${selected === stage.id ? "selected" : ""}`}
            style={
              {
                left: stage.x,
                top: stage.y,
                "--node-color": `var(--${stage.color})`,
              } as CSSProperties
            }
            onClick={() => onSelect(stage.id)}
            aria-pressed={selected === stage.id}
          >
            <span className={`node-icon ${stage.color}`}>
              <Icon name={stage.icon} size={24} />
            </span>
            <span className="node-copy">
              <strong>{stage.label}</strong>
              <small>{stage.caption}</small>
              <span className="node-count">
                <i />
                {stageMetric(stage.id, data).count}{" "}
                {stageMetric(stage.id, data).unit}
              </span>
            </span>
            <span className="port in" />
            <span className="port out" />
          </button>
        ))}
        <div className="graph-note">
          <Icon name="shield" size={15} /> Every external action requires an
          exact-content confirmation.
        </div>
      </div>
    </div>
  );
}
