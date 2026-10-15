"""기존 카카오맵 장소 검색 API로 사건 주변 병원·학교 직선거리를 조회합니다."""

import httpx
from .normalization import get_json, measurement


# 기존 위험도 정책의 500m 범위에서만 확인하며 결과가 없을 때 임의 거리를 만들지 않습니다.
def fetch_data(query: dict) -> dict:
    fields = {
        'nearby_hospital_distance_m': 'HP8',
        'nearby_school_distance_m': 'SC4',
    }
    source = 'KAKAO_LOCAL'
    now = query['now']

    def empty(status, reason=None):
        item = {
            'value': None,
            'observed_at': None,
            'source': source,
            'unit': 'm',
            'status': status,
        }
        if reason:
            item['reason'] = reason
        return item

    if not query.get('mapped') or not query.get('api_key'):
        return {field: empty('NO_MAPPING') for field in fields}

    try:
        latitude = float(query['latitude'])
        longitude = float(query['longitude'])
        from math import isfinite
        if not (
            isfinite(latitude)
            and isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise ValueError('좌표 범위 오류')
    except (KeyError, TypeError, ValueError, OverflowError):
        return {field: empty('INVALID') for field in fields}

    result = {}
    for field, category in fields.items():
        try:
            payload = get_json(
                'https://dapi.kakao.com/v2/local/search/category.json',
                {
                    'category_group_code': category,
                    'x': str(longitude), 'y': str(latitude),
                    'radius': 500, 'sort': 'distance', 'size': 1,
                },
                {'Authorization': 'KakaoAK ' + query['api_key']},
            )
            documents = payload['documents']
            if not isinstance(documents, list):
                raise ValueError('장소 검색 응답 구조 오류')
            if not documents:
                result[field] = empty('NO_DATA', 'NO_MATCH_WITHIN_500M')
                continue
            distance = float(documents[0]['distance'])
            # 장소 데이터의 관측 시각 대신 이번 API 조회 시각을 기록합니다.
            result[field] = measurement(
                distance,
                now,
                source,
                'm',
                now,
                query.get('max_age_sec', 3600),
            )
        except httpx.TimeoutException:
            result[field] = empty('TIMEOUT')
        except (httpx.HTTPError, KeyError, ValueError, TypeError, OverflowError):
            result[field] = empty('ERROR')
    return result
