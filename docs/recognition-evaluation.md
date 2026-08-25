# Recognition fixture evaluation

## 2026-08-23 構造認識baseline

`PYTHONPATH=backend python backend/evaluate.py` を実行した結果です。800×500pxの決定的な合成fixture 5枚を使用し、fixture名による分岐はありません。

| 項目 | 実測 |
| --- | ---: |
| State detection | 13 / 13 (100%) |
| Transition detection | 8 / 8 (100%) |
| Transition connection | 8 / 8 (100%) |
| Direction | 8 / 8 (100%) |
| State label | 0 / 13 (0%) |
| Event label | 0 / 8 (0%) |
| 処理時間 | 平均 23.16ms / 最大 40.62ms |

この測定時の環境にはTesseract実行ファイルがなく、文字は`State N` / `event_N`の仮名になりました。したがって上記のlabel 0%は**2026-08-23時点の環境結果**であり、現在のOCR自動命名機能の精度を示しません。

方向100%もfixtureが左から右へ明瞭に描かれた対応範囲内の値であり、一般画像への精度を意味しません。

## 2026-08-25 OCR自動命名追加

RecognitionへTesseractの日本語・英語OCRを追加しました。production Dockerには`tesseract-ocr`、`tesseract-ocr-eng`、`tesseract-ocr-jpn`を導入し、`jpn+eng`を優先します。

現在の処理は次のとおりです。

- State box内部の文字 → State名候補
- 矢印付近の文字 → Event名候補
- 複数token → 視覚上の読み順で結合
- 日本語文字間の不要な空白を正規化
- OCRできない場合 → `State N` / `event_N` fallback
- すべてReviewで編集可能

日本語・英語の文字列正規化と複数token結合はbackend testで固定しています。一方、実写真・手書き文字に対するOCR精度を示す十分な外部benchmarkはまだ実施していないため、**OCRの成功率を数値として主張しません**。

## 苦手なケース

構造認識では交差・曲線・self-loop、線が状態枠と重なる図、影や罫線、強い遠近歪み、右から左または下から上の矢印が難しいです。

OCRでは小さい文字、崩れた手書き、複数行、矢印や枠線と重なる文字が誤認識しやすいため、confidenceとReviewによる修正を前提とします。

合成fixtureとは別に、FA Databaseの手描きInkML 24図を用いた外部評価を実施しています。これは主に構造認識評価であり、結果と改善前後の判断は[外部評価レポート](external-evaluation.md)を参照してください。
