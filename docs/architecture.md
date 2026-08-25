# Architecture

## 境界

`samples → StateMachine IR → Simulator / Analyzer / Counterexample → UI` の一方向で依存します。`src/core` は React と XYFlow に依存しません。図の Node/Edge は `App.tsx` が IR から投影するため、画像認識が IR を生成しても core は変更不要です。

## StateMachine IR

`State` は id、name、position、initial、final、`Transition` は id、from、to、event を持ちます。position は入力された図の表示位置として IR に保持します。

## Simulator

現在状態、最後の遷移、状態とイベントの trace を不変データとして返します。同一状態・イベントの遷移が厳密に1つの場合だけ進みます。0件や conflict の場合は状態を変えないため、曖昧な実行結果を作りません。初期状態が0件または複数なら error を持つ実行不能状態を返し、暗黙に開始地点を選びません。図の編集後は常に新しい IR の開始状態へ reset します。

## Analyzer

初期状態数、到達可能性、入出次数、`(source,event)` のグループ化で基本問題を検出します。循環解析は標準的な Tarjan 法（計算量 O(V+E)）で強連結成分を求めます。final状態が1件以上ある機械に限り、到達可能な循環SCCからどのfinal状態へも到達できない場合を「正常終了へ進めないループ（Non-terminating Cycle）」として警告します。final状態のない自動販売機や信号機など、意図的に永続稼働する機械には循環警告を出しません。

## Counterexample

初期状態から問題状態まで幅優先探索（BFS）します。辺を1イベントとして探索するため、最初に見つかった経路が最短操作列です。到達不能な問題には再現列を付けません。

## Editor とライブ更新

`src/core/editor.ts` の immutable operation が StateMachine IR の追加・更新・削除を担います。状態削除時は接続遷移も同時に削除して dangling edge を防ぎます。UI は各編集操作の直後に新しい IR を保持するため、Analyzer と XYFlow が即時更新されます。

## Recognition

`画像 → FastAPI / OpenCV / Tesseract → RecognitionResult → Review → StateMachine IR` の一方向依存です。RecognitionResultは候補のgeometry、confidence、warningsを保持し、coreのIRとは分離します。

OpenCVは適応的二値化、輪郭による円・楕円・長方形候補、確率的Hough変換による接続候補を生成します。矢印方向はshaft端付近のV字短線からarrowhead候補を推定します。

### OCR自動命名

Tesseractが利用可能な場合、利用可能言語を確認し、`jpn+eng`を優先します。片方しかない場合は`jpn`または`eng`へfallbackします。

状態名は検出済みState boxの内部をcropしてOCRし、文字列をそのStateへ直接割り当てます。Event名はState領域と長いshaftをOCR用コピーから除去したうえで矢印周辺をOCRし、近い文字列をTransitionへ割り当てます。複数tokenは視覚上の行・x座標順に結合し、日本語文字間の不要な空白や句読点前の空白を正規化します。

OCRが利用できない、または文字を得られない場合は従来どおり`State 1` / `event_1`などの仮名を保持します。つまり構造認識をOCR成否に依存させません。

### Human-in-the-loop

認識結果を直接実行せず、必ずReviewで状態名、イベント名、接続方向、initial/final、不要候補を人が確認します。低confidenceを隠さず、Reviewではsource/targetの選択と「向きを反転」で修正できます。

OCR自動命名も自動確定ではなく下書きです。小さい文字、崩れた手書き、複数行、線と重なる文字では誤認識し得ます。構造のConnection/Directionも外部評価で完全ではないため、StateInkは「認識精度を装う」のではなく「編集可能な下書きから検証へ進める」方針を採用します。

Confirm後だけ `recognitionToStateMachine` がIRへ変換し、既存Editor、Simulator、Analyzerには認識ライブラリを依存させません。

## Deployment boundary

Frontendは静的artifact、Recognition backendは独立したFastAPI serviceとしてdeployします。Frontendはbuild時の`VITE_API_BASE_URL`をRecognition requestのoriginに使います。Backendはruntimeの`STATEINK_CORS_ORIGINS`だけを許可します。

Backend Docker imageにはTesseract本体と`eng` / `jpn` language dataを含め、productionでも日本語・英語OCRを利用できるようにします。`VITE_*`は公開bundleへ含まれるためsecretを置きません。API URLの切替はtransport boundaryだけに限定し、StateMachine IRとcoreには環境依存を持ち込みません。
