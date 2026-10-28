# RGBA Composer for Stable Diffusion WebUI Forge Neo

複数画像を左上揃えでsource-over合成し、透明度を保持したPNGを作成するローカル拡張です。

## インストール

Stable Diffusion WebUI Forge Neo の `Extensions` → `Install from URL` で、以下の URL を指定してインストールし、WebUI を再起動してください。

```text
https://github.com/nodchip/sd-webui-rgba-composer.git
```

起動後、`RGBA Composer` タブから画像を追加できます。Python や画像処理ライブラリは Forge Neo の環境を使用します。

## 互換性と転送

Forge Neo のローカル環境で動作確認しています。他の WebUI や最新の Forge Neo のすべてのバージョンでの動作は確認していません。転送ボタンは各画面の UI 構造に依存するため、WebUI や拡張の更新で利用できなくなる場合があります。外部画像の追加と PNG の保存は、Inpaint Anything がなくても利用できます。

Cleaner からの転送ボタンは、[Inpaint Anything の Forge Neo 対応 fork](https://github.com/nodchip/sd-webui-inpaint-anything) にある Cleaner の Extras 転送ボタンを目印に表示します。Composer から Inpaint Anything への転送には、Inpaint Anything のインストールが必要です。

## 初版の機能

- 外部画像ファイルの複数追加
- img2img、Extras Single Image、Inpaint Anything Cleaner出力からのレイヤー追加
- サムネイル、レイヤー名、入力元、画像サイズ、不透明度の表示
- ドラッグ、ボタン、`Alt+↑`／`Alt+↓`による重ね順変更
- 表示切り替え、不透明度変更、名前変更
- 個別削除、5秒間の削除取り消し、全削除
- 全レイヤーを収容する透明キャンバスの自動計算
- RGBA PNGのダウンロード
- img2img、Extras Single Image、Inpaint Anythingへの出力転送

初版ではレイヤーごとの位置指定を行いません。すべての画像を左上 `(0, 0)` に揃えます。
Inpaint AnythingはRGB入力のため、転送時だけ指定した背景色（初期値は黒）へ合成します。RGBA Composerの出力自体は変更されません。

## License

[AGPL-3.0](LICENSE)
