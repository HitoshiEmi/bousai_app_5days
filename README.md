# 防災アプリ

## 起動

```bash
pip install -r requirements.txt
python app.py
```

ブラウザで `http://localhost:5000/` を開きます。

## 環境変数

- `SECRET_KEY`: セッション署名用のランダムな秘密鍵。本番では必ず設定してください。
- `ADMIN_PASSWORD`: 職員ログイン用パスワード。本番では必ず設定してください。
- `SESSION_COOKIE_SECURE=true`: HTTPS 環境で Secure Cookie を有効にします。
- `PREFECTURE_CODE`, `AREA_CODE`, `AREA_NAME`: 気象庁連携の対象地域設定。

`ADMIN_PASSWORD` 未設定時は動作確認用に `123` を使用します。本番環境では設定しないでください。

## 外部 API

ホーム画面は Leaflet と OpenStreetMap タイルを利用します。気象情報はサーバー側から気象庁の警報・注意報 JSON を取得します。ネットワーク障害時は画面を壊さず取得失敗として表示します。
