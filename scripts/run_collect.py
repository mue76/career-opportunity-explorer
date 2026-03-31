"""데이터 수집 CLI 진입점.

사용 예:
    python run_collect.py --source saramin --query python --pages 2
    python run_collect.py --source saramin --query "데이터 분석" --pages 1 --out ../data/raw/test.json
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from collectors.saramin import SaraminCollector
from collectors.wishket import WishketCollector
from utils.io import merge_and_save

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "raw"

COLLECTORS = {
    "saramin": SaraminCollector,
    "wishket": WishketCollector,
    # "saramin-api": SaraminAPICollector,  # TODO: Open API 키 승인 후 등록
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="커리어 기회 탐색기 — 데이터 수집기",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=list(COLLECTORS),
        default="saramin",
        help="수집 대상 소스",
    )
    parser.add_argument(
        "--query",
        default="python",
        help="검색 키워드",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="수집할 페이지 수 (1페이지 ≈ 20건)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="출력 파일 경로 (기본: data/raw/{source}_{날짜}.json)",
    )
    args = parser.parse_args()

    out_path = args.out or DATA_DIR / f"{args.source}_{datetime.now().strftime('%Y%m%d')}.json"

    collector = COLLECTORS[args.source]()
    logger.info("수집 시작 | source=%s | query=%s | pages=%d", args.source, args.query, args.pages)

    try:
        items = collector.collect(query=args.query, pages=args.pages)
    except NotImplementedError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    logger.info("수집 완료: %d건", len(items))

    merged = merge_and_save(items, out_path)
    print(f"\n결과: {len(merged)}건 저장 → {out_path}")


if __name__ == "__main__":
    main()
