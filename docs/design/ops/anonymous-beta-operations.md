# 匿名公開 β の運用

配備対象は監査・再公開後の **公開リポジトリの固定 tag / commit** だけとする。
この手順のドメイン・アドレス・アカウントはすべて placeholder。実値、パスワード、AWS の認証情報を追記しない。
本書のホスト操作・Docker・AWS・DNS・実ブラウザ確認はすべて **この機械では未実行**。
実施担当は β8 のレビュー側。公開、AWS 作成、DNS 変更は利用者の承認後に行う。

## 前提と構成（この機械では未実行）

- Lightsail 東京、Ubuntu 24.04 LTS、2 GB / $12 のプランを作成画面で再確認する。静的 IPv4 を割り当てる。
- 閉じた staging は 22 / 80 / 443 を運用者の IPv4 だけに許可する。公開時は 80 / 443 だけ全体に許可し、22 は自分の IP のまま。
  SSH は鍵認証、root ログイン禁止。Docker 公開ポートは UFW を迂回しうるので Lightsail のファイアウォールでも絞る。
- **Lightsail の IPv6 は無効にし、AAAA レコードを置かない**。IPv6 を使うなら、Docker の IPv6 routing を別途設計し、
  実接続元が Caddy に届くことを証明してから使う。gateway に変換された IPv6 を信用すると利用者ごとの制限が共通になる。
- AWS root / 運用アカウントに MFA。サーバーに AWS キーや GitHub token を置かない。公開 clone に認証は要らない。
- OS のセキュリティ更新、2 GiB swap、Docker の公式 apt / Compose plugin は installer が用意する。
  既存 Docker と競合するパッケージがあるサーバーでは先に公式手順で確認する。installer は既存パッケージを勝手に削除しない。
- `/opt/dem-beta` は運用者が管理する公開 clone、`.env` は root 所有 600。
  `/var/lib/dem-beta/{flags,status,state,backups}` はコンテナ UID/GID 10001、`host-state` と `logs` は root 700。
  API は flags / status を読取専用、contacts を書込可で mount し、管理資格情報・バックアップ・Webhook の秘密を持たない。
  contacts は UID/GID 10001・700。送信済みの sent はホストだけが扱う。
- DB / tools は internal の database、API は database と internal の proxy だけに接続し、外部へ通信できる network を持たない。
  web だけが公開用 frontend と proxy の両方に接続する。公開ポートは web の TCP 80 / 443 のみ。
  API が信用する転送元は web の proxy 側固定 IP `172.30.42.2` だけ。
  `172.30.42.0/24` が既存 network と衝突しないことを確認する。変更時は compose と API の信用する Caddy IP を一緒に変え、静的検査を通す。

## 初回配備（この機械では未実行）

installer は同じ tag の unit / シェルを読むため、**clone を先に行う**。installer → clone という順ではファイルが揃わない。
以下の `<...>` を承認済み公開 URL / tag に置き換える。private checkout を転送しない。

```bash
sudo apt-get update
sudo apt-get install -y git
sudo git clone --branch <approved-public-tag> --depth 1 <public-repository-url> /opt/dem-beta
cd /opt/dem-beta
sudo bash deploy/beta/install.sh
sudoedit deploy/beta/.env
```

installer は再実行可能。既存 `.env` のパスワードを生成し直さず、値も表示しない。
初回のみ `openssl rand -hex 32` で 3 資格情報を作り、完成したファイルを置く。
現在の commit、既定 `Mon 04:00 Asia/Tokyo`、noindex=1、既定 interface、月間 2,500,000,000,000 bytes も記録する。
パスワードは URL に入れるので **生成された hex を使用**し、手作業で記号を足さない。
`.env` を source するため、運用者以外に編集権限を与えない。`docker compose config` の出力には資格情報が出るので記録・共有しない。

閉じた staging の初期 HTTP 検査では `DEM_BETA_DOMAIN=http://beta.example.invalid` とし、手元の名前解決 / Host ヘッダを用いる。
これは ACME が閉じた firewall を通れない間の設定。公開時は実 FQDN（scheme 無し）に直し、自動 HTTPS を確認する。
`DEM_BETA_INTERFACE` が実際の外向き interface であることも確認する。
notify timerをstartする前に、本書の「問い合わせとSlack通知」でWebhookの設定と個人情報のないテスト通知を済ませる。

