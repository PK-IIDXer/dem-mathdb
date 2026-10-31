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
  `swapped` / `failed_restored` で token が合うなら、確認後 `docker compose ... run --rm -T tools reset finish`。
  prepare 失敗だけなら unfreeze は不要。別の理由で既存 freeze があるときは、その理由を確認してから解除する。
  未処理 next / old を推測で削除しない。
- reset swap の入口で失敗し、phase が `prepared` のままの場合: まず失敗の原因を除く。
  **API を止める前に** `state/prepared.json` の phase が `prepared` であり、その token が `flags/read_only` の tools の停止印と一致することを確認する。
  一致を確認してから API を停止 → `docker compose ... run --rm -T tools reset swap` → API を起動し healthy を待つ →
  `docker compose ... run --rm -T tools reset finish` の順に復旧する。`reset-error.json` は、復旧確認後にfinishしてから手動で削除する。自動配備導入後は次の定期resetも復旧待ちで止まるため、それを待って消去しない。
  未処理の next / old を推測で削除しない。この順序は閉じた staging で実際に確認した手順。
- DB 復元: `sudo dem-beta restore dem-beta-backup-<timestamp>-<id>.dump`。
  ファイルは `/var/lib/dem-beta/backups` に UID 10001 が読める状態で置く（引数は basename のみ）。
  **API を止めてから** tools restore が next を構築・検査・切替し、API 起動 → healthy → finish。
  復元は保存された現在の base digest と一致するものだけ。旧 base の dump や改ざんは拒否される。
  検査に通らなければトリガを緩めず、原因確認後に現在の base から reset する。
- サーバー喪失: 日次スナップショットから新規インスタンスを作り、static IP を付け替える。
  firewall・IPv6・timer・API / DB・counter の復帰を確認し、古いインスタンスが二重稼働しないようにする。

## 接続元 IP の緊急遮断

staging で遮断・解除・再起動による規則の消失と、遮断中の SSH 利用を確認済み（確認記録 §74.6）。例の `eth0` は実際の interface に置き換える。

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

