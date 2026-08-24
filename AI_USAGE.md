# AI Usage Log

## 2026-08-23 — Codex

Codex が空に近いリポジトリ（README のみ）を調査し、Phase 1 の React/TypeScript/Vite/Tailwind/XYFlow 構成、StateMachine IR、Simulator、Analyzer、BFS による最短反例、Tarjan 法による Trap SCC、サンプル、UI、単体テスト、ドキュメントを実装しました。また lint、test、typecheck、production build と画面確認を実行し、発見した問題を修正しました。

アルゴリズムと設計の採否、および生成コードは提出者が理解・レビューして説明できる状態にしてください。利用した外部生成 AI API や画像生成はありません。

## 2026-08-23 — Codex（編集フェーズ）

Codex が Phase 1 の semantic audit を行い、final、Dead End と Trap SCC、到達不能な反例、初期状態不備、遷移競合の意味をテストで固定しました。StateMachine IR を immutable に編集する core operation、XYFlow 上の状態選択・移動・編集、遷移フォーム、ライブ解析、編集時の Simulator reset、初心者向けの問題整理を実装しました。問題版へ refund を追加し、警告消失と一連の実行を確認する Playwright E2E テストおよび画面キャプチャも作成しました。

## 2026-08-23 — Codex（循環解析の修正）

Codex が循環SCCの意味を再監査し、genericなclosed SCCを問題扱いする判定を廃止しました。Tarjan法は維持しつつ、final状態が存在する場合に限って、到達可能な循環SCCからfinalへ到達できないものをNon-terminating Cycleとして報告するようAnalyzer、初心者向け表示、ユニットテスト、設計文書を更新しました。OCRや新しいUI機能は追加していません。

## 2026-08-23 — Codex（Phase 2 Recognition）

CodexがFastAPI/OpenCVバックエンド、輪郭とHough線分による限定的な構造認識、confidenceとwarningsを含むRecognitionResult、5組の合成fixture画像とexpected JSON、backend testsを実装しました。フロントエンドには画像選択、低confidenceを明示するReview、候補修正、Confirm後のIR変換と既存Editor/Simulator/Analyzerへの接続を追加しました。認識APIを模擬したReviewからSimulatorまでのPlaywrightテストも追加しました。LLM Vision、Cloud Vision、独自ML学習は使用していません。

## 2026-08-23 — Codex（外部データ評価）

Codexが公開FA Database 1.1を一時領域へダウンロードし、InkML strokeとannotationを解析する外部evaluation harnessで24図のbaselineを測定しました。raw datasetはGitへ追加していません。最多だったline detectionとsource/target associationを調査し、線分延長上の状態関連付けと重複線分抑制の2点だけを汎用的に修正して同一データを再評価しました。connectionとdirectionが基準未達だったため、指示されたSubmission-ready polishには進んでいません。

## 2026-08-23 — Codex（Recognition最終改善）

Codexが同じFA Database 24図を使い、近接・同角度のHough線分mergeと、shaft端のV字短線によるarrowhead候補検出を実装しました。evaluation専用の一時overlay出力とOverall/Supported両集計を追加し、改善前後を再測定しました。Connectionは改善した一方Directionは低下した事実を記録し、閾値未達でも指示どおり追加CV開発を停止してHuman-in-the-loop前提の機能凍結を決定しました。raw dataとdebug画像はcommitしていません。

## 2026-08-23 — Codex（Submission-ready polish）

Codexが3択のHome、問題版サンプルへの短い導線、Recognitionを下書きと明示するReview、低confidenceの強調、遷移方向の反転、loading/error/empty stateを実装しました。問題発見からrefund追加、警告消失、再実行までのE2Eと、方向反転を含むRecognition E2Eを更新し、U-22提出向けREADMEへ外部評価の実測値とHuman-in-the-loop採用理由を記載しました。Recognitionアルゴリズムは変更していません。

## 2026-08-24 — Codex（提出準備監査）

CodexがREADME、Product、Architecture、Plan、外部評価文書の表現を照合し、サブコピー、Recognitionの方向推定説明、フェーズ状態の矛盾を修正しました。3分動画用の操作台本とProtoPedia掲載用作品説明を作成し、問題版自動販売機とRecognitionのE2Eでブラウザconsole errorも検査しました。新機能およびRecognitionアルゴリズムの変更は行っていません。

## 2026-08-24 — Codex（Deployment readiness）

Codexがfeature freezeを維持したまま、Frontendのproduction API URL、FastAPIの許可originを環境変数化し、Frontend/Backend用Dockerfile、nginx静的配信設定、非secretの環境変数例、production deploy手順を追加しました。CORS設定のテストと全validationを実行し、Recognitionおよびdomain機能は変更していません。

## 2026-08-24 — Codex（Pre-deploy review）

CodexがGit remote/upstream、Frontend/Backend container、nginx、環境変数、health endpointを静的監査しました。公開後にHome、自動販売機修正、Recognition Review、Simulator、health、CORS、HTTPS、consoleを確認するrunbookとrollback基準を作成しました。アプリ機能とRecognitionアルゴリズムは変更していません。