```bash
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml build
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml up -d --wait db
sudo dem-beta roles
sudo dem-beta build-base
# live がまだ無いので API は作成だけし、起動しない。
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml create api
sudo dem-beta reset
sudo dem-beta up
sudo dem-beta status
sudo systemctl start dem-beta-reset.timer dem-beta-backup.timer dem-beta-watch.timer dem-beta-notify.timer
sudo systemctl list-timers 'dem-beta-*'
```

`roles` は compose の管理ロールでのみ実行する。所有者と API ロールは別で、ともに非 superuser / 非 CREATEDB / 非 CREATEROLE /
非 replication / 非 BYPASSRLS。API は DML のみ、statement_timeout=10s、idle_in_transaction_session_timeout=30s。
base 作成時だけ所有者として migration → seed の全検証 → 全 release 公開 → 検査・権限 probe を行う。
API 起動は SELECT だけで接続・head revision・未完成式 0 を確認し、不一致なら起動しない。
base は接続不可に封印し、API は live だけに接続する。起動時 migration や seed は行わない。

Python の実行時依存は `deploy/beta/requirements.lock` の試験済み版を使い、DEM 自身も `--no-deps` で入れる。
更新時は先に `python deploy/beta/lock_requirements.py --prepare-only` で、Linux x86_64 / CPython 3.13.7 の固定 marker による閉包と不足を確認する。
全体の pip freeze ではなく、pyproject の基本 + webapi と psycopg[binary] からインストール済み metadata をたどる。
配備先だけの package の不足は、レビュー側が許可を得て manylinux x86_64 / cp313 の wheel を取得して補う。取得前に版や license を推測しない。
生成器で lock と requirements.target-metadata.json を同時に再生成し、回帰確認と一緒にコミットする。
後者には wheel から読んだ name / version / Requires-Dist / license と wheel 名 / sha256 を残し、CI でインストールされた metadata と照合する。
Windows では target-metadata による不足の補完を明示し、lock の名前集合と手元の版をすべて照合する。実物 wheel の確認を代用しない。
Linux の閉包には uvloop を含め、Windows 専用の colorama / tzdata は含めない。起動設定は `--loop asyncio`、lock インストールは `--no-deps` のまま。
カーネル版を参照する依存 marker は拒否する。実 image の Linux build / import・zoneinfo は staging で確認する。

## staging の確認表（全項目、この機械では未実行）

失敗項目があれば公開しない。負荷試験で RSS が 1.2 GiB を超えて張り付く、swap の出入りが続く、OOM が 1 回でも出る場合は
4 GB プランへの変更を検討する。件数・失敗数・時間・peak RSS・可能なら温度と limit flags を記録する。

