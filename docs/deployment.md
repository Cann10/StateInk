# Production deployment runbook

StateInkはfeature freeze済みです。この文書は公開直前と公開後の確認だけを扱います。

## 確定した構成

- Frontend: `Dockerfile.frontend`でViteをbuildし、nginxのport 8080から静的配信する。
- Backend: `Dockerfile.backend`でFastAPIをUvicornから配信する。platformが渡す`PORT`を使用する。
- FrontendとBackendは別serviceとして公開し、両方にHTTPSを設定する。
- Recognition request先はFrontend build時の`VITE_API_BASE_URL`へ固定する。
- Backendはruntimeの`STATEINK_CORS_ORIGINS`に列挙したFrontend originだけを許可する。

## Production環境変数

| Service | 変数 | 必須条件 | 値 |
| --- | --- | --- | --- |
| Frontend build | `VITE_API_BASE_URL` | FrontendとBackendが別originの場合は必須 | BackendのHTTPS origin。例: `https://api.stateink.example`。通常は`/api`を付けない |
| Backend runtime | `STATEINK_CORS_ORIGINS` | productionでは必須 | FrontendのHTTPS origin。複数はカンマ区切り。pathと末尾`/`は付けない |
| Backend runtime | `PORT` | hosting platformが指定する場合 | platform指定値。未指定時は`8000` |

`VITE_*`は公開JavaScriptへ埋め込まれるためsecretを設定しません。StateInkにAPI keyなどのsecretはありません。`.env`ファイルをcommitせず、hosting platformのenvironment設定を使います。

## Deploy前チェック

- [ ] Git remoteが正しい提出用repositoryを指している。
- [ ] deploy対象branchにupstreamがあり、local HEADとremote HEADが一致している。
- [ ] working treeがcleanである。
- [ ] `npm run check`が成功する。
- [ ] `PYTHONPATH=backend pytest backend/tests`が成功する。
- [ ] `npm run test:e2e`が成功する。
- [ ] Frontend buildへproductionの`VITE_API_BASE_URL`を渡した。
- [ ] Backendへproductionの`STATEINK_CORS_ORIGINS`を渡した。
- [ ] FrontendとBackendのHTTPS certificateが有効である。

## Deploy commands

`APP_ORIGIN`と`API_ORIGIN`は実際のHTTPS originへ置き換えます。

```bash
export APP_ORIGIN=https://app.stateink.example
export API_ORIGIN=https://api.stateink.example

docker build -f Dockerfile.backend -t stateink-backend:release .
docker build -f Dockerfile.frontend \
  --build-arg VITE_API_BASE_URL="$API_ORIGIN" \
  -t stateink-frontend:release .

docker run --rm -p 8000:8000 \
  -e STATEINK_CORS_ORIGINS="$APP_ORIGIN" \
  stateink-backend:release
docker run --rm -p 8080:8080 stateink-frontend:release
```

実際の公開では、buildしたimageをregistryへpushし、hosting platformの2 serviceへ同じrelease tagを指定します。

## Post-deploy smoke test

### HTTP / security

- [ ] `curl -fsS "$APP_ORIGIN/health"`が`ok`を返す。
- [ ] `curl -fsS "$API_ORIGIN/api/health"`が`{"status":"ok"}`を返す。
- [ ] 次のpreflightが成功し、`access-control-allow-origin`が`$APP_ORIGIN`と完全一致する。

  ```bash
  curl -i -X OPTIONS "$API_ORIGIN/api/recognize" \
    -H "Origin: $APP_ORIGIN" \
    -H "Access-Control-Request-Method: POST"
  ```

- [ ] `$APP_ORIGIN`と`$API_ORIGIN`がどちらも`https://`で始まる。
- [ ] Browser DevToolsのSecurity/Consoleにmixed-contentまたはCORS errorがない。

### Critical user flow

- [ ] Homeにメインコピーと「紙から読み取る / 自分で図を作る / サンプルを試す」が表示される。
- [ ] 「サンプルを試す」で問題版自動販売機が表示される。
- [ ] Dead Endの説明と`coin → select → sold_out`の再現操作が表示される。
- [ ] `coin`、`select`、`sold_out`を押すと現在状態が「売り切れ」になる。
- [ ] `売り切れ → 待機`、event `refund`を追加すると警告が即座に消える。
- [ ] Reset後、`coin → select → sold_out → refund`で「待機」へ戻る。
- [ ] 「紙から読み取る」で対応範囲内のPNG/JPEG/WebPをuploadできる。
- [ ] Reviewで低confidence、source、target、direction、eventを確認・修正できる。
- [ ] Confirm後にEditorへ移り、Simulatorで認識した遷移を実行できる。
- [ ] 上記操作中、Browser Consoleにerrorがない。

## Rollback

smoke testの必須項目が1つでも失敗した場合は公開を継続せず、FrontendとBackendを直前の同一release tagへ戻します。特にFrontendとBackendで異なる環境の組み合わせを残さないよう、2 serviceをセットでrollbackします。
