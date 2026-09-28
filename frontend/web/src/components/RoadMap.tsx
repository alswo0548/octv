import { useState } from "react";
import { mock, incidentById, type Incident } from "@octv/shared";
export function RoadMap({
  incident: d,
  index = 0,
  active = "A",
  onRoute,
  onIncident,
  overview = false,
  incidentIds = [],
}: {
  incident: Incident;
  index?: number;
  active?: string;
  onRoute?: (id: string) => void;
  onIncident?: (id: string) => void;
  overview?: boolean;
  incidentIds?: string[];
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <div className="map-shell">
      <svg
        className="road-map"
        viewBox="0 0 820 430"
        role="img"
        aria-label={overview ? "사건 위치 도식" : "기관별 후보 경로 도식"}
      >
        <rect width="820" height="430" fill="#0b1925" />
        <path
          d="M260 -30L370 150 230 320 210 480"
          stroke="#1b4355"
          strokeWidth="42"
          fill="none"
        />
        <g fill="none" stroke="#293f50" strokeWidth="9" strokeLinejoin="round">
          <path d="M-20 140L425 255 850 395M30 385L800 65M145 440L280 90 700 105M145 340L620 340 780 -20M-10 245L440 280 740 130" />
        </g>
        <g fill="#7593a6" fontSize="12">
          <text x="355" y="405">
            {d.location.split(" ")[1]}
          </text>
          <text x="560" y="65">
            도심 간선도로
          </text>
          <text x="42" y="200">
            {d.location.split(" ")[0]}
          </text>
        </g>
        {overview ? (
          incidentIds.map((id) => {
            const v = incidentById(id),
              { x, y } = v.mapPoint;
            const color =
              v.priority === "P1"
                ? "#f49caa"
                : v.priority === "P2"
                  ? "#ffcf8d"
                  : "#78cae7";
            return (
              <g
                key={id}
                role="button"
                tabIndex={0}
                aria-label={`${id} 사건 상세`}
                data-incident-id={id}
                transform={`translate(${x} ${y})`}
                className={
                  "incident-pin" +
                  (hovered === id ? " pin-active" : "") +
                  (hovered && hovered !== id ? " pin-paused" : "")
                }
                style={{ color }}
                onMouseEnter={() => setHovered(id)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(id)}
                onBlur={() => setHovered(null)}
                onClick={() => onIncident?.(id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onIncident?.(id);
                  }
                }}
              >
                <ellipse className="pin-ripple" cx="0" cy="0" rx="21" ry="8" />
                <ellipse
                  className="pin-ripple ripple-late"
                  cx="0"
                  cy="0"
                  rx="21"
                  ry="8"
                />
                <g className="pin-body">
                  <path
                    d="M0 0 C-4 -7 -13 -17 -13 -25 A13 13 0 1 1 13 -25 C13 -17 4 -7 0 0Z"
                    fill="currentColor"
                  />
                  <circle cx="0" cy="-25" r="5" fill="#102332" />
                </g>
                <text
                  x={x > 630 ? -18 : 18}
                  y="-10"
                  textAnchor={x > 630 ? "end" : "start"}
                  fill="#d9e7f1"
                  fontSize="13"
                >
                  {v.priority} · {id}
                </text>
              </g>
            );
          })
        ) : (
          <>
            {mock.mapPaths[index].map((p, i) => (
              <path
                key={p}
                role="button"
                tabIndex={0}
                aria-label={"경로 " + "ABC"[i]}
                onClick={() => onRoute?.("ABC"[i])}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onRoute?.("ABC"[i]);
                }}
                d={p}
                fill="none"
                stroke={
                  i === 1
                    ? "#eb8e91"
                    : active === "ABC"[i]
                      ? "#ffcd78"
                      : "#62bbef"
                }
                strokeWidth={active === "ABC"[i] ? 6 : 3}
                strokeOpacity={active === "ABC"[i] ? 1 : 0.6}
                strokeDasharray={i === 1 ? "8 7" : undefined}
              />
            ))}
            <circle
              cx={[145, 110, 175][index]}
              cy={[340, 295, 365][index]}
              r="8"
              fill="#73dceb"
            />
            <text x="80" y="397" fill="#9ce7f0" fontSize="13">
              출발 기관
            </text>
            <circle cx="690" cy="105" r="9" fill="#ff8d9f" />
            <text x="665" y="80" fill="#ffa4b2" fontSize="13">
              사건 현장
            </text>
            <text x="460" y="222" fill="#ffcd78">
              A
            </text>
            <text x="557" y="364" fill="#ed8c98">
              B · 통제
            </text>
            <text x="380" y="79" fill="#87c8f0">
              C
            </text>
          </>
        )}
      </svg>
      <div className="map-caption">
        <span>{overview ? "사건 위치 · 우선순위" : d.location}</span>
      </div>
    </div>
  );
}