| ID | 確認と合格条件 |
| --- | --- |
| S1 / 設計 §10-1 | 公開 tag から image build、Compose 起動。PG server/client は 18、db/API/tools に公開ポート無し、API は非所有者。 |
| S4 / §10-4 | 複数の実クライアントで匿名 CRUD と並行編集。片方の競合は 409、DB は整合し、基本 release は変更不能。 |
| S7 / §10-7 | Caddy 経由で 256 KiB 超、遅い body、rate / 同時実行 / DB 満杯 / freeze / 禁止 endpoint を確認。429 + Retry-After、409、422、503 の拒否を維持。 |
| S8 / §10-8 | prepare → API 停止 → swap → API 起動 → healthy → finish。prepare 失敗は API を止めず新規の停止印無し、API 停止以降の失敗は再起動試行と停止印を確認。reset-error.json と /config の last_reset_error、成功時の消去、backup / restore、不正 dump 拒否も確認。 |
| S9 / §10-9 | コンテナと OS を再起動し Docker の自動起動・restart policy・API の読取専用起動・timer の復帰を確認。healthcheck 失敗だけでは Docker が再起動しない点も確認。 |
| S10 / §10-10 | 主要画面、式・証明の入力、検証、依存表示、拒否メッセージをブラウザで操作。 |
| IP | 異なる IPv4 から Caddy JSON の remote_ip と API の制限が分離する。偽 X-Forwarded-For で逃げられない。IPv6 は無効、または実接続元を保つ Docker routing を実証。 |
| CSP | 開発者ツールで CSP と外部通信を確認。KaTeX_Size3 の data:woff2 は拒否されても同一 origin の woff / ttf に fallback し、大きい括弧等が正常表示される。script の inline / eval / 外部 origin を許可しない。 |
| INDEX | 既定で X-Robots-Tag: noindex と robots.txt Disallow: /。設定 0 では両方が解除され、SPA fallback に robots が吸われない。 |
| MAINT | API 停止による Caddy 自身の接続エラー（502/503）だけ日英メンテナンス頁（200 にしない）。API 自身の beta.maintenance / beta.full / health の 503 は JSON の本文・code をそのまま通す。/assets と index / SPA の圧縮、長期 / 非 cache、API の二重圧縮無しを確認。 |
| ROLE | 実 API 資格情報で current_user が所有者と異なり SELECT 成功。DISABLE TRIGGER、CREATE TABLE、DROP TRIGGER、ALTER TABLE ADD、TRUNCATE が **すべて 42501**。公開済み symbol UPDATE は published の **23514**。新規下書きの正当な DML は成功。両 timeout 設定も実接続で確認。probe 不合格なら base / next を採用しない。 |
| LOAD | β1 の上限付近の大規模 DB 計測を、固定 Python / PG と実際の 2 GB Compose で再実行。全体の重い処理 1 本、export 無効を保持し、時間・メモリ・応答と DB 件数/サイズを記録。手元の値を配備機の結果に代用しない。 |
| OPS | systemd-analyze calendar と status の next_reset_at が同じ。日次 backup は reset の 2 時間後、watch は 10 分。disk 85% freeze / 90% 名前限定 prune、tx 累積・月替わり・再起動・上限時 web 停止、日次ログ回転・30 日削除、日次スナップショットも確認。 |
| TZ | 承認 B で、最終の β API/tools image 内に `/usr/share/zoneinfo/Asia/Tokyo` があり、Python の `ZoneInfo("Asia/Tokyo")` と `scripts.beta_admin.next_reset` が動くことを確認する。ホスト Ubuntu は別に system の zoneinfo と `deploy/beta/host.py` の日付設定の検査を確認する。どちらかが欠ければ配備を止める。β6-fix7 の offline 点検では base image の実物と公式 Dockerfile が手元に無く、配備先での可用性は未確認。 |

Caddy の `validate` / `adapt`、image 内の pg_dump / pg_restore の版、Compose の補間、mount の UID/権限、
実際のリセット・再起動・CSP / noindex / メンテナンス応答は上表で実測する。静的 pytest の合格をこれらの代わりにしない。

## 公開（この機械では未実行）

利用者が β7/β8 の結果と費用を承認した後、DNS A を静的 IP に向ける。AAAA は作らない。
`.env` の DOMAIN を実 FQDN に変更して web を再作成し、80 / 443 を開く。
Caddy の ACME / HTTPS、証明書更新経路、セキュリティヘッダ、S7 / IP / CSP / INDEX / MAINT を実 URL で再確認して公開を告知する。
noindex は既定 1 を維持し、変更は明示判断する。AWS Budgets $20（実績80%・予測100%）、Cost Anomaly Detection、
Lightsail 状態通知・NetworkOut アラーム、日次スナップショット 7 世代を設定する。価格・枠は作成時に公式画面で再確認する。

## 日常の運用（この機械では未実行）

```bash
sudo dem-beta status
sudo dem-beta backup
sudo dem-beta reset
sudo journalctl -u dem-beta-watch.service -u dem-beta-reset.service --since today
```

既定 reset は月曜 04:00 JST、backup は毎日 06:00 JST。schedule を変更したら installer を再実行して timer を再生成し、
`systemd-analyze calendar` の次回と、次の正常 reset 後の status.json / API `/config` を照合する。
reset / backup / watch / status は同じホスト lock を取り、重なった実行は 75 で終了する（次の timer または手動で再実行）。
コンテナの起動は `docker.service` と `restart: unless-stopped` に任せるため専用 startup unit は無い。
意図して stop した web / API は reboot だけで勝手に公開再開しない。

