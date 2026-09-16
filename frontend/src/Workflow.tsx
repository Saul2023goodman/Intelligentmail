import type { CSSProperties } from "react";
import type { Workspace } from "./core";
import { stages, stageMetric } from "./workflow-model";
import Icon from "./Icon";

export default function Workflow({
  data,
  selected,
  onSelect,
  zoom,
}: {
  data: Workspace | null;
  selected: string;
  onSelect: (id: string) => void;
  zoom: number;
}) {
  return (
    <div
      className="graph-size"
      style={{ width: 1300 * zoom, height: 870 * zoom }}
    >
      <div className="graph" style={{ transform: `scale(${zoom})` }}>
        <div className="lane intake-lane">
          <span>00 / 读取 → 入库 → 比对查重</span>
        </div>
        <div className="lane green-lane">
          <span>01 / PREPARE & AUTHORIZE</span>
        </div>
        <div className="lane rose-lane">
          <span>02 / RESOLVE & RECONCILE</span>
        </div>
        <div className="lane purple-lane">
          <span>03 / REPLY & FOLLOW UP</span>
        </div>
        <svg className="connections" viewBox="0 0 1300 870" aria-hidden="true">
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
          <g transform="translate(0 110)">
            {[
              "M495 298H515V173H550",
              "M515 298V423H550",
              "M750 173H790",
              "M990 173H1040",
              "M1013 173V298H1040",
              "M1013 298V423H1040",
              "M1013 298H1010V354H890V382",
              "M790 423H750",
              "M1140 466V520H645V466",
              "M550 423H520V360H395V341",
              "M1140 216V257",
              "M1140 339V570H650V602",
              "M890 570V602",
              "M890 686V723H395V341",
            ].map((d, i) => (
              <path
                key={d}
                d={d}
                className={i > 7 ? "dashed" : ""}
                markerEnd="url(#arrow)"
              />
            ))}
          </g>
          {[
            "M255 117H295",
            "M495 117H550",
            "M155 367V205H395V159",
            "M645 159V215H395V367",
            "M750 117H765V534H750",
            "M495 409H510V117H550",
          ].map((d, index) => (
            <path
              key={d}
              d={d}
              className={index === 5 ? "dashed" : ""}
              markerEnd="url(#arrow)"
            />
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
