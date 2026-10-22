export const CCTV_SOURCE = "경찰청 도시교통정보센터(UTIC) 제공";

/** Display credit only; preserve any existing camera caption. */
export function cctvCaption(caption = "") {
  return caption.includes(CCTV_SOURCE)
    ? caption
    : caption
      ? `${caption} / ${CCTV_SOURCE}`
      : CCTV_SOURCE;
}