backup は通常 7 世代、preswap は 1 世代。disk 90% の緊急 prune は名前が一致する通常ファイルだけを対象に、各種類の最新 1 本を残す。
symlink、ディレクトリ、別名の dump、partial は消さない。disk 85% 以降は freeze し、自動解除しない。
送信量は UTC 月ごとに外向き interface の tx_bytes を積算する。boot ID 変化、counter 減少、interface 変更時は現在値を追加する。
初回は boot 後の現在値を全加算、月をまたぐ観測間隔は新しい月に計上する。再起動直前の未観測分は取得できないので、
これは請求の正確なメーターではない。10 分間隔・2.5 TB の余裕に加え AWS 側の通知を併用する。
状態ファイル破損や counter 不明では freeze して web を止める。上限超過・月替わり後も web の自動再開はしない。

アクセスログは Caddy の JSON（接続元 IP を含む）、10 MiB のサイズ回転・720h 保持に加え、ホスト logrotate が日次回転 / 30 世代 / maxage 30。
watch は対応する回転済みログの通常ファイルを 30 日で削除する。稼働中ログは削除しない。ログには個人の接続元があるので root のみで扱う。
Docker ログは各サービス 10 MB × 5。月 1 回は Bills と Cost Explorer を見て、停止中の旧 EC2 の EBS / Elastic IP も確認する。

## 緊急時と復旧（この機械では未実行）

- 書き込み停止 / 解除: `sudo dem-beta freeze` / `sudo dem-beta unfreeze`。解除前に DB と API の healthy を確認する。
  問題投稿は個別にトリガを外して削除せず、検証済み base から reset する。
- 全公開停止: `/opt/dem-beta` で `sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml stop web`。
  転送上限の停止後も同じ。再開は原因・月間送信量を確認して利用者の判断で行う。
- reset prepare 失敗: live に触れていないので API の停止 / 起動をせず、道具が自分の印を片付けた状態を保つ。
  ホストは新しい停止印を置かない。以前から人が置いた freeze は勝手に解除しない。
  `status/reset-error.json` の failed_at / stage と `/config` の beta.last_reset_error で失敗を確認する。
  記録は UTC 時刻と固定の段階名だけで、成功した reset / restore で消える。破損ファイルは API が null として扱う。
- API の停止以降の reset / restore 失敗: シェルは API 起動を試し、既存の停止印の token を保ち、reset-error.json を記録する。
  restore 検査が自分の印を消した場合もホストが印を作る。
  再起動の成功だけを理由に解除しない。DB 名・目印・所有者、prepared.json の phase、status、API healthy を確認する。
  `swapped` / `failed_restored` で token が合うなら、確認後 `docker compose ... run --rm tools reset finish`。
  prepare 失敗だけなら unfreeze は不要。別の理由で既存 freeze があるときは、その理由を確認してから解除する。
  未処理 next / old を推測で削除しない。
- reset swap の入口で失敗し、phase が `prepared` のままの場合: まず失敗の原因を除く。
  **API を止める前に** `state/prepared.json` の phase が `prepared` であり、その token が `flags/read_only` の tools の停止印と一致することを確認する。
  一致を確認してから API を停止 → `docker compose ... run --rm tools reset swap` → API を起動し healthy を待つ →
  `docker compose ... run --rm tools reset finish` の順に復旧する。`reset-error.json` は次の正常な `dem-beta reset` で消す。
  未処理の next / old を推測で削除しない。この順序は閉じた staging で実際に確認した手順。
- DB 復元: `sudo dem-beta restore dem-beta-backup-<timestamp>-<id>.dump`。
  ファイルは `/var/lib/dem-beta/backups` に UID 10001 が読める状態で置く（引数は basename のみ）。
  **API を止めてから** tools restore が next を構築・検査・切替し、API 起動 → healthy → finish。
  復元は保存された現在の base digest と一致するものだけ。旧 base の dump や改ざんは拒否される。
  検査に通らなければトリガを緩めず、原因確認後に現在の base から reset する。
- サーバー喪失: 日次スナップショットから新規インスタンスを作り、static IP を付け替える。
  firewall・IPv6・timer・API / DB・counter の復帰を確認し、古いインスタンスが二重稼働しないようにする。

