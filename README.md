# tamami-remote-client

マイクから音声を取得してOpusでWebRTCに載せて送信するクライアント

# セットアップ

## uvのインストール

すでにuvが入っている場合は飛ばして下さい。

uvは以下のコマンドでインストールできます。

```bash
$ curl -LsSf https://astral.sh/uv/install.sh | sh
```

macOSではHomebrewでもインストールできます。

```bash
$ brew install uv
```

## プロジェクトのセットアップ

gitリポジトリのクローン。

```bash
$ git clone git@github.com:stc-zao-developer/python-project-base.git
```

プロジェクトディレクトリに移動して、uvで依存関係をインストール
（dev依存を含めて `.venv` に同期されます）。

```bash
$ cd tamami-remote-client
$ uv sync
```

pre-commitのセットアップ

```bash
$ uv run pre-commit install
```

pre-commitをセットアップすることにより、gitのcommit時に自動でコードの静的解析が実行されるように
なり、静的解析で検出された問題はコミットできなくなります。
これにより、コードの品質を保つことができます。

# 開発

ソースコードはsrcディレクトリ以下に配置されます。

```bash
$ uv run python src/main.py --waveform
```

を実行することにより、main.pyが実行されます。

tamamiサーバーへマイク音声をストリーミング送信する場合は `--connect` を指定します。

```bash
$ uv run python src/main.py --connect ws://localhost:8765/ws
```

## テストの実行

テストはtestsディレクトリ以下に配置されます。
pytestを使って実行します。

```bash
$ uv run pytest -s
```

また、
```bash
$ uv run ptw --config pytest.ini --runner 'pytest --testmon -s'
```

を実行することにより、コードの変更を監視し、変更があった場合に自動でテストを実行します。
とてもおすすめです。

## コードのフォーマット

コードのテストは、pre-commitで自動的に行われまが、手動で実行することもできます。

```bash
$ uv run pre-commit run --all-files
```

pre-commitや、checkコマンドで指摘された問題を自動で修正するには

```bash
$ uv run ruff check . --fix && uv run black .
```

を実行します。
