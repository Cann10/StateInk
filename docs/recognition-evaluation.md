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

苦手なケースは、交差・曲線・戻り矢印、線が状態枠と重なる図、複数行ラベル、影や罫線のある紙、強い遠近歪み、右から左または下から上の矢印です。これらはconfidenceとwarningを表示し、人がReviewで修正します。

合成fixtureとは別に、FA Databaseの手描きInkML 24図を用いた外部評価を実施しました。結果と改善前後の判断は[外部評価レポート](external-evaluation.md)を参照してください。
