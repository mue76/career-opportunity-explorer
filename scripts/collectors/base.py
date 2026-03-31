from abc import ABC, abstractmethod


FIELDS = ("title", "organization", "type", "description", "keywords", "link", "note")


class BaseCollector(ABC):
    """공통 수집기 인터페이스.

    모든 수집기는 이 클래스를 상속하고 collect()를 구현한다.
    반환 데이터는 FIELDS 기준의 dict 리스트.
    """

    source_name: str = ""

    @abstractmethod
    def collect(self, **kwargs) -> list[dict]:
        """기회 데이터를 수집해 표준 dict 리스트로 반환."""

    @staticmethod
    def _item(
        title: str = "",
        organization: str = "",
        kind: str = "",        # dict key는 "type" — 예약어 충돌 방지
        description: str = "",
        keywords: list[str] | None = None,
        link: str = "",
        note: str = "",
    ) -> dict:
        """표준 필드 구조의 dict 생성 헬퍼."""
        return {
            "title": title,
            "organization": organization,
            "type": kind,
            "description": description,
            "keywords": keywords if keywords is not None else [],
            "link": link,
            "note": note,
        }
