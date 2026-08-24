# Architecture

## 境界

`samples → StateMachine IR → Simulator / Analyzer / Counterexample → UI` の一方向で依存します。`src/core` は React と XYFlow に依存しません。図の Node/Edge は `App.tsx` が IR から投影するため、将来画像認識が IR を生成しても core は変更不要です。

## StateMachine IR

`State` は id、name、position、initial、final、`Transition` は id、from、to、event を持ちます。Phase 1 に不要な guard や action は追加しません。position は入力された図の表示位置として IR に保持します。

## Simulator

現在状態、最後の遷移、状態とイベントの trace を不変データとして返します。同一状態・イベントの遷移が厳密に1つの場合だけ進みます。0件や conflict の場合は状態を変えないため、曖昧な実行結果を作りません。初期状態が0件または複数なら error を持つ実行不能状態を返し、暗黙に開始地点を選びません。図の編集後は常に新しい IR の開始状態へ reset し、削除済み状態を現在地として残さない予測可能な方針です。

## Analyzer

初期状態数、到達可能性、入出次数、`(source,event)` のグループ化で基本問題を検出します。循環解析は標準的な Tarjan 法（計算量 O(V+E)）で強連結成分を求めます。ただし、閉じたSCCだけを問題とはしません。final状態が1件以上ある機械に限り、到達可能な循環SCCからどのfinal状態へも到達できない場合を「正常終了へ進めないループ（Non-terminating Cycle）」として警告します。final状態のない自動販売機や信号機など、意図的に永続稼働する機械には循環警告を出しません。self-loopも同じ終了到達性で判定し、遷移のない単一状態はDead Endだけに任せます。UIは初期状態エラーをほかの派生問題より優先し、根本原因が分かる件数に整理します。

## Counterexample

初期状態から問題状態まで幅優先探索（BFS）します。辺を1イベントとして探索するため、最初に見つかった経路が最短操作列です。到達不能な問題には再現列を付けません。

## Editor とライブ更新

`src/core/editor.ts` の小さな immutable operation が StateMachine IR の追加・更新・削除を担います。状態削除時は接続遷移も同時に削除して dangling edge を防ぎます。UI は各編集操作の直後に新しい IR を state として保持するため、React の再描画で Analyzer と XYFlow が即時更新されます。サンプル専用の修正ロジックはありません。

## Recognition（Phase 2）

`画像 → FastAPI / OpenCV → RecognitionResult → Review → StateMachine IR` の一方向依存です。RecognitionResultは候補のgeometry、confidence、warningsを保持し、coreのIRとは分離します。OpenCVは適応的二値化、輪郭による円・楕円・長方形候補、確率的Hough変換による接続候補を生成します。Tesseractが利用可能なら短い英数字ラベルを補助的に読み、文字が読めなくても `State 1` / `event_1` の仮名で構造を返します。

認識結果を直接実行せず、必ずReviewで状態名、イベント名、接続方向、initial/final、不要候補を人が確認します。低confidenceを隠さず、shaft端付近のV字候補から推定した方向も確信度が低ければ要確認として提示します。Reviewではsource/targetの選択と「向きを反転」で修正できます。これはOCR精度より「構造を下書きにして人が直せること」を優先するHuman-in-the-loop方針です。Confirm後だけ `recognitionToStateMachine` がIRへ変換し、既存Editor、Simulator、Analyzerには認識ライブラリを依存させません。

## Deployment boundary

Frontendは静的artifact、Recognition backendは独立したFastAPI serviceとしてdeployします。Frontendはbuild時の`VITE_API_BASE_URL`をRecognition requestのoriginに使い、未指定ならlocal proxyや同一origin向けの相対`/api`を使います。Backendはruntimeの`STATEINK_CORS_ORIGINS`だけを許可します。`VITE_*`は公開bundleへ含まれるためsecretを置きません。API URLの切替はこのtransport boundaryだけに限定し、StateMachine IRとcoreには環境依存を持ち込みません。