## 接続元 IP の緊急遮断（staging で確認するまで未確認）

大量の一斉送信で uvicorn の L=128 を瞬間的に超えると、他の利用者にも plain text の503が返る。この可用性の危険は受け入れる。
検証の結果を偽装したり、基本の内容・DBの整合のガードを迂回したりできるという意味ではない。
対応は以下の手動遮断と、必要に応じた `dem-beta freeze`、web の停止。Lightsail の firewall は許可ルールであり、特定sourceの拒否はホストで行う。
この手順は installer に常設せず、自動でIPを選んで遮断もしない。

root の対話端末で `/opt/dem-beta` に移動し、`python3 deploy/beta/access_log.py summary --minutes 5` を実行する。
`/var/lib/dem-beta/logs/access.log` の直近5分の remote_ip ごとの件数と状態コードだけを表示する。
ローテートをまたぐ場合は必要なファイルを `--log FILE` の繰返しで指定する（gzipにも対応）。同じファイルを重複指定しない。
URLやlog原文は出力しない。IPを含む出力を保存・転送・共有しない。道具はroot以外や端末でないstdoutへの出力を拒否し、ネットワーク送信しない。
件数だけで攻撃と決めず、時刻・状態コード・負荷と対応させて判断する。CGNATのIPには複数の正当な利用者が含まれ得る。

運用者のIPとLightsailブラウザSSHの経路を取り違えないこと。DOCKER-USERはforward用で通常のホストSSHのINPUTとは異なるが、他chainやSSHの規則を一緒に変更しない。
`ip route show default` と設定の DEM_BETA_INTERFACE を照合し、外向きinterfaceを確認する。
以下のIPは文書用の例なので、実際の対象のIPv4に置き換える。必ず1個の `/32` だけを扱い、hostname・CIDR・余計な文字は道具が拒否する。
`/32`以外への拡大はこの手順の範囲外。影響する利用者と復旧経路を別に確認し、安易に `/24` 等へ広げない。

```bash
# root の対話端末。実際の設定に合わせて入力する。
export DEM_BETA_INTERFACE=eth0
BLOCK_IP=198.51.100.23
python3 deploy/beta/access_log.py block-commands --ip "$BLOCK_IP" --interface "$DEM_BETA_INTERFACE"
iptables -n -L DOCKER-USER
# chain が無ければ止める。INPUT/UFWで代用したりbackendを切り替えたりしない。
iptables -I DOCKER-USER 1 -i "$DEM_BETA_INTERFACE" -s "$BLOCK_IP/32" -j DROP
iptables -C DOCKER-USER -i "$DEM_BETA_INTERFACE" -s "$BLOCK_IP/32" -j DROP
iptables -n -v -L DOCKER-USER --line-numbers
# 解除: 登録した同じsource/interfaceの規則だけを消す。
iptables -D DOCKER-USER -i "$DEM_BETA_INTERFACE" -s "$BLOCK_IP/32" -j DROP
iptables -C DOCKER-USER -i "$DEM_BETA_INTERFACE" -s "$BLOCK_IP/32" -j DROP
# 最後の-Cがexit 1なら、その規則は無い。別の規則を番号で推測して消さない。
```

道具は検査済みのargv一覧を表示するだけで、iptablesもshellも実行しない。上の操作は運用者が行う。
同じ規則を重複挿入しない。OS再起動でこの一時規則は消える。Dockerの再起動等でも規則が残ると仮定しない。
再起動後は確認し、攻撃が続いていれば意図して付け直し、終わっていれば消えたままにする。iptables-persistent等へ保存しない。
stagingではスマートフォンのIPの遮断・解除、他sourceの継続利用、再起動で消えることをレビュー側が確認する。

## 新しい公開 commit の配備（この機械では未実行）

