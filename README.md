# StateInk

> **描いた設計を、動かして確かめる。**  
> 紙の状態遷移図を、実行・検証できる設計図へ。

## StateInkとは

StateInkは、紙や画面上の状態遷移図を操作可能な設計へ変え、設計上の問題とそこへ至る最短操作列を示すWebアプリです。画像認識をゴールにせず、**問題を見つける → 自分で直す → 警告が消える → 実際に動かす**体験を中心にしています。

Production: https://state-ink.vercel.app  
Recognition API: https://stateink.onrender.com

## 制作背景と問題

大学の授業で自動販売機の状態遷移図を書いた際、図は描けても「本当に正しく動くか」は紙の上で状態を一つずつ追う必要がありました。状態や矢印が増えるほど、到達不能、行き止まり、同じ操作の競合を人間だけで見つけるのは難しくなります。

## 解決方法・デモ

1. 図を写真から下書き化する、空から作る、またはサンプルを開く
2. イベントボタンで状態を動かす
3. Analyzerが問題を初心者向けの日本語で説明し、BFSで最短の再現操作を示す
4. 図を編集すると解析が即座に更新され、修正後の動作を再確認できる

本番デモでは「問題のある自動販売機」を開き、`coin → select → sold_out` で行き止まりを再現します。`売り切れ → 待機` の `refund` 遷移を追加すると警告が消え、Reset後に同じ操作と`refund`で待機へ戻れます。

## Architecture

```text
画像 → FastAPI / OpenCV / Tesseract(jpn+eng) → RecognitionResult → 人によるReview
                                                               ↓ Confirm
Samples / Editor ─────────────────────────────→ StateMachine IR
                                                  ├ Simulator
                                                  ├ Analyzer
                                                  └ Counterexample (BFS)
```

`src/core`はReact・XYFlow・OpenCVに依存しません。Simulatorは曖昧な遷移を実行せず、Analyzerは初期状態不備、到達不能、Dead End、孤立、Transition Conflictを検出します。Tarjan法で循環SCCを求め、正常終了状態が存在する場合だけ、そこへ到達できない循環をNon-terminating Cycleとして報告します。BFSは問題状態までの最短イベント列を生成します。詳しくは[architecture](docs/architecture.md)を参照してください。

## Recognition pipelineとHuman-in-the-loop

OpenCVの輪郭解析で円・楕円・長方形の状態候補、Hough線分とarrowhead候補から遷移候補を作ります。Tesseractの`jpn+eng` OCRが利用できる環境では、文字領域の位置から**状態内の文字をState名、矢印付近の文字をEvent名へ自動割り当て**します。複数トークンは読み順にまとめ、日本語間の不要な空白も正規化します。OCRできない場合は`State N` / `event_N`の仮名を残します。

認識結果は**自動完成ではなく下書き**です。confidenceを表示し、人が状態名、イベント、source、target、方向、initial/finalを確認してからIRへ確定します。特に矢印方向と密な図、手書き文字のOCRは誤認識し得るため、Reviewで修正できることを正式な設計にしています。

FA Database 1.1の24図による外部評価のSupported subset実測値は次のとおりです。これはOCR自動命名追加前に測定した**構造認識**の値で、OCR精度を示すものではありません。

| 指標 | 実測値 |
|---|---:|
| State detection | 94.9% |
| Transition detection | 95.2% |
| Connection | 50.0% |
| Direction | 29.4% |

評価条件・overall値・出典は[外部評価記録](docs/external-evaluation.md)に記載しています。

## 対応範囲・制限

- 対応: 白紙＋濃い線、円・楕円・長方形、明確な直線矢印、日本語・英語の状態名/イベント名のOCR下書き
- OCR: 印刷文字や読みやすい文字ほど安定。小さい文字、崩れた手書き、複数行、線との重なりは誤認識しやすい
- 構造認識の苦手: 曲線、self-loop、交差線、密な図、影、強い遠近歪み
- 認識した接続・方向・文字はReviewで確認する
- アカウント、共同編集、コード生成、完全UMLには対応しない

## AI利用

設計・実装・テスト・文書化にCodexおよびChatGPTを利用しました。外部Vision/LLM API、Cloud Vision、独自ML学習は使用していません。作業単位の記録は[AI_USAGE.md](AI_USAGE.md)にあります。

## 起動方法

Node.js 20+とPython 3.11+を想定しています。

```bash
npm install
npm run dev
```

画像読み取りを使う場合は別ターミナルで起動します。

```bash
python -m pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

OCRを利用する場合はTesseract本体と`eng` / `jpn` language dataを導入してください。Docker backendにはこれらを含めています。未導入でも構造候補と仮名を返します。

```bash
npm run check
PYTHONPATH=backend pytest backend/tests
npm run test:e2e
```

## Production deployment

FrontendはViteの静的build、Recognition backendはFastAPIの独立サービスとして公開します。API URLはFrontendの**build時**、CORS originはBackendの**起動時**に設定します。

| 変数 | 設定場所 | 例 | 説明 |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Frontend build | `https://stateink.onrender.com` | Backend originのみ。`/api`は付けない |
| `STATEINK_CORS_ORIGINS` | Backend runtime | `https://state-ink.vercel.app` | 許可するFrontend origin。複数はカンマ区切り |
| `PORT` | Backend runtime | `8000` | 待受port |

`.env`と`.env.*`はGit対象外です。`VITE_*`はブラウザへ埋め込まれる公開値なのでsecretを置きません。

```bash
# Backend
docker build -f Dockerfile.backend -t stateink-backend .
docker run --rm -p 8000:8000 \
  -e STATEINK_CORS_ORIGINS=https://state-ink.vercel.app \
  stateink-backend

# Frontend
VITE_API_BASE_URL=https://stateink.onrender.com npm run build
```

公開直前の確認とrollback手順は[Production deployment runbook](docs/deployment.md)を参照してください。
