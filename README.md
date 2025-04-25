# scan-scheduler プロジェクト

このプロジェクトは、複数のセキュリティツールをスケジュール実行するためのWebアプリケーションです。ユーザーは、さまざまなツールを使用してドメインやターゲットの情報を収集し、結果を表示することができます。

## 構成

プロジェクトは以下のコンポーネントで構成されています。

- **backend/**: Flaskを使用したバックエンドAPI。ドメイン情報の収集を行います。
- **frontend/**: ユーザーインターフェースを提供するフロントエンドアプリケーション。Bootstrapを使用してスタイリングされています。
- **nuclei-api/**: Nucleiツールを使用して、ターゲットのスキャンを行うAPI。
- **pd-api/**: Project Discoveryのツールを使用して、さまざまなセキュリティスキャンを実行するAPI。

```
/
├── backend/
│   ├── app.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── recon_runner.py
├── frontend/
│   ├── app.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── templates/
│       ├── index.html
│       ├── results.html
│       └── schedules.html
├── nuclei-api/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── pd-api/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
└── docker-compose.yml
```

## セットアップ

1. リポジトリをクローンします。

   ```bash
   git clone <repository-url>
   cd asmmm-02
   ```

2. DockerとDocker Composeをインストールします。

3. プロジェクトをビルドして起動します。

   ```bash
   docker-compose up --build
   ```

4. ブラウザで`http://localhost:3333`にアクセスして、アプリケーションを使用します。

## 使用方法

- **フロントエンド**: スキャン結果を表示し、フィルタリングやページネーションを行うことができます。

- **バックエンドAPI**: `/amass`, `/recon`, `/nmap`などのエンドポイントを使用して、情報収集を行います。

### スケジュール実行

フロントエンドでは、スケジュール管理機能を提供しています。ユーザーは、特定の時間にスキャンを実行するためのスケジュールを設定できます。スケジュールは、バックエンドAPIを通じて管理され、ユーザーが指定した時間に自動的にスキャンが実行されます。

### 結果表示

スキャンが完了すると、結果はフロントエンドの結果一覧ページに表示されます。ユーザーは、フィルタリングオプションを使用して、特定のツールやターゲットに基づいて結果を絞り込むことができます。また、各結果をクリックすることで、詳細な情報をモーダルウィンドウで表示することができます。
