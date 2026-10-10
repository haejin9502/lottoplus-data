# LottoPlus Data Feed

로또플러스 Android 앱에서 사용하는 로또 6/45 공식 회차 데이터 피드입니다.

## 공개 파일

- `public/manifest.json`: 최신 회차와 파일 무결성 정보
- `public/snapshot.json.gz`: 신규 설치용 전체 압축 스냅샷
- `public/years/{year}.json`: 기존 설치의 증분 동기화용 연도별 데이터

앱은 GitHub API가 아니라 GitHub Pages의 정적 HTTPS 파일을 읽습니다.

## 자동 갱신

GitHub Actions가 매주 토요일 추첨 이후 동행복권 회차 API를 확인합니다. 새 회차가 있으면 원본 데이터와 Pages 배포 파일을 다시 만들고 검증한 뒤 자동 배포합니다. 필요할 때 Actions 화면에서 수동 실행할 수도 있습니다.

## 로컬 실행

```powershell
python .\scripts\update_latest.py
python .\scripts\build_feed.py
```

## 주의

과거 당첨 이력은 다음 회차의 당첨 결과를 예측하거나 보장하지 않습니다.

