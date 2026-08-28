# StateInk

> **描いた設計を、動かして確かめる。**<br>
> 紙の状態遷移図を、実行・検証できる設計図へ。

## StateInkとは

StateInkは、紙や画面上の状態遷移図を操作可能な設計へ変え、設計上の問題とそこへ至る最短操作列を示すWebアプリです。画像認識をゴールにせず、**問題を見つける → 自分で直す → 警告が消える → 実際に動かす**体験を中心にしています。

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
画像 → FastAPI / OpenCV → RecognitionResult → 人によるReview
                                              ↓ Confirm
Samples / Editor ────────────────→ StateMachine IR
                                      ├ Simulator
                                      ├ Analyzer
                                      └ Counterexample (BFS)
```

`src/core`はReact・XYFlow・OpenCVに依存しません。Simulatorは曖昧な遷移を実行せず、Analyzerは初期状態不備、到達不能、Dead End、孤立、Transition Conflictを検出します。Tarjan法で循環SCCを求め、正常終了状態が存在する場合だけ、そこへ到達できない循環をNon-terminating Cycleとして報告します。BFSは問題状態までの最短イベント列を生成します。詳しくは[architecture](docs/architecture.md)を参照してください。

## Recognition pipelineとHuman-in-the-loop

OpenCVの輪郭解析で円・楕円・長方形の状態候補、Hough線分とarrowhead候補から遷移候補を作ります。OCRはTesseractの`jpn+eng`で日本語・英語を読み、文字領域と図形の距離から、状態内／近傍の文字を状態名、矢印近傍の文字をイベント名へ割り当てます。複数語や短い文は空白を正規化して保持します。認識結果は**自動完成ではなく下書き**です。低confidenceの文字は自動命名せず、`State N` / `event_N`の仮名と警告を表示します。人がReviewで状態名、イベント、source、target、方向、initial/finalを確認・修正してからIRへ確定します。

この判断は弱点を隠すためではありません。FA Database 1.1の24図による外部評価のSupported subset実測値は次のとおりです。

| 指標 | 実測値 |
|---|---:|
| State detection | 94.9% |
| Transition detection | 95.2% |
| Connection | 50.0% |
| Direction | 29.4% |

自動認識だけで完成させる品質ではないため、StateInkでは認識結果を下書きとして扱い、人間が確認するHuman-in-the-loop方式を採用しました。評価条件・overall値・出典は[外部評価記録](docs/external-evaluation.md)に記載しています。

## 対応範囲・制限

- 対応: 白紙＋黒ペン、円・楕円・長方形、明確な直線矢印、日本語・英語・混在ラベル
- 苦手: 崩した手書き文字、小さい文字、薄い文字、曲線・self-loop・交差線・密な図・影や強い遠近歪み
- 保存、アカウント、共同編集、コード生成、完全UMLには対応しません

## AI利用

設計・実装・テスト・文書化にCodexを利用しました。外部Vision/LLM APIや独自ML学習は使用していません。作業単位の記録は[AI_USAGE.md](AI_USAGE.md)にあります。

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

Docker backendにはTesseractと日本語・英語language dataが含まれます。Dockerを使わず起動する場合は、Tesseract本体に加えて`jpn`と`eng`のtrained dataを導入してください。未導入でも仮名を持つ構造候補を返します。

```bash
npm run check
PYTHONPATH=backend pytest backend/tests
npm run test:e2e
```

## Production deployment

FrontendはViteの静的build、Recognition backendはFastAPIの独立サービスとして公開します。API URLはFrontendの**build時**、CORS originはBackendの**起動時**に設定します。`VITE_*`はブラウザへ埋め込まれる公開値なので、秘密情報を設定しないでください。

### 必須環境変数

| 変数 | 設定場所 | 例 | 説明 |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Frontend build | `https://api.example.com` | Render Backendのoriginのみ（通常は`/api`を付けない）。空なら同一originの`/api`を使用 |
| `STATEINK_CORS_ORIGINS` | Backend runtime | `https://app.example.com` | 許可するFrontend origin。複数はカンマ区切り |
| `PORT` | Backend runtime | `8000` | コンテナの待受port。未指定時は8000 |

値の形は[`.env.example`](.env.example)を参照してください。`.env`と`.env.*`はGit対象外です。productionではHTTPSのFrontend originだけを`STATEINK_CORS_ORIGINS`へ列挙し、`*`を使用しないでください。

### Dockerで公開する

```bash
# Backend
docker build -f Dockerfile.backend -t stateink-backend .
docker run --rm -p 8000:8000 \
  -e STATEINK_CORS_ORIGINS=https://app.example.com \
  stateink-backend
curl http://localhost:8000/api/health

# Frontend（API URLはbuild artifactへ埋め込まれる）
docker build -f Dockerfile.frontend \
  --build-arg VITE_API_BASE_URL=https://api.example.com \
  -t stateink-frontend .
docker run --rm -p 8080:8080 stateink-frontend
curl http://localhost:8080/health
```

Frontendはnginxで静的ファイルを配信し、SPA fallbackを設定しています。Dockerを使わない場合は`VITE_API_BASE_URL=https://api.example.com npm run build`で生成した`dist/`を任意の静的ホスティングへ配置してください。BackendはPython 3.11で依存を導入し、次のように起動できます。

```bash
STATEINK_CORS_ORIGINS=https://app.example.com \
PORT=8000 \
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

公開後はFrontend、`GET /api/health`、画像Reviewを同じproduction URLの組み合わせで確認してください。API URLを変更した場合、Frontendは再buildが必要です。

Vercelでは`VITE_API_BASE_URL`にRenderの公開origin（例: `https://stateink-api.onrender.com`）を設定します。`/api/recognize`はFrontendが付加します。値を変更した後はVercelを再deployしてください。HTMLや`The page could not be found`が返る場合は、`$VITE_API_BASE_URL/api/health`と`$VITE_API_BASE_URL/api/recognize`が同じRender serviceを指すか確認します。

公開直前のGit確認、確定環境変数、CORS確認、Critical user flow、rollback手順は[Production deployment runbook](docs/deployment.md)を使用してください。
