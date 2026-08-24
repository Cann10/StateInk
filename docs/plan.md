# Delivery plan

## Phase 1 — Core（完了）

IR、純粋な Simulator、Analyzer、BFS 反例、Tarjan Trap SCC、正常/問題ありサンプル、1画面 UI、テストとドキュメントを完成させます。

## Phase 1.5 — Editable verification（完了）

状態と遷移の最小編集、ドラッグ配置、ライブ解析、編集時の Simulator reset、問題版を refund 遷移で直して実行する E2E デモを追加しました。OCRへ進む前に「見つける → 直す → 警告が消える → 動かす」の核を完成させます。

## Phase 2 — Recognition（完了・機能凍結）

白紙＋黒線の限定条件で、OpenCVによる状態形状・接続候補をRecognitionResultとして返し、人がReviewで修正してからIRへ確定するパイプラインを実装しました。OCRは仮名を置き換える補助と位置づけ、完全認識を目標にしません。

## Phase 3 — Polish / Evaluation / Submission（完了）

3択のHome、下書きであることを明示したRecognition Review、低confidenceと方向反転、問題版デモの短い導線、loading/error/empty state、提出向けREADMEを整備しました。RecognitionはHuman-in-the-loop前提で機能凍結します。残る工程は実ユーザーによる理解度・問題発見時間の評価と応募資料の最終確認です。
