"""Regenerate database/ERD.svg from feature SQL using only Python's standard library."""
from pathlib import Path
from html import escape
import re
ROOT = Path(__file__).resolve().parents[1]
T, E = {}, {}
for p in sorted((ROOT / 'backend/app').rglob('*.sql')):
    s=p.read_text(encoding='utf-8')
    for name,values in re.findall(r'CREATE TYPE (\w+) AS ENUM \((.*?)\);',s,re.S):
        E[name]=re.findall("'([^']+)'",values)
    for name,body in re.findall(r'CREATE TABLE (\w+) \((.*?)\n\);',s,re.S):
        fields=[]
        for line in body.splitlines():
            line=line.strip().rstrip(',')
            if not line or line.startswith('CONSTRAINT'): continue
            col,typ,tail=re.match(r'(\w+) (\w+(?:\([\d,]+\))?)(.*)',line).groups()
            ref=re.search(r'REFERENCES (\w+)\((\w+)\)',tail)
            fields.append((col,typ,tail,ref.groups() if ref else None))
        title=re.search(rf"COMMENT ON TABLE {name} IS '([^']+)'",s).group(1)
        T[name]=(title,fields)
positions={
 'region':(0,0),'agencies':(1,0),'users':(2,0),'monitoring_settings':(3,0),
 'cctvs':(0,1),'incidents':(1,1),'incident_agency_recommendations':(2,1),'route_candidates':(3,1),
 'weather_alerts':(0,2),'incident_contexts':(1,2),'incident_assessments':(2,2),'notifications':(3,2),
 'incident_support_requests':(2,3)}
notes={
 'users':['U1  lower(btrim(email))'],
 'cctvs':['U2  provider + external_cctv_id'],
 'incidents':['U3  incident_no','U4  cctv_id + hazard_type + dedup_key','U4  WHERE status IN (DETECTED, CONFIRMED, SENT)'],
 'weather_alerts':['U5  external_alert_id + region_code'],
 'incident_agency_recommendations':['U6  incident_id + agency_id'],
 'notifications':['U7  agency_recommendation_id + user_id']}
W,H=3260,2440;parts=[]
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
parts.append('''<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#9aabc0"/></marker></defs>
<style>text{font-family:"Noto Sans KR",sans-serif;fill:#172b46} .head{fill:white;font-weight:700}.field{font-family:"DejaVu Sans Mono",monospace;font-size:13px}.type{font-family:"DejaVu Sans Mono",monospace;font-size:12px;fill:#4e6076}</style>''')
parts.append(f'<rect width="{W}" height="{H}" fill="#f3f6fa"/>')
def text(x,y,s,size=16,cls='',fill=None):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" class="{cls}"'+(f' style="fill:{fill}"' if fill else '')+f'>{escape(s)}</text>')
text(42,53,'OCTV 최종 ERD  |  PostgreSQL',32)
text(42,85,'13 tables  ·  123 columns  ·  19 foreign keys  ·  10 ENUMs  ·  7 additional UNIQUE rules  |  2026-10-02',18)
text(42,115,'PK 기본키   FK 외래키   NN 필수값   NULL 선택값   U1–U7 고유 규칙   •   화살표: 참조하는 테이블 → 참조 대상',17)
BW=740;ROW=26;GAP=65
boxes={}
for name,(gx,gy) in positions.items():
    x=42+gx*(BW+GAP);y=160+gy*510
    title,fields=T[name];height=76+ROW*len(fields)+26*len(notes.get(name,[]))+10
    boxes[name]=(x,y,BW,height)
# Draw relationships behind opaque tables; the FK target remains explicit in each row.
for name,(title,fields) in T.items():
    for col,typ,tail,ref in fields:
        if not ref: continue
        x,y,w,h=boxes[name];xx,yy,ww,hh=boxes[ref[0]]
        if x==xx:
            sx=x+w*.75;sy=y if yy<y else y+h;ex=xx+ww*.75;ey=yy+hh if yy<y else yy
            mid=(sy+ey)/2;d=f'M{sx} {sy} V{mid} H{ex} V{ey}'
        else:
            sx=x if xx<x else x+w;sy=y+44;ex=xx+ww if xx<x else xx;ey=yy+44
            mid=(sx+ex)/2;d=f'M{sx} {sy} H{mid} V{ey} H{ex}'
        parts.append(f'<path d="{d}" fill="none" stroke="#9aabc0" stroke-width="1.5" stroke-dasharray="5 4" marker-end="url(#arrow)"/>')
for name,(x,y,w,h) in boxes.items():
    title,fields=T[name]
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="white" stroke="#cad5e2"/>')
    parts.append(f'<path d="M{x+7} {y} H{x+w-7} Q{x+w} {y} {x+w} {y+7} V{y+55} H{x} V{y+7} Q{x} {y} {x+7} {y}" fill="#244563"/>')
    text(x+14,y+24,name,20,'head');text(x+14,y+45,title,14,'head')
    for i,(col,typ,tail,ref) in enumerate(fields):
        ry=y+76+i*ROW
        if i%2==0:parts.append(f'<rect x="{x+1}" y="{ry-18}" width="{w-2}" height="{ROW}" fill="#f4f7fa"/>')
        key=('PK ' if 'PRIMARY KEY' in tail else '')+('FK ' if ref else '')+('NN' if ('NOT NULL' in tail or 'PRIMARY KEY' in tail) else 'NULL')
        label=typ.lower().replace('decimal','numeric')
        if typ=='TIMESTAMP':label='timestamp (without time zone)'
        text(x+12,ry,col,13,'field');text(x+352,ry,label,12,'type');text(x+651,ry,key,12)
    ny=y+76+len(fields)*ROW+4
    for note in notes.get(name,[]):text(x+14,ny,note,14,fill='#125ca6');ny+=26
# Source-of-truth references and ENUM values are part of the image, not hidden in a caption.
text(42,1775,'수정 기준과 저장 규칙',23)
for i,line in enumerate([
 '새 첨부 반영: FALSE_POSITIVE · COMPLETED · captured_at NOT NULL',
 'U1: 이메일의 앞뒤 공백과 대소문자를 무시합니다.',
 'U4: RESOLVED / FALSE_POSITIVE 이후 같은 키로 재발 사건 저장 가능',
 'U6: 사건·기관별 현재 추천 1행. 재평가는 기존 행 갱신',
 'U7: 같은 기관추천의 사용자별 알림 중복 생성 방지',
 '상황 스냅샷·평가·경로·지원요청은 여러 행 저장 가능',
 '모든 FK의 실제 참조 컬럼과 NULL 조건: 기능별 sql/*.sql',
 '자세한 UNIQUE 기준: docs/ERD_UNIQUES.md',
 '원본 첨부: database/reference/ERD_2026-10-02.png']):text(42,1810+i*29,line,17)
text(2457,1720,'FK 참조 목록',23)
for i,(source,col,target,key) in enumerate((name,c,ref[0],ref[1]) for name,(_,fields) in T.items() for c,_,_,ref in fields if ref):
    text(2457,1754+i*17,f'{source}.{col} → {target}.{key}',10)
text(42,2130,'ENUM 허용값',23)
for i,(name,values) in enumerate(E.items()):
    col=i//5;row=i%5;x=42+col*1610;y=2170+row*48
    text(x,y,name,16,fill='#244563');text(x+350,y,' | '.join(values),14)
parts.append('</svg>')
(ROOT/'database/ERD.svg').write_text('\n'.join(parts),encoding='utf-8')
print('Generated ERD.svg:',len(T),'tables,',sum(len(v[1]) for v in T.values()),'columns')
