/** 화면 숨김은 현재 로그인 세션에 한정. 원본 DB·모바일 전달 이력을 삭제하지 않습니다. */
let version = -1;
let hidden = new Set<number>();
export function hiddenIncidentIds(sessionVersion: number): Set<number> {
  if (version !== sessionVersion) { version = sessionVersion; hidden = new Set(); }
  return hidden;
}
export function hideIncident(sessionVersion: number, id: number): void {
  hiddenIncidentIds(sessionVersion).add(id);
}
export function restoreHiddenIncidents(sessionVersion: number): void {
  hiddenIncidentIds(sessionVersion).clear();
}
