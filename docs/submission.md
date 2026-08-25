# ProtoPedia掲載用 作品説明

## 作品概要

**StateInk — 描いた設計を、動かして確かめる。**

紙や画面上の状態遷移図を、操作して実行できる設計へ変換し、設計上の問題と最短の再現操作を示すWebアプリです。紙の写真から編集可能な下書きを作ることも、ブラウザ上で最初から作図することもできます。

## 制作背景

大学の授業で自動販売機の状態遷移図を描いたとき、「図として描けた」ことと「正しく動く」ことは別だと感じました。状態が増えるほど、紙を見ながら頭の中で遷移を追う確認は難しくなります。この体験から、描いた設計自体をその場で動かせるStateInkを制作しました。

## 解決する課題

- 初学者が状態遷移図の動きを頭の中だけで追う負担
- 到達不能、行き止まり、同じイベントの競合などを見落とす問題
- 問題が示されても、そこへ至る操作が分からず再現できない問題
- 紙の図を検証可能なデータへ移す手間

## 特徴

1. イベントボタンで図を実行し、現在状態とTraceを確認できる
2. 設計ミスを初心者向けの日本語で自動チェックする
3. 問題までの最短イベント列を表示する
4. 図の修正直後に警告とSimulatorへ反映する
5. 写真から状態と遷移の**下書き**を作り、人が確認してから実行する
6. 写真内の日本語・英語をOCRし、State名・Event名の候補へ自動割り当てする

## 技術構成

- Frontend: React、TypeScript strict、Vite、XYFlow、Tailwind CSS
- Domain core: StateMachine IR、Simulator、Analyzer、Counterexample Generator
- Recognition backend: Python、FastAPI、OpenCV、Tesseract (`jpn+eng`)
- Testing: Vitest、pytest、Playwright
- Algorithms: 最短反例のBFS、強連結成分のTarjan法、輪郭解析、Hough線分、arrowhead候補解析、OCR文字領域と図形の空間対応付け

UIやXYFlowの型をdomain coreへ持ち込まず、`Recognition → Review → StateMachine IR → Simulator / Analyzer`の一方向依存にしています。

## 工夫した点

- 技術用語より「この状態に入ると、どこにも移動できません」のような日本語説明を主表示にした
- Analyzerが問題を見つけるだけでなく、BFSで最短の再現操作を示す
- 編集のたびに解析を自動更新し、「見つける → 直す → 警告が消える → 動かす」を一画面で完結させた
- 初期状態不備やTransition ConflictではSimulatorが勝手な経路を選ばない
- finalのない自動販売機や信号機の正常な永久ループを誤警告しない終了到達性の定義を採用した
- OCRは状態枠内の文字をState名、矢印付近の文字をEvent名として位置関係から割り当てる
- OCRできない場合も`State N` / `event_N`を残し、構造認識を文字認識の成功に依存させない

## Human-in-the-loop採用理由

画像認識だけで完成させる品質を目指すと、誤った接続・方向・文字を確定したまま実行する危険があります。StateInkは認識を「自動完成」ではなく「下書き生成」と位置づけ、confidenceを隠さず表示します。人が状態名、event、source、target、方向、initial/finalをReviewし、必要なら「向きを反転」してからIRへ確定します。

Tesseractの`jpn+eng`で日本語・英語の自動命名を試みますが、手書き・小さい文字・複数行・線と重なる文字では誤認識し得ます。文字を読めない場合も仮名で構造を残し、人が修正できます。

## 外部評価結果

FA Database 1.1の手描き有限オートマトン24図を用いて構造認識を評価しました。Supported subsetの実測値は次のとおりです。

| 指標 | 実測値 |
| --- | ---: |
| State detection | 94.9% |
| Transition detection | 95.2% |
| Connection | 50.0% |
| Direction | 29.4% |

ConnectionとDirectionは自動完成品質ではありません。この結果を隠さず、Human-in-the-loopを正式な製品設計として採用しました。この外部評価はOCR自動命名追加前の構造認識評価であり、OCR精度を示す数値ではありません。OCRについては十分な外部benchmarkがないため、成功率を数値として主張しません。

raw datasetはリポジトリへ含めず、評価条件、Overall値、失敗分類は`docs/external-evaluation.md`へ記録しています。

## 制限事項

- Recognitionの主対象は白紙＋濃い線、円・楕円・長方形、明確な直線矢印
- 日本語・英語OCRは下書き生成として対応するが、崩れた手書き、小さい文字、複数行、線との重なりは苦手
- 曲線、self-loop、交差線、密な図、影、強い遠近歪みは構造認識が難しい
- 認識した接続・方向・文字はReviewでの確認が必要
- アカウント、共同編集、コード生成、完全UMLには非対応

## 公開先

- Webアプリ: https://state-ink.vercel.app
- Source: https://github.com/Cann10/StateInk

## AI利用

設計レビュー、実装、テスト、ドキュメント整備にOpenAI CodexおよびChatGPTを利用しました。外部のVision/LLM API、Cloud Vision、独自ML学習は利用していません。作業内容は`AI_USAGE.md`へ時系列で記録しています。
