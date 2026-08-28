# Recognition fixture evaluation

2026-08-23に `PYTHONPATH=backend python backend/evaluate.py` を実行した結果です。800×500pxの決定的な合成fixture 5枚を使用し、fixture名による分岐はありません。

| 項目 | 実測 |
| --- | ---: |
| State detection | 13 / 13 (100%) |
| Transition detection | 8 / 8 (100%) |
| Transition connection | 8 / 8 (100%) |
| Direction | 8 / 8 (100%) |
| State label | 0 / 13 (0%) |
| Event label | 0 / 8 (0%) |
| 処理時間 | 平均 23.16ms / 最大 40.62ms |

評価環境にはTesseract実行ファイルがないため、文字は意図どおり `State N` / `event_N` の仮名になりました。Tesseractが利用可能な環境では短い英数字OCRを試みますが、構造認識をOCR成否に依存させません。方向100%はfixtureが左から右へ明瞭に描かれた対応範囲内の値であり、一般画像への精度を意味しません。

## 2026-08-25 OCR自動命名追補

現在のbackendはTesseract `jpn+eng`を使用し、日本語・英語・混在文字をline単位で抽出します。State内／近傍の文字をState名へ優先的に関連付け、残りをTransition線分までの距離でEvent名へ関連付けます。複数語と短文は正規化して保持し、confidenceが55%未満なら自動命名せず仮名とReview警告を残します。

自動テストでは「待機」「入金済み」「商品選択」、「coin」「select」「refund」、`商品選択 select item`の関連付け、日英token結合、改行・余分な空白の正規化、State/Event双方の低confidence fallbackを固定しています。上表は2026-08-23時点の構造fixture評価として保持し、OCR raw正解率とは混在させません。

苦手なケースは、崩した手書き、小さい／薄い文字、縦書き、交差・曲線・戻り矢印、線が状態枠と重なる図、影や罫線のある紙、強い遠近歪み、右から左または下から上の矢印です。これらはconfidenceとwarningを表示し、人がReviewで修正します。

## 2026-08-28 Connection / Direction追補

同じ5枚の合成fixtureを再生成して評価し、State 13/13、Transition 8/8、Connection 8/8、Direction候補 8/8を維持しました。状態外周との距離、shaft角度、状態領域との重なりを接続スコアへ追加したことで、外周線の断片を遷移として数えるfalse positiveを除外しています。

Directionは正解率だけでなく誤確定を避ける評価へ変更しました。完全なV字arrowheadで自動確認した4件は4/4正解（precision 100%）、残る4件は候補方向を表示するだけで `direction_confirmed=false` とし、Reviewで明示確認するまで実行可能IRへ入りません。これは合成fixture上のcoverage 50%であり、一般画像の認識率を表す値ではありません。

合成fixtureとは別に、FA Databaseの手描きInkML 24図を用いた外部評価を実施しました。結果と改善前後の判断は[外部評価レポート](external-evaluation.md)を参照してください。

## 2026-08-28 実画像耐性・OCR追補

前処理へ紙面四隅による遠近補正、長線の合意角による傾き補正、影除去、CLAHE、bilateral filter、adaptive/Otsu二値化の選択を追加しました。認識は補正画像上で行い、StateとTransitionの座標を逆射影して元画像オーバーレイへ戻します。直線検出から漏れた曲線・途切れ線は、状態枠を除いたink componentが複数の状態外周へ接続する場合だけ、confidence 0.38のReview候補にします。

fixtureは従来5枚に、遠近・影・blur・noiseを含む写真風1枚と、曲線・影を含む1枚を追加しました。7枚の結果はState 17/17、Transition 10/10、Connection 10/10、Direction候補 10/10です。自動確定Directionは2/2正解（precision 100%）、Review送りは8/10（80%）です。処理時間は平均178.55ms、最大418.54msでした。前回5枚の自動確定4/4に対し今回は原5枚で2/2となり、画質評価を通らない候補を誤確定しない方向へcoverageを意図的に下げています。

OCRはNFKC正規化、zero-width/control文字除去、日本語文字間の不自然な空白除去を追加しました。global OCRで割り当たらない場合はState内およびTransition中央付近を`--psm 7`で再試行し、Transitionでは線分への距離だけでなく射影位置も評価します。実行環境にTesseract本体がないため、`jpn+eng`の実OCR正解率は未測定です。mockによる日本語・英語・混在文字、位置割当、低confidence fallbackはpytestで固定しています。
