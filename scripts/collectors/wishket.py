"""위시켓 수집기 (구현 보류).

이용약관 크롤링 조항 확인 후 구현 예정.
BaseCollector를 상속하면 run_collect.py에 "wishket"으로 등록만 하면 됨.

수집 대상: https://www.wishket.com/project/
렌더링 방식: JS 동적 (Playwright 필요)
robots.txt: /project/ 허용, Crawl-delay 5초 요구

TODO:
  [ ] wishket.com 이용약관 크롤링 금지 조항 확인
  [ ] 프로젝트 목록 페이지 CSS 셀렉터 파악
  [ ] 무한 스크롤 또는 페이지네이션 방식 확인
  [ ] WishketCollector(BaseCollector) 구현
        - collect(query, pages) → list[dict]
        - _parse_item() → _item() 매핑
        - Crawl-delay 5초 준수
"""

from .base import BaseCollector


class WishketCollector(BaseCollector):
    source_name = "wishket"

    def collect(self, **kwargs) -> list[dict]:
        raise NotImplementedError(
            "위시켓 수집기는 미구현 상태입니다. "
            "이용약관 확인 후 구현 예정."
        )
