# FA Database external evaluation — final recognition cycle

## Protocol

External data: [FA Database 1.1, Czech Technical University](https://cmp.felk.cvut.cz/~breslmar/finite_automata/)（Bresler et al., ICFHR 2014）。24図のInkMLを一時PNGへ描画し、同じ図で改善前後を測定しました。raw ZIP、InkML、PNGと24枚のdebug overlayは `/tmp/stateink-fa` のみに置き、Gitには含めていません。`backend/external_evaluate.py` は各図とaggregateを表示し、`--debug-dir` 指定時だけ状態、shaft、arrowhead、予測source/target、正解source/targetを重ねた画像を一時出力します。

Overallは24図の全annotationを含みます。Supported subsetは、7状態以上の高密度図、交差が4箇所を超える図を図単位で除外し、self-loopとshaftの経路長/直線距離が1.35を超える曲線を遷移単位で分離します。結果は22図、98状態、126遷移です。除外は数値を良くする目的ではなく、Phase 2で明示した直線的で明確な矢印というgrammarとの境界です。両方の数値を常に併記します。

## Before

| Scope | State | Transition detection | Connection | Direction |
| --- | ---: | ---: | ---: | ---: |
| Overall | 113/118 (95.8%) | 190/203 (93.6%) | 65/177 (36.7%) | 58/203 (28.6%) |
| Supported | 93/98 (94.9%) | 119/126 (94.4%) | 46/104 (44.2%) | 40/126 (31.7%) |

## Final algorithm changes

1. Hough線分をangle差10度未満、直線間距離12px未満、端点gap 45px未満でgroup化し、射影上の両端をmerged shaftとしました。元線分も候補に残し、不適切なmergeで既存検出を失わないようにしています。
2. shaft端点24px以内で、shaftと20〜70度をなす短線を調べます。端点の両側にwingがあるV字だけをarrowheadとし、その端をtargetにします。片側しかない、または両端が同程度ならページ方向で補完せず、入力線分順の候補をconfidence 0.42でReviewへ渡します。検出できた場合も手描き評価を踏まえてconfidence 0.68とします。

## After

| Scope | State | Transition detection | Connection | Direction |
| --- | ---: | ---: | ---: | ---: |
| Overall | 113/118 (95.8%) | 192/203 (94.6%) | 73/177 (41.2%) | 54/203 (26.6%) |
| Supported | 93/98 (94.9%) | 120/126 (95.2%) | 52/104 (50.0%) | 37/126 (29.4%) |

Segment mergingでSupported connectionは+5.8pt、transition detectionは+0.8pt改善しました。一方、ページ方向という強い事前仮定を廃止した結果、現状のarrowhead検出だけではdirectionが-2.3ptとなりました。これは後退を隠さず、Human-in-the-loopで方向確認が必須であることを示す結果です。Transition detectionは正解数に対する検出候補数のrecall相当で、false positive precisionはfailure分類で別途確認します。

全24図の画像別結果と分類は [`fa-database-before.json`](evaluation/fa-database-before.json) と [`fa-database-after.json`](evaluation/fa-database-after.json) にあります。AfterのSupported failureはstate contour 5、line detection 52、arrowhead 22、source/target association 106、unsupported geometry 50でした。

## Freeze decision

State 90%とTransition detection 85%は満たしますが、Connection 75%とDirection 75%には届きません。指定された最終改善サイクルを終えたため、追加の大規模CV開発は停止しました。Recognitionは「状態構造の下書きを作る補助」として機能凍結し、接続と方向はReviewで必ず確認する前提です。Submission-ready polishも完了しており、この値を前提に提出資料とデモを構成します。