まず backup。公開 tag を確認して checkout し、`.env` の COMMIT を完全な SHA に更新、image を build する。
既存 API は切替まで稼働できる。新 image の tools で `dem-beta build-base` → `dem-beta reset` → `dem-beta up`。
古いコード用 compose の API が使われないよう、**reset 前に** `docker compose ... create --force-recreate api` を実施する。
これにより旧 API は停止するため、その直前に freeze し、API 停止を確認してから、確認済み手順で停止印を外して reset prepare に渡す。
無停止配備は目指さない。base build 失敗なら旧 live を維持し、新旧 image / COMMIT を取り違えて起動しない。
install / unit の変更もある場合は installer を再実行し、S1 / S7 / S8 / S9 と各公開ヘッダを再確認する。
旧 base の dump は新 base に復元できるとは限らないので、旧 commit と base 情報を復旧判断用に保持する。

実行順序は次のとおり。各行が失敗したら次へ進まず、上の段階別の復旧手順で確認する。
新しい API がまだ停止している初期構築・更新の最中に prepare が失敗した場合も、自動的に起動や公開再開はしない。
新 API の起動設定を作る前に旧コンテナを止めるため、schema revision が変わった場合も旧 image を起動して健康確認することはない。

```bash
cd /opt/dem-beta
sudo dem-beta backup
sudo git fetch --tags origin
sudo git checkout --detach <approved-public-tag>
# git rev-parse HEAD の完全な SHA を COMMIT に設定。パスワードは変更しない。
sudoedit deploy/beta/.env
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml build
sudo dem-beta build-base
sudo dem-beta freeze
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml create --force-recreate api
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml ps -a api
# API が created / stopped（実行していない）ことを確認してからだけ、prepare に引き渡す。
sudo dem-beta unfreeze
sudo dem-beta reset
sudo dem-beta up
sudo dem-beta status
```

復旧確認後の finish を直接行う完全なコマンドは以下（正常 reset ではシェルが実行するので不要）。

```bash
cd /opt/dem-beta
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml run --rm tools reset finish
```

## 撤収と課金停止（この機械では未実行）

1. 終了告知。任意で最後の backup を安全な手元へ移す。timer と web を停止し、DNS A を削除する。
2. Lightsail **インスタンスを削除**する（停止では課金停止にならない）。静的 IP を解放する。
3. 手動・自動スナップショット、バケット、不要な DNS ゾーン、アラームを削除する。
   別サービスの旧 EC2 / EBS / Elastic IP も所有者が要否を確認する。
4. 翌日以降 Bills / Cost Explorer の日別で費用停止を確認する。Budgets は最終請求を確認して約 1 か月後に削除する。
   これらの削除は利用者が対象を確認して実行する。

## 問い合わせとSlack通知（β4b、staging 未実施）

API は数学の DB に触らず、`/var/lib/dem-beta/contacts` に問い合わせを1件1ファイルで保存する。
書き込み停止・DB満杯・βとDEM_READ_ONLYの併用中も受け付ける。βでなければ `/contact` は404。
接続元ごと1件/10分、全体50件/UTC日で、通常操作の枠とは別。カウンタは単一APIプロセス内なのでAPI再起動で戻る。
未送信の上限は1,000件で、満杯・保存不能なら503。ファイルのJSON・返信先・接続元を公開のログに貼らない。

1. 利用者のSlackワークスペースに、運用者だけが入る非公開チャンネルを用意して参加する。
2. [Slackの公式手順](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)に従い、Slack Appを作成し、Incoming Webhooksを有効にする。
   Add New Webhook to Workspaceから非公開チャンネルを選ぶ。既存ワークスペースの承認手順があれば従う。
3. サーバーの`sudoedit /opt/dem-beta/deploy/beta/.env`で、`DEM_BETA_SLACK_WEBHOOK_URL`に作成した値を設定する。
   root所有600を保持する。URLは秘密であり、リポジトリ・image・チャット・コマンド引数・シェル履歴・スクリーンショットに載せない。
   `set -x`や環境変数の全出力、`docker compose config`の共有はしない。APIへの環境変数追加は不要。
4. Slack側のワークスペースの保持設定を利用者が確認する。ローカルの削除はSlack上の通知を削除しない。
   Incoming Webhookでは送信した通知の取り消しを行えない。実データを送る前に外部への送信と保持期間を確認する。
5. 初回配備の確認が済むまでtimerをstartしない。installerはnotify timerもenableするだけである。
   閉じたstagingで、個人情報のないテスト問い合わせをフォームから1件送り、`sudo dem-beta notify`を実行する。
   202後に未送信ファイルがあり、送信成功後に`contacts/sent/`へ移ること、Slackに種別・受付時刻・対象URL・本文・返信先の有無が届くことを確かめる。
   接続元と返信先そのものは通知しない。返信する場合は運用者がサーバー上の元のファイルを確認する。