まず backup。公開 tag を確認して checkout し、`.env` の `DEM_BETA_COMMIT` を完全な SHA に更新、image を build する。
既存 API は切替まで稼働できる。新 image の tools で `dem-beta build-base` → `dem-beta reset` → `dem-beta up`。
古いコード用 compose の API が使われないよう、**reset 前に** `docker compose ... create --force-recreate api` を実施する。
これにより旧 API は停止するため、その直前に freeze し、API 停止を確認してから、確認済み手順で停止印を外して reset prepare に渡す。
無停止配備は目指さない。base build 失敗なら旧 live を維持し、新旧 image / DEM_BETA_COMMIT を取り違えて起動しない。
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
# git rev-parse HEAD の完全な SHA を DEM_BETA_COMMIT に設定。パスワードは変更しない。
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
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml run --rm -T tools reset finish
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
- [Caddy の timeout 構文・固定版ソース](https://github.com/caddyserver/caddy/blob/v2.11.7/caddyconfig/httpcaddyfile/serveroptions.go)
- [Caddy のログ](https://caddyserver.com/docs/caddyfile/directives/log)、[respond](https://caddyserver.com/docs/caddyfile/directives/respond)


## 公開時の DNS と継続的な security 更新

公開する際は A と同時に CAA `0 issue "letsencrypt.org"` と `0 issuewild ";"` を作る。AAAA は作らない。
CAA で既定の予備発行元も制限されるため、Let's Encrypt の発行に失敗したら公開を待つ。この DNS 手順は staging 未確認。

週 1 回、ホストの利用可能な更新、自動 security 更新の結果、再起動の要否を確認する。
image の OS package 一覧と Caddy / Go / Python / PostgreSQL の実際の版を取り出し、
Python・frontend の lock とともに OSV の package 名・版の照合を行う（security 点検記録 §79.1 の方法）。
CA bundle は証明書の subject を調べ、emSign ECC Root CA - G3 がないことを確認する。
この週次手順の一連の実行は staging 未確認。

security release が出たら一次情報で適用対象と互換性を確認し、版・digest・lock・CI の目標を同時に更新する。
試験に合格した候補を既存の backup → build → 配備の手順で staging に入れ、
Caddy / Go / CA、DB の reset・backup・restore、S1〜S10・IP・CSP・INDEX・MAINT を再確認する。
失敗時は公開を進めず、既存の復旧手順で戻す。新しい版によるこの更新手順は staging 未確認。
配備の Python 目標は CPython 3.13.18 / Linux x86_64 / Debian bookworm。


### Caddy binary の週次点検（staging 確認済み、§83.2）

稼働中の web の `/usr/bin/caddy` を取り出し、使い捨ての digest 固定 builder container で
`go install golang.org/x/vuln/cmd/govulncheck@v1.9.0` の後に
`govulncheck -mode=binary -json /scan/caddy` を実行する。配備 image に検査用の道具を入れない。
例えば、ホストの `/opt/dem-beta` で次を行う (JSON は消さずに点検記録へ保存する)。

```bash
scan_dir="$(mktemp -d)"
web_container="$(sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml ps -q web)"
test -n "$web_container"
sudo docker cp "$web_container:/usr/bin/caddy" "$scan_dir/caddy"
scan_status=0
sudo docker run --rm -v "$scan_dir:/scan:ro" \
  caddy:2.11.7-builder@sha256:bf6a7d38add2508b7d2e3e3f40cf2af399214f143c0fa3daa51f254e01f8d293 \
  sh -ec 'go install golang.org/x/vuln/cmd/govulncheck@v1.9.0; govulncheck -mode=binary -json /scan/caddy' \
  > "$scan_dir/govulncheck.json" || scan_status=$?
printf 'govulncheck status=%s, report=%s\n' "$scan_status" "$scan_dir/govulncheck.json"
```

JSON stream の `config.db_last_modified` (DB の日付)、`config.db`、scanner の版、実行時刻、
対象の公開 commit と binary の hash を一緒に記録する。終了コード・解析エラーと findings を必ず読み、
非 0 終了を合格として扱わない。symbol が binary に含まれるか、Caddy の経路に関わるかを各項目で判断する。
§83.2 は DB 2026-10-27 版で実行した確認記録であり、週次点検では毎回の DB の日付を記録する。


## アクセスログの異常通知（staging で確認するまで未確認）

既存の5分ごとの notify timer が Caddy の現行・回転済み gzip ログを集計する。
Slack・状態ファイル・確認用表示には件数、割合、固定の区分名と UTC 時刻だけを出す。
接続元は実行中だけ数え、IP・その hash・URL・header・log 原文は残さない。
通知は `Beta traffic:` で始まる英語の plain text。件数だけで攻撃と決めない。
CGNAT 等で利用者が同じ接続元を共有する場合もある。自動の遮断・freeze・web 停止は行わない。

| 種類 | 通知する条件 |
| --- | --- |
| api_errors | 直近5分の API 5xx が10件以上 |
| rate_limited | 直近5分の429が300件以上 |
| source_volume | 直近5分の1接続元が3,000件以上 |
| total_volume | 直近5分の全体が10,000件以上 |
| writes | 直近60分の API 書き込み成功が全体500件以上、または1接続元150件以上 |
| log_unreadable | 現行ログの欠落・非通常ファイル・symlink・読取不可、回転ログの読取失敗、または不正行20件以上かつ読んだ全行の1%以上 |
| analysis_failed | 例外・直近集計20秒／日次集計15秒の時間制限・各集計の容量上限等で完了しなかった |

初回に開始、継続中は送信成功から60分以上後、条件を30分続けて満たさなくなったら解消を通知する。
直近の集計失敗・ログ読取不能の間は、他の異常を解消せず、clear の継続時間をリセットする。古い件数による継続も送らない。
読めた範囲だけで閾値を超えるものは開始・継続を送る。復帰後に成功した集計で30分の clear を観測してから解消する。
送信失敗は次回に再送する。問い合わせを先に配信し、traffic は1回につき最大3通とするため、複数の異常は次の実行に回る場合がある。
状態は root 専用 `host-state/traffic-state.json` に atomic に保存する。既存の notify 状態とは別で、DB 操作の lock を取らない。
UTC 0時（日本時間9時）後、前日分が未送信のときだけ別の子 process で日次集計し、要約を送る。失敗時は前日分だけ再試行し、2日以上前は送らない。
日次の失敗も analysis_failed で知らせるが、直近の観測不能とは扱わず、5分・60分の判定は続ける。日次要約の送信失敗も現在の異常通知を止めない。
要約には状態コード class、429・5xx、API 区分、上位5接続元の割合、固定の探り pattern に合う件数と接続元数、異常の開始回数を含む。
開始時刻までログが残らない場合や読取失敗があれば `partially missing` と表示する。
`complete` は読み取れた最古の時刻による推定であり、途中のログ消失まで検知する保証ではない。

例（固定の文・数値のみ）:

```text
Beta traffic: api_errors started
UTC: 2026-10-30T00:05:00Z
Started UTC: 2026-10-30T00:05:00Z
count: 10
total: 100
sources: 2
Inspect counts in a root interactive terminal with:
python3 deploy/beta/access_log.py summary --minutes 5
```

受信したら root の対話端末で `/opt/dem-beta` に移動して、まず案内の `access_log.py summary` を実行する。
回転境界をまたぐ場合は既存 summary に対象を `--log FILE` で明示する。
UTC 時刻・状態コード・ホスト負荷と照合し、必要なら既存の「接続元 IP の緊急遮断」、`dem-beta freeze`、web 停止の順に判断する。
IP を含む summary の出力を Slack に貼らない。`log_unreadable` はファイル・権限・回転、不正行の増加を調べ、
`analysis_failed` は処理量・時間・容量と unit の終了状態を確認する。ログ原文を journal や通知へ転記しない。

送信しない確認（root の対話端末だけ、状態も更新しない）:

```bash
cd /opt/dem-beta
sudo dem-beta traffic --dry-run
sudo dem-beta traffic --dry-run --log /root/traffic-test.log --log /root/traffic-test.log.gz --now 2026-10-30T00:05:00Z
```

`--log` は繰返し指定できる。明示しない場合、通常は現行と直近60分に必要な回転ログ、開始をまたぐ境界の1ファイルまでを読む。
回転名の時刻（他の形は mtime）で古いファイルを開く前に絞り、境界が不正行だけ・読取不能でもその先の古い日には進まない。
前日分は未送信のときだけ独立した日次 worker が前日の開始と境界まで読む。送信済みなら日次のファイルを開かない。
同一行のファイル間の重複を除き、同じファイル内の同一行の回数は保持する。回転ログの時系列を前提とする。
64 KiB 超の行は小さな chunk で読み飛ばして不正1行とする。時刻・状態コード・IPv4 が不正な行や60秒以上未来の行も除く。
不正率の分母は直近60分のために選んだファイルと境界ファイルから読んだ全行（境界内の窓より古い行も含む）で、日次の行を混ぜない。
直近の子 process は20秒、日次は独立して15秒で打ち切る。容量は直近20万・日次25万の異なる行キーと接続元数を上限とする。
重複行キーを2つの一時辞書に持つ場合も容量の分母に二重計上しない。日次の容量超過は日次だけを再試行する。
最悪の送信枠は既存の運用通知7通×5秒=35秒、問い合わせ5通×5秒=25秒、直近集計20秒、日次15秒、traffic3通×5秒=15秒で計110秒。
2分の service 上限に対し残り10秒を読み書き・起動等の余裕とする。新しい timeout や容量上限でも未完了を正常とは扱わない。
API 経由の推定は response の Via を使い、無いものは edge_or_unknown とする。成功書き込みは Via 付き2xxだけ。
停止中の書き込み503は Via と既知の短い maintenance JSON の Content-Type / Content-Length、Retry-After・Content-Encoding 無しが揃うものだけ除く。
本文の code はログに無いのでこれは応答の形による推定である。同じ形の別の503は区別できない。
既知の beta.full・pool（Retry-After 有り）・uvicorn（plain text）や形の不明な503は除かない。
実際の Via と maintenance の形は staging で必ず確かめ、不一致なら適用を止める。

### ホスト側だけの更新（staging で確認するまで未確認）

今回の更新は image・DB・Caddy 設定を変更しない。既存の通常更新の reset 手順を使わず、以下だけを行う。
先に承認済み公開 tag を取得済みであること、作業ツリーが clean であることを確認する。
`DEM_BETA_COMMIT` は **今稼働中の image に対応する既存の SHA のまま** とする。
checkout する新 tag はホスト道具の版であり、稼働 image の版とは独立する。image を実際に更新する別作業でだけ同値を変更する。
`.env` の表示・再生成はしない。Web/DB/API コンテナ、live/base、問い合わせ、停止印を保持する。

```bash
sudo systemctl stop dem-beta-notify.timer
# 実行中の oneshot があれば完了まで待つ。service の stop で配信を中断しない。
sudo systemctl show dem-beta-notify.service -p ActiveState -p SubState
# inactive/failed になったことを確認してから進む。
cd /opt/dem-beta
sudo git checkout --detach <approved-public-tag>
sudo install -o root -g root -m 0755 deploy/beta/bin/dem-beta /usr/local/sbin/dem-beta
sudo install -o root -g root -m 0644 deploy/beta/systemd/dem-beta-notify.service /etc/systemd/system/dem-beta-notify.service
sudo stat -c '%U %G %a' /var/lib/dem-beta/host-state
# root root 700 を確認。既存の状態を削除・置換しない。
sudo systemctl daemon-reload
sudo dem-beta traffic --dry-run
sudo systemctl start dem-beta-notify.timer
sudo systemctl list-timers dem-beta-notify.timer
```

新しい Python module は checkout 先から読まれるので別の install は不要。
全体の installer（apt/Docker を含む）は再実行しない。build・build-base・reset・up・コンテナ再作成も行わない。
失敗時は timer を止め、oneshot 完了後に以前の承認済み tag と wrapper / unit だけに戻し、reload する。
新しい traffic-state は root 専用のまま保持する。次の更新で再利用できる。

レビュー側は staging で、Ubuntu Python 3.12、権限と2分の unit 制限、DB lock 中の実行、reset 無しの更新とデータ保持を確認する。
作成したログ（gzip・回転境界・不正行・未来・各閾値・停止中/停止外503）で dry-run を行い、canary の IP・URL・header が出ないことを確かめる。
実際の攻撃や負荷を起こして試さない。既存の承認された Webhook で件数だけの試験通知・日次要約・失敗後の再送と重複防止を確認し、
問い合わせ配信が継続することも確認する。実通知はレビュー側が行い、この実装作業では送信していない。


## beta-2026-11.11 の通常配備予定（未実行）

beta-2026-11.10 は frontend CI 失敗のため配備対象外。tag は残し、この手順では使わない。

実施担当はレビュー側。2026-11-02（月）04:00 JST = 2026-11-01 19:00 UTC の定期resetが
正常に完了した直後に行う。定期resetから以下の配備resetまでの投稿は失われる。
これは定期的に戻す共有βの運用であり、今回は通常のbackup / build / build-base / API再作成 / reset / upを使う。
個別migrationの手作業やデータ移行は追加しない。ホスト側だけの更新手順は今回には使わない。

今回は書き込みを失う間隔を狭めるため、backup直後・build前にfreezeする。
freezeはbuild約4分を含み、base作成・検査・API再作成・reset・起動確認の時間も加わる。
時間は実機で未測定。開始・解除のUTC時刻と所要時間をレビュー側が記録する。
freezeまでに受けた投稿を配備resetが消すことは残る。build失敗時は先へ進まず、既存の段階別復旧手順で判断する。

```bash
cd /opt/dem-beta
# 定期resetが成功していることと、現在のtag・image SHA・base情報を記録する。
sudo dem-beta status
sudo dem-beta backup
sudo dem-beta freeze
sudo git fetch --tags origin
sudo git checkout --detach beta-2026-11.11
# 公開候補のレビュー済みtreeとtagを照合する。
# 今回はimageを更新するので、DEM_BETA_COMMITをこのtagの完全なSHAへ更新する。
# 資格情報は変更・表示しない。
sudoedit deploy/beta/.env
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml build
# 失敗したら進めない。runはservice用portをpublishしない。
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo dem-beta build-base
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml create --force-recreate api
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml ps -a api
# 新APIがcreated/stoppedで実行していないことを確認後だけ、停止印をprepareに渡す。
sudo dem-beta unfreeze
sudo dem-beta reset
sudo dem-beta up
sudo dem-beta status
```

APIが止まる前にunfreezeしない。resetのprepare / swap / start / finishが失敗したら、通常の復旧手順で止めて確認する。
upのbuildは変更の無いimageのcacheを使う予定だが、所要時間は未測定。検査不合格を理由にDBのガードを外さない。

配備後の確認（すべてこの修正版では未実行）:

- Homeの任意開始からチュートリアル9操作でverified。通常の定理案内・集計・候補・依存グラフから練習を除き、直接URLと数式は共有すること。
- maintenance / full / read-only・前提欠落・取得失敗で入口全体が消え、リセット後は前提を再取得すること。
- 429/503の既存案内と、途中まで保存された公理・Gen・検証の再開。自動リトライで負荷を増やさない。
- 実URLでh2とh1.1が応答し、Alt-Svcのh3案内が無いこと。UDP443はpublishせずfirewallも変更しない。
- 既存のS1/S4/S7/S8/S9/S10/IP/CSP/INDEX/MAINT/ROLE/LOAD/OPS/TZと公開ヘッダの確認を再実施する。
- freeze中の既知のmaintenance503はtrafficのAPIエラーから除外される。API停止中のCaddy502/504や他の503は数える。
  配備の実5xxが5分10件以上ならapi_errors開始は観測として正しく、攻撃と決めない。時刻と配備段階に照合する。
  開始した場合は復旧後30分連続clearで1回だけ解消され、観測不能中は解消されないことを確認する。
- 既存の問い合わせ・日次要約・ログ異常通知も確認する。試験後の練習は次の通常resetで消え、今回追加のresetで利用者の投稿を消さない。


## beta-2026-11.14 の通常配備予定（未実行）

beta-2026-11.13 は公開 CI の frontend 試験が2件失敗したため配備対象外とし、tag は残す。11/9 は修正版 beta-2026-11.14 を配備する。

日英切り替えの配備予定。英語の法的文書は2026-10-30に利用者承認済み。公開候補のレビュー完了が前提。11/2向けの11.12の予定は変更しない。

実施担当はレビュー側。2026-11-09（月）04:00 JST = 2026-11-08 19:00 UTC の定期resetが
正常に完了した直後に行う。定期resetから以下の配備resetまでの投稿は失われる。
これは定期的に戻す共有βの運用であり、今回は通常のbackup / build / build-base / API再作成 / reset / upを使う。
個別migrationの手作業やデータ移行は追加しない。ホスト側だけの更新手順は今回には使わない。

今回は書き込みを失う間隔を狭めるため、backup直後・build前にfreezeする。
freezeはbuild約4分を含み、base作成・検査・API再作成・reset・起動確認の時間も加わる。
時間は実機で未測定。開始・解除のUTC時刻と所要時間をレビュー側が記録する。
freezeまでに受けた投稿を配備resetが消すことは残る。build失敗時は先へ進まず、既存の段階別復旧手順で判断する。

```bash
cd /opt/dem-beta
# 定期resetが成功していることと、現在のtag・image SHA・base情報を記録する。
sudo dem-beta status
sudo dem-beta backup
sudo dem-beta freeze
sudo git fetch --tags origin
sudo git checkout --detach beta-2026-11.14
# 公開候補のレビュー済みtreeとtagを照合する。
# 今回はimageを更新するので、DEM_BETA_COMMITをこのtagの完全なSHAへ更新する。
# 資格情報は変更・表示しない。
sudoedit deploy/beta/.env
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml build
# 失敗したら進めない。runはservice用portをpublishしない。
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo dem-beta build-base
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml create --force-recreate api
sudo docker compose --env-file deploy/beta/.env -f deploy/beta/compose.yml ps -a api
# 新APIがcreated/stoppedで実行していないことを確認後だけ、停止印をprepareに渡す。
sudo dem-beta unfreeze
sudo dem-beta reset
sudo dem-beta up
sudo dem-beta status
```

APIが止まる前にunfreezeしない。resetのprepare / swap / start / finishが失敗したら、通常の復旧手順で止めて確認する。
upのbuildは変更の無いimageのcacheを使う予定だが、所要時間は未測定。検査不合格を理由にDBのガードを外さない。

配備後の確認（すべてこの修正版では未実行）:

- `?lang=en`で英語になり、保存した言語が再読込後も維持され、`<html lang>`が表示言語に一致すること。法的3ページ・問い合わせ画面が英語になり、βの帯の日時も表示言語の書式になること。

- Homeの任意開始からチュートリアル9操作でverified。通常の定理案内・集計・候補・依存グラフから練習を除き、直接URLと数式は共有すること。
- maintenance / full / read-only・前提欠落・取得失敗で入口全体が消え、リセット後は前提を再取得すること。
- 429/503の既存案内と、途中まで保存された公理・Gen・検証の再開。自動リトライで負荷を増やさない。
- 実URLでh2とh1.1が応答し、Alt-Svcのh3案内が無いこと。UDP443はpublishせずfirewallも変更しない。
- 既存のS1/S4/S7/S8/S9/S10/IP/CSP/INDEX/MAINT/ROLE/LOAD/OPS/TZと公開ヘッダの確認を再実施する。
- freeze中の既知のmaintenance503はtrafficのAPIエラーから除外される。API停止中のCaddy502/504や他の503は数える。
  配備の実5xxが5分10件以上ならapi_errors開始は観測として正しく、攻撃と決めない。時刻と配備段階に照合する。
  開始した場合は復旧後30分連続clearで1回だけ解消され、観測不能中は解消されないことを確認する。
- 既存の問い合わせ・日次要約・ログ異常通知も確認する。試験後の練習は次の通常resetで消え、今回追加のresetで利用者の投稿を消さない。


## 承認済み tag の自動配備（β7 修正1、実Docker・実機は未確認）

公開A番号とは別に、利用者が承認したtag/完全commit/tree/次回reset日時をrootが登録する。hostが公開HTTPS originからpullする。
GitHub Actionsの配備job・SSH鍵・新secretは作らない。11/2の11.12と11/9の11.14の予定・手順は変更しない。導入日は未定。

### 資源の設計と移行

稼働projectは **dem-betaに固定**する。既存のdem-beta_proxy（172.30.42.0/24、internal）、web .2、api .3をそのまま使い、
APIが信用する転送元172.30.42.2も変更しない。Caddyは既存の **dem-beta_caddy_data / dem-beta_caddy_config** を名前で指定して引き継ぐ。
証明書・ACME account/keyを消したり、配備ごとに新規volumeを作ったりしない。network/公開port/証明書volumeは世代にしない。

DBだけを `dem-beta-db-<commit>-<unique>` の外部volumeにする。既存hostの初期値は **dem-beta_pgdata**。
main composeはpgdataをexternalとして名前で参照する。初回新規installerだけは既定volumeを明示作成する（既存volumeは保持）。
準備用 `prepare.compose.yml` はdb/toolsとinternalのdatabase networkだけを定義し、固定subnet/IP、proxy、public port、Caddy volumeを一切持たない。
image buildはdocker build、Caddy検査は `docker run --rm --network none`（ログはtmpfs、既存証明書のmountなし）で行う。
準備DBでroles/build-base/statusを通し、候補コンテナを停止・除去してから準備完了とする。切替まで稼働DBは旧volumeのまま。

切替時は旧API/Web/DBを止め、停止確認後にdem-betaのDBを **--force-recreate** して準備済みvolumeを選ぶ。
volumeの定義だけ変わったときも旧mountが残らないよう強制再作成する。候補DBはその前に停止を再確認し、同じvolumeに二つのPostgreSQLを起動しない。
旧DBコンテナは再作成で置き換えられ、旧volumeは残す。API/Webも同じdem-beta projectで新imageへ更新する。
`down`で稼働networkを破棄しないので、2回目以後もproxyと証明書の名前は同じである。
根拠となる定義は[Dockerのvolume name/external](https://docs.docker.com/reference/compose-file/volumes/)と[network](https://docs.docker.com/reference/compose-file/networks/)。
これらの定義と静的試験は実Dockerでの成功を示すものではない。

**既存本番からの移行:** 昼間のhost道具更新ではcheckout/wrapper/unitだけを更新し、DEM_BETA_COMMITは旧imageのSHAのまま、
DEM_BETA_DB_VOLUMEは未設定（既定dem-beta_pgdata）または既存volume名とする。稼働コンテナは再作成しない。
proxy/証明書/DBの物理的な名前はこの時点では変わらないため、host道具の初回導入にサービス停止やresetは要らない。
その後の **承認した定期resetの1回** で初めてDBvolumeを世代へ切り替える。この回は旧API/Web/DBの停止、DB再起動、検証、API/Web再起動が必要。
停止時間は実機未測定で、上限はreset serviceの20分。短い無停止更新とは扱わない。失敗後の停止は人の復旧まで続く。
初回移行も2回連続の配備も、stagingの実Dockerで確認してから本番を承認する。

### 登録・確認・取り消し

```bash
sudo dem-beta deploy-dry-run <beta-tag> <full-commit-sha> <full-tree-sha> <reset-ISO8601-with-timezone>
sudo dem-beta deploy-approve <beta-tag> <full-commit-sha> <full-tree-sha> <reset-ISO8601-with-timezone>
sudo dem-beta deploy-status
sudo dem-beta deploy-cancel
```

日時はhostの既存scheduleと一致する次回（7日以内）だけ。本番の月曜04:00 JSTは変更しない。
登録・準備・切替直前にcommit/treeを照合し、候補コードは照合前に実行しない。deploy/beta全体に差分があれば手動host更新を先に行う。
Dockerfile/Caddy/lockだけの変更も保守的に拒否する。host道具のcheckout SHAと稼働image SHAを別に照合するので、host-only導入後も登録できる。
自動配備を一度行った後に既存の手動配備手順を使う場合は、そこでのcd /opt/dem-betaと.env/composeの参照先を、active-repoが選ぶcheckoutへ置き換える。
既存のDEM_BETA_DB_VOLUMEを保持し、稼働projectはdem-betaを明示する。退役した/optの.envを更新して稼働版を取り違えない。
originは資格情報のないhttps://github.com/所有者/repoに限定する。追跡ファイルの変更も拒否する。
root専用host-state（700）のファイルを600で原子的に保存し、承認は成功・失敗・取消いずれも単回消費する。既存承認は先に取り消す。
dry-runは一時取得・照合だけ。statusは秘密を表示せず、取消は準備中にも無効化印を置いて候補publishを拒否する。

生成する.envはbash sourceとComposeの両方でリテラルになる文字に制限する。英数字と `_./:@%+=, ?&-`、空白、空値だけを単引用符で囲む。
単/二重引用符、$、#、backslash、改行、backtick、制御文字、その他の文字は停止前に拒否する。
既存の生成hex passwordとSlack URL/schedule/標準host pathはこの範囲内。拒否した値やsubprocess出力は記録・表示しない。

### 通常の流れとlock

5分周期prepare timerが1時間前から準備し、最大45分。登録を消費してからDocker資源の所有情報をroot専用deploy-candidatesへ永続化する。
別DBで本物のbase構築・検査を行い、seed/proof検証・DBガードは省略しない。現行checkout/.env/live/base/image参照は変えない。
準備はdeploy.lockだけを長く持つ。watch/backup/statusは旧版・旧DBで動く。準備publishだけ短いoperation lockを取る。
候補は準備完了後も停止状態で待つ。prepareが間に合わなければ旧版の通常resetを行う。
切替のoperation lockは最大20分。watch/backup/statusはその間75で終了し、disk85%freeze等の監視が最大20分休止し得る。
notifyは独立lockなので動く。準備の掃除もDocker stopの待ち（通常最大30秒、command上限120秒）を使い、掃除失敗は記録して次回再試行する。

指定時刻より前には切替しない。早いscheduled-reset呼出は承認を保持して **early-reset-rejectedを通知**し、resetしない。
Persistent timerによる遅延は指定時刻から5分以内だけ候補に使える。5分超なら承認を消費し、期限切れ通知と旧版通常reset。
正常切替は旧版backup → 時刻再確認 → 切替中の印/停止印 → 旧API/Web/DB停止とAPI停止確認 → 新volumeでDB起動 →
新版prepare → swap → API/Web起動と検査 → finishの1回だけ。先に旧版のresetはしない。
active-repoを原子的に変更して他timerも新checkout/.env/DBvolumeを使う。/opt/dem-beta自体を準備中に変更しない。

### 通知・中断・失敗と復旧

切替開始は **deploy-switching.json**（開始時刻と実際の段階）を保存する。成功する切替中にreset-errorやswitch-failedは書かない。
notifyが途中のどの段で動いても失敗とは配信しない。切替中の印が開始から20分残れば、service上限を超えた中断として失敗を通知する。
中断では停止印を保持し、次のscheduled-resetも手動復旧待ちで止める。実際に例外を検出した場合だけreset-errorにstop/prepare/swap/start/ready/finishの実段階を書く。

| 条件 | 状態と処置 |
|---|---|
| 照合・差分・build・Caddy/base検査等の停止前失敗、壊れた/権限不正な承認・consumed・prepared、unlink競合 | 承認/準備を消費し、通知し、旧版で通常reset。個別の記録/掃除の例外でも通常resetを黙って飛ばさない |
| 準備失敗・期限切れ・取消 | 登録した候補projectのコンテナを止めて除去する。volumeは残す。掃除失敗は次のprepare/resetで再試行し通知 |
| 準備processの強制終了/timeout | dockerd側のコンテナは残り得るので、次のprepareまたはscheduled-resetが永続registryの所有候補を止める。45分preparingのままなら中断通知 |
| API停止を始めた後の失敗・image/commit不一致・API不健康 | freeze/reset-errorを保持、switch-failedを通知。finish/unfreeze・旧版の自動起動はしない |
| **新webが起動する前の失敗** | **旧webも止まっているため、読取も含めサイト全体に到達できないことがある。人の復旧まで全停止が続く** |
| 20分を超えたswitching印 | 中断失敗として通知、書込停止・次回reset停止。自動rollbackなし |
| 既存reset-errorがある次の定期回 | **通常resetの失敗由来も含め**復旧待ちで停止し、その回ごとにrecovery-blocked通知 |
| 公開ヘッダ・next_reset・protocol・ページGETだけの失敗 | 版/健康を確認したうえでfinish、警告を通知 |

**従来との差:** 以前は通常resetの失敗後も翌週のtimerが再試行した。自動配備導入後はreset-errorがある限り、由来を問わず翌週も止める。
失敗後に管理者の判断なしで書き込みを再開しないための厳格化であり、旧版の自動復旧と取り違えない。止めた回ごとに通知時刻を更新する。
数学の検証・base検査・DBガードの受入条件は変更しない。通常resetコマンド自体の既存検証・回復手順は維持するが、timerの再試行方針はこの差分に従う。
復旧ではpointer、旧/新DBvolume、image/commit/schema、base参照、prepared.json、backupを確認する。旧schemaへ戻せる保証はない。
正常な復旧を人が確認してから停止印・reset-error・中断印を処置する。それまでは手動でもfinish/unfreezeを行わない。

必須検査はAPI健康、API/Webのimage参照とID、APIのDEM_BETA_COMMIT、公開/api/health/readyのok。
警告検査は/api/configのnext_reset_at、HSTS/nosniff/CSP等とnoindex、h2/h1.1の実際の版、Alt-Svc不在、主要6ページGET。
書込チュートリアルは自動化しない。既存の記録→notify timer→Slack経路を使い、本作業で実Slack送信はしない。

### 片付けと容量（昼間、成功/失敗を確認した24時間以内、次回承認前）

コンテナは自動停止する。成功時は旧dem-betaのAPI/Web/DBを止めて置き換え、準備projectは全コンテナと専用networkを止めて除去する。
失敗・取消・期限切れ・強制終了もregistryに列挙したdem-beta-prepare-<id>だけを止める。固定のdem-betaや他のprojectを掃除対象にしない。
**volumeは自動で消さない。** 旧DB、image tag、checkout/git object、runtimeは世代ごとに残るので、運用者が翌日の24時間以内に確認して整理する。
復旧中の世代は削除しない。必要なら次回の承認を延期する。掃除せず何週間も運転しない。

1回の追加diskは、DBvolume 1個（V）、API/Webの新規image layer（I）、checkoutと2つのgit object領域（C）、build cache（B）とruntime（R）で **V+I+C+B+R**。
実Docker実測は未実施。承認前の予算は保守的に `2×現DB使用量 + 新API/Webの全image size + 2×source/git使用量 + build cache余裕 + runtime余裕` とする。
計算例に限ればV予算2 GiB、image合計1.25 GiB、source/git予算0.4 GiB、cache/runtime1 GiBで **4.65 GiB/回**。
これは実測値でも上限保証でもない。新しいseed/imageで増える場合は事前に予算を増やす。
`docker system df -v`、各volumeの使用量、releasesのdu、dfから容量を見積もり、準備後でもdisk使用80%未満になる余裕を確保して承認する。
watchの80%通知・85%freezeは維持する。容量不足なら掃除/増設後まで承認しない。

削除は次の手順で、人が対象の完全名を確認して行う。docker system prune/volume prune、down -v、wildcard削除は使わない。

1. prepare timerを止め実行中service完了を待ち、承認/準備がないことをdeploy-statusで確認する。operation.lock/deploy.lockが空いている昼間に行う。
2. active-repo（初回は/opt/dem-beta）のroot専用.envから、DEM_BETA_COMMITとDEM_BETA_DB_VOLUME（省略時dem-beta_pgdata）だけを確認する。env全体を表示しない。
   `docker ps -a`とvolume inspectで現DBのMount、候補registryのid/volume/projectを照合する。backupが利用でき、復旧不要と判断した世代だけを選ぶ。
3. 退役volumeの完全名を選ぶ。現DBvolumeと一致しないことと、`docker ps -a --filter volume=<退役volume>`が空であることを確認する。
   **この確認後だけ** `sudo docker volume rm <退役volumeの完全名>`。最初の退役volumeはdem-beta_pgdataになり得る。Caddyの2volumeは削除対象外。
4. registryの退役image IDが現行/準備IDと異なり、どのコンテナにも使われていないことを確認して、
   `sudo docker image rm dem-beta-api:candidate-<退役id> dem-beta-web:candidate-<退役id>`（-fなし）。同じcommitでもIDで判断する。従来commit tagのimageを整理するときも、IDと使用中コンテナを照合する。
5. 退役releases/<id>をrealpathで解決し、/var/lib/dem-beta/releases直下の正しいidで、active-repoの親でもpreparedの親でもないことを確認する。
   確認済みの完全パスだけを `sudo rm -r -- <確認済み退役releaseの完全パス>` で削除する。root直下や変数の未確認展開へ再帰削除しない。
6. volume/containers/checkoutの整理が済んだidだけ、host-state/deploy-candidates/<id>.jsonを完全名で削除する。registryを先に消して孤児を作らない。
   build cacheの整理が必要なら他buildがないことを確認し、そのDocker公式手順で容量を記録して実施する。準備timerを戻し、df/du/docker system dfを再確認する。

### 初回host道具の導入（昼間、未実行）

利用者承認後、全timerを一時停止し、oneshot完了を待つ。API/Web/DBはそのまま動かし、現在wrapperが選ぶcheckout（初回/opt/dem-beta）を承認tagへ更新する。
DEM_BETA_COMMITと既存DBvolume名は保持する。wrapperと全unitを更新し、reloadする。

```bash
cd /opt/dem-beta
sudo git checkout --detach <approved-host-update-tag>
sudo install -o root -g root -m 0755 deploy/beta/bin/dem-beta /usr/local/sbin/dem-beta
sudo bash -c 'set -a; source deploy/beta/.env; set +a; python3 deploy/beta/host.py units deploy/beta/systemd /etc/systemd/system "$DEM_BETA_RESET_SCHEDULE"'
sudo systemctl daemon-reload
sudo dem-beta deploy-status
sudo dem-beta status
sudo systemctl enable dem-beta-deploy-prepare.timer
sudo systemctl start dem-beta-reset.timer dem-beta-backup.timer dem-beta-watch.timer dem-beta-notify.timer dem-beta-deploy-prepare.timer
sudo systemctl list-timers 'dem-beta-*'
```

GitとcurlのHTTP2対応も確認。全installer、build/build-base/reset/up/コンテナ再作成はこの昼間の操作では行わない。
Persistentの未処理resetがある状態や04:00直前にはtimerを再開しない。
同じtagを最初の自動配備に承認できる。DBの実際の移行停止は承認済み定期resetの時だけにまとめる。

### staging予行（要利用者承認、修正2の再予行は未実施）

11.15の予行で資源の引継ぎは確認されたが、F1/F2で不合格になった。修正2のimage/mode対応後は、以下の実Docker確認をレビュー側がやり直す。
閉じたstagingで、既存dem-beta projectのproxy/IP/ports/証明書volume/DBvolumeのIDとCaddy accountを記録してから始める。

- scheduleを一時的に近い曜日/時刻にそろえ、画面とunitも同じにする。準備に十分な猶予をとる。本番schedule/11月の予定は変更しない。
- **旧project稼働中のbuild・network無しCaddy検査・DB準備全段**が成功し、旧proxy/証明書/DBを変更しないこと。
- **初回移行と切替**でproxy network ID/固定IPが同じ、Caddy volume ID/account/certificateが同じ、既定dem-beta_pgdataが残り、DBが新世代volumeを使うこと。
- **2回連続の切替**で同じnetwork/証明書を維持し、証明書を再発行しないこと。旧DB/準備DBのコンテナが毎回止まっていること。
- build/Caddy/base失敗、期限切れ、取消、準備processの強制終了→次prepare/resetの掃除、switch強制終了→20分後の失敗通知/次回reset停止。
- tag付替え、host差分拒否、unsafe/corrupt承認/consumed/preparedとunlink競合で、停止前なら通常resetが行われ通知されること。
- notifyを切替の各段で走らせて失敗の誤通知がなく、実失敗では実段階が届き、復旧待ちで止めた各回に通知が届くこと。
- API版/健康失敗ではfinishしないことと、旧web停止後はサイト全体が到達不能になり得ること。自動で旧版を起動しない。
- 公開ヘッダ、h2/h1.1、Alt-Svc、next_reset、ページGET、watch85%freeze、lock休止、実際のdisk追加量と手動整理手順。

UTC開始/終了・各段・失敗状態・通知・network/volume/image ID・disk/memoryを記録する。予行後にstaging schedule/unitを戻す。
本番・staging・実Slack・公開tag/pushはこの実装作業では実行しない。


### 修正2：checkout権限・image固定・復旧手順

予行（11.15）では、固定network/IP・証明書の引継ぎとDB世代化は実Dockerで成功したが、checkoutのmodeと同commitの再buildで失敗した。
以下はその2点を修正した手順であり、修正後の実Docker再予行は未実施。既存の11/2・11/9の予定には使わない。

checkoutのclone/checkoutだけumask 022にする。外側releaseは700、.envは600、runtimeのUID/GIDは10001を保持し、全体をchmodしない。
API build後、network none・UID 10001で必須moduleのimportと/app全ファイルの読取を検査する。読めなければ準備失敗で通常resetに戻る。

**同じcommitの再承認は許す。** buildは `dem-beta-{api,web}:candidate-<id>` の一意なtagを使い、稼働tagを付け替えない。
API/Webの完全image IDをroot専用registryとprepared記録へ保存し、検査・準備tools・切替後のapi/web/toolsは全てそのIDを直接参照する。
.envのDEM_BETA_API_IMAGE/DEM_BETA_WEB_IMAGEにIDを保存する（未設定の既存hostは従来のcommit tagを使う）。
切替前にIDの存在も再照合し、切替のapi/webは--force-recreateで必ず作り直す。criticalはtagの現在値でなく、準備記録のID・稼働コンテナのID・COMMIT/健康を照合する。
これで準備中の旧版backup/通常resetも稼働imageのまま実行でき、後から候補tagが変わっても選択imageは変わらない。
IDを持つ版でdem-beta upを呼ぶ場合はbuildをせず、保存IDから起動する。手動で別版をbuildする場合だけ、先に.envの旧API/WEB_IMAGE指定を外し、承認したCOMMITを設定する。
片付けのimage削除はcommit tagだけでなく候補tagも対象とする。退役idのregistryにあるIDとcandidate tagを確認し、現行/準備IDや他コンテナが使うimageは残す。
同じcommitでも別候補は別IDになり得る。削除の基準をcommit一致だけで決めず、使用中IDを照合し、docker image rmに-fを付けない。

**初回host更新のoneshot待機:** timerを止めても実行中のserviceは完了していないことがある。更新checkoutに入る前に、以下を実行する。

```bash
sudo systemctl stop dem-beta-reset.timer dem-beta-backup.timer dem-beta-watch.timer dem-beta-notify.timer
if sudo systemctl cat dem-beta-deploy-prepare.timer >/dev/null 2>&1; then
  sudo systemctl stop dem-beta-deploy-prepare.timer
fi
# 各serviceがactive/activating/deactivatingである間は既存処理を中断せず待つ。
for service in dem-beta-reset dem-beta-backup dem-beta-watch dem-beta-notify dem-beta-deploy-prepare; do
  if ! sudo systemctl cat "$service.service" >/dev/null 2>&1; then
    # 11.14からの初回導入ではprepare unitだけがまだ存在しない。
    [[ "$service" == dem-beta-deploy-prepare ]] && continue
    echo "Required service missing; inspect before host update" >&2; exit 1
  fi
  while :; do
    state=$(sudo systemctl show "$service.service" -p ActiveState --value) || exit 1
    case "$state" in
      active|activating|deactivating) sleep 2 ;;
      inactive) break ;;
      failed) echo "$service failed; inspect before host update" >&2; exit 1 ;;
      *) echo "Unknown service state; inspect before host update" >&2; exit 1 ;;
    esac
  done
done
```

待機後に上の「初回host道具の導入」のcheckout/install/unit/reloadを行い、元のtimerを戻す。これ自体はresetや稼働コンテナ再作成を行わない。

**切替後失敗の手動復旧:** 旧版へ自動では戻さない。DB/schema/baseとprepared.jsonのphase/tokenをrootローカルで確認し、
swapが完了して正しい候補DBを使っているstart/ready障害だけが、以下の再起動→検査→finishの対象となる。
prepare/swap障害や中断は先に既存DB復旧手順で状態を確定する。トークンや.env全体をログ/チャットへ貼らない。
11.15予行で確認した順序を、修正2以降では準備記録のimmutable IDを使って行う。

```bash
sudo bash <<'ROOT'
set -euo pipefail
active_repo=$(cat /var/lib/dem-beta/host-state/active-repo)
set -a
source "$active_repo/deploy/beta/.env"
set +a
registry="$DEM_BETA_HOME/host-state/deploy-candidates/$(basename "$(dirname "$active_repo")").json"
# IDとcommitだけを照合する。.envの他の値は出力しない。
python3 - "$registry" <<'PY'
import json, os, sys
record = json.load(open(sys.argv[1]))
assert record['commit'] == os.environ['DEM_BETA_COMMIT']
for service in ('api', 'web'):
    assert record['images'][service] == os.environ['DEM_BETA_' + service.upper() + '_IMAGE']
PY
dc=(docker compose --project-name dem-beta --env-file "$active_repo/deploy/beta/.env" -f "$active_repo/deploy/beta/compose.yml")
"${dc[@]}" up -d --no-deps --no-build --force-recreate --wait api web
api_id=$("${dc[@]}" ps -q api)
web_id=$("${dc[@]}" ps -q web)
[[ "$(docker inspect --format '{{.Image}}' "$api_id")" == "$DEM_BETA_API_IMAGE" ]]
[[ "$(docker inspect --format '{{.Image}}' "$web_id")" == "$DEM_BETA_WEB_IMAGE" ]]
docker exec "$api_id" python -c 'import os,sys; assert os.environ["DEM_BETA_COMMIT"] == sys.argv[1]' "$DEM_BETA_COMMIT"
printf 'Confirmed commit: %s\nAPI image: %s\nWeb image: %s\n' "$DEM_BETA_COMMIT" "$DEM_BETA_API_IMAGE" "$DEM_BETA_WEB_IMAGE"
# 上記の健康/版とDBの復旧確認後だけ。finishは既存のphase/tokenガードを使う。
"${dc[@]}" run --rm -T tools reset finish
rm -f -- "$DEM_BETA_HOME/status/reset-error.json"
rm -f -- "$DEM_BETA_HOME/host-state/deploy-switching.json"
curl --fail --silent --show-error "https://$DEM_BETA_DOMAIN/api/config"
ROOT
```

最後にread_only=false、write_state=open、last_reset_error=nullとnext_reset_atを確認し、freezeが残っていないことを確認する。
finish/検査の失敗時はそこで止め、印を手で外さない。SSHのbash -s/heredocではcompose runが後続入力を消費しないよう必ず-Tを付ける。
今回のwrapperと自動配備toolsもrun --rm -Tを使う。通常reset成功なら既存wrapperがreset-errorを消すが、失敗のまま次の定期回を待っても自動では消えない。

dem-beta_pgdataは世代移行後も復旧用に保持するため、Composeが「compose fileと一致しない/手動削除」というwarningを出すことがある。
予行で見られた想定内の旧volumeであり、warningだけを理由に消さない。上の片付け手順3で現行mount/backup/復旧不要を確認した24時間以内の整理対象となる。
Caddyの2volumeには適用せず、現在のDBvolumeなら当然削除しない。未知のvolume警告は名前を確認して止めて調査する。

**再予行:** 本番と旧stagingを使わず、承認済みの予行専用hostをレビュー側が使う。通知は実Slackでなくhost内loopback受信器（127.0.0.1:18080）へ送る。
受信器/外部からの観測/notifyの起動時刻、各段のUTC、tag/commit/tree、候補IDとimage ID、root checkout/env/runtimeのmode/所有者を記録する。
最初に稼働API/Web/DBとproxy/IP/証明書serial/ACME account/旧volumeを記録し、shimなし・wrapper umask077で再予行する。
UID10001読取probe→roles/base検証→切替が成功すること、同じcommitを2回続けて承認/配備できること、準備中も旧toolsのimage IDが変わらないことを必須とする。
候補tagの移動/削除でも記録IDから選択されること、IDそのものの消失では停止前に拒否すること、force-recreateとcriticalのID照合も記録する。
従来の拒否/中断/復旧待ち/誤通知なし、network/IP/証明書の不変、旧/候補コンテナ停止、OOM/応答停止の有無、memory/swap/diskも再確認する。
復旧場面は上の具体コマンドを-T付きで実行し、/api/configを記録する。
完了後はtimer・受信器・観測processを止め、使い捨て候補を片付け、秘密を記録しない。instance/静的IP/DNSの撤去は利用者/レビュー側の別作業とする。
この実装作業では予行host・staging・本番・AWS・DNS・実Slackを操作しない。
