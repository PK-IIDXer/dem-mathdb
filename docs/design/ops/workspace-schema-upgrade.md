# Workspace schema upgrade 配備手順

既存 workspace は API を停止した状態でだけ更新する。online migration は行わない。

## 事前確認

1. workspace filesystem に、最大 workspace の約 2〜3 個分の空き容量があることを確認する。
2. `DEM_MANAGEMENT_DATABASE_URL` を本番の管理 DB に向ける。
3. 管理 DB が PostgreSQL 等で、全 worker が同じ local path を共有しない構成なら、
   `DEM_WORKSPACE_DEPLOYMENT_LOCK_PATH` を全 API process と更新コマンドで同じ共有 path にする。
   既定の lock file は、管理 DB が SQLite ならその隣、それ以外ならリポジトリ直下の `build/` に置く
   (起動時の作業ディレクトリには依存しない)。
   lock は API が共有、更新コマンドが排他で取る。POSIX は `fcntl.flock`、Windows は `LockFileEx`
   (`msvcrt.locking` には共有モードが無く、2 つ目の API process が起動できなくなるため使わない)。
   管理 DB を使わない単一 DB モードの API は workspace を持たないので lock を取らない。
4. 現行コードで template を再生成する。

```powershell
.\.venv\Scripts\python.exe scripts\build_workspace_template.py build\template.db
```

## 配備順

1. load balancer から API を外し、全 API process を停止する。process が残っていれば更新は
   `busy` で終了し、workspace には触れない。
2. dry-run する。head の workspace は管理行だけを `ready` へ収束できる。未知 schema、
   `quick_check` 失敗、不完全な式は `upgrade_blocked` として記録される。

```powershell
.\.venv\Scripts\python.exe scripts\upgrade_workspace_schemas.py --dry-run
```

3. dry-run が認識した対象を更新する。特定 workspace だけなら `--workspace-id UUID` を付ける。

```powershell
.\.venv\Scripts\python.exe scripts\upgrade_workspace_schemas.py
```

4. 終了 code が 0 で、全行が `ready`、embedded revision が head であることを確認する。
   `upgrade_blocked` が 1 件でもあれば API を公開しない。`schema_error` の JSON に安定 error code、
   該当する場合は formula ID が入る。
5. API を起動する。起動時に template の fingerprint / `quick_check` / embedded head を検査する。
   request の workspace は管理状態と embedded head を照合し、cache admission 時に一度だけ
   `INCOMPLETE_FORMULAS_SQL` を実行する。失敗時は 503 で、engine cache には入らない。

## Backup と再実行

backup は workspace directory の `.schema-backups/<workspace-id>.db` に直前 1 世代を保持する。
更新中は `.pending.db` と workspace sibling の shadow が加わる。更新失敗時は原本 bytes を
変更せず、pending backup を調査・復元に使える。再実行は残留 shadow の schema を読んでから
回収する。publish 後、管理行更新前に process が落ちても、次の dry-run は原本の embedded head
を正本として migration を再適用せず、管理行と backup だけを収束させる。