6. `<!channel>`・`<@U...>`・`<https://example.invalid|label>`・`&`を含むテスト文字列でmentionやリンクの書式が作られず、プレビューも出ないことを実Slackで確認する。
   [公式の書式仕様](https://docs.slack.dev/messaging/formatting-message-text/)の`&`・`<`・`>`のescapeとplain_textを使い、unfurlを無効にしている。
7. 失敗時にファイルが残って次回再送され、reset-errorの新規・変化、watchのfreeze/stop-web/カウンタ取得不能、ディスク80%以上の警告（85%以上はcritical）、
   問い合わせの保存先1,000件の満杯が通知されることをstagingで確認する。同じ状態は再送せず、正常に戻って再発したときは再通知する。
8. `sudo systemctl start dem-beta-notify.timer`と`sudo systemctl list-timers 'dem-beta-*'`で5分周期を確認する。
   `journalctl -u dem-beta-notify.service`のログは一般的な成否だけで、URL・問い合わせ本文・接続元を含まないことを確かめる。

送信はホストの標準ライブラリのHTTPだけを使う。環境のHTTPプロキシやリダイレクトは使わず、HTTPSのSlack Webhook宛だけに送る
（試験用の例外はloopback HTTPだけ）。1回に問い合わせ5件まで、各送信のtimeoutは5秒。通知専用のlockで重複実行を防ぎ、DB操作のlockを占有しない。
watch/resetのhookは通知用の状態を記録するだけで通信せず、失敗しても元の処理を失敗させない。配信は5分のtimerが行う。
Webhook未設定なら1行だけ記録して正常終了し、配信も削除もしない。この状態のまま公開しない。
送信後に移動する前、または状態を保存する前にプロセスが落ちた場合には重複送信の可能性がある（少なくとも1回の配信）。
読めない・形の不正な問い合わせは`contacts/invalid/`へ隔離し、正常な送信5件の枠には数えない。
新しく隔離したファイルだけを運用通知し、内容・接続元・返信先は通知に含めない。通知失敗は次回再送し、成功済みの隔離通知は繰り返さない。

問い合わせの送信済み・未送信・隔離済みは受付時刻から90日経過で削除する。削除は正確な`contact-<UTC timestamp>-<UUID>.json`の名前を持つ通常ファイルだけで、
無関係なファイル・ディレクトリ・symlinkは対象にしない。Webhookが設定され、timerが動いていることを保持期限の前提にする。
未送信が古くなる前に配信失敗を調査する。容量不足などで問い合わせ自体を保存できない場合には運用者がログとディスクを確認する。

URLを漏らしたときは、Slack Appの管理画面で対象Webhookを無効化/削除し、新しいWebhookを作成してサーバーの`.env`だけを更新する。
古いURLで送信できないことと、新しいURLのテスト通知をstagingで確かめる。流出したURLを調査ログに再掲しない。

規約・ポリシー・免責事項のβ版は[下書き](../ux/public-legal-pages.md)で、利用者の確認待ち。
投稿の利用許諾、禁止事項、削除依頼への対応、ログ/問い合わせ/Slackの保持期間、外部への送信、制定日を利用者が確定してから公開する。

## 参照

- Staging acceptance evidence is recorded separately by the operator.
- [PGDG Debian 公式手順](https://www.postgresql.org/download/linux/debian/)（bookworm-pgdg と client-18）
- [PostgreSQL 公式 image](https://github.com/docker-library/docs/blob/master/postgres/README.md)（18 の volume は /var/lib/postgresql）
- [Docker Ubuntu 公式手順](https://docs.docker.com/engine/install/ubuntu/)
- [Caddy の timeout 構文・固定版ソース](https://github.com/caddyserver/caddy/blob/v2.10.2/caddyconfig/httpcaddyfile/serveroptions.go)
- [Caddy のログ](https://caddyserver.com/docs/caddyfile/directives/log)、[respond](https://caddyserver.com/docs/caddyfile/directives/respond)
