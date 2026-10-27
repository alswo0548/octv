import { hazardLabel } from "@octv/shared";
import { formatSeoulTime } from "../incidentData";

export type Preview = { state: string; frame: null | {
  captured_at: string; width: number; height: number; image: string;
  detections: { hazard_type: string; confidence: number; bbox: number[]; model_version: string }[];
} };
export function InferencePreview({ data, error }: { data: Preview | null; error: string | null }) {
  const result = {data, error};
  const frame = result.data?.frame;
  return <section className="panel" style={{ padding: 16 }}>
    <h3>실제 YOLO 추론 프레임</h3>
    <p>위 영상과 별도인 실제 분석 시점의 정지 프레임입니다. 박스는 이 프레임에 대한 추론 결과이며 사건 확정과 다릅니다.</p>
    {result.error && <p role="alert">추론 출력 조회 불가 · v5 API와 Runtime 실행을 확인해주세요.</p>}
    {!frame && !result.error && <p>{result.data?.state === "OFF" ? "감시 중지" : "최근 30초 이내 추론 프레임 없음 · 수집 상태와 Runtime 확인 필요"}</p>}
    {frame && <>
      <svg viewBox={`0 0 ${frame.width} ${frame.height}`} style={{ width: "100%", maxHeight: 380 }} role="img" aria-label="실제 추론 프레임과 탐지 박스">
        <image href={`data:image/jpeg;base64,${frame.image}`} width={frame.width} height={frame.height}/>
        {frame.detections.map((d,i) => <g key={i}>
          <rect x={d.bbox[0]} y={d.bbox[1]} width={Math.max(0,d.bbox[2]-d.bbox[0])} height={Math.max(0,d.bbox[3]-d.bbox[1])} fill="none" stroke="#ffff00" strokeWidth={3}/>
          <text x={d.bbox[0]} y={Math.max(24,d.bbox[1]-8)} fill="#fff" stroke="#000" strokeWidth={1} paintOrder="stroke" fontSize={Math.max(16,frame.width/55)}>{hazardLabel(d.hazard_type)} {(d.confidence*100).toFixed(1)}%</text>
        </g>)}
      </svg>
      <p>{formatSeoulTime(frame.captured_at)} · 해당 프레임 탐지 {frame.detections.length}개 · {frame.detections.length ? [...new Set(frame.detections.map(d=>d.model_version))].join(" / ") : "이 프레임에서 임계값을 통과한 탐지 없음"}</p>
    </>}
  </section>;
}
