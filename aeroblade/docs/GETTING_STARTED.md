# 克隆、服务管理、令牌与参数批量导入

本页适用于完整 Git 仓库。除特别标明外，命令均在 **Linux / WSL 的 Bash** 中、仓库根目录执行。便携 ZIP 用户将 `bash scripts/start.sh` 替换为 `bash bridge/start-local.sh`，并去掉示例路径中的 `aeroblade/`。

## 1. 克隆到本地

Windows 用户先在 PowerShell 执行 `wsl -d Ubuntu-24.04`，再在 WSL 中执行：

```bash
# 替换为项目实际 GitHub 地址；仓库尚未配置固定远程地址
git clone <你的GitHub仓库URL> BladeDesign
cd BladeDesign
```

建议克隆到 WSL 的 Linux 文件系统（例如 `~/projects/BladeDesign`）；也可在 `/mnt/e/...` 下运行。后续启动、停止与读取令牌应使用同一个 Linux 用户。Git 不包含历史 jobs、runtime 日志和私有令牌，新电脑需重新计算。

要求：Git、Python 3.10+、Node.js 20+、OpenCFD OpenFOAM。现有真实验证使用 **v2512**，不表示兼容所有 OpenFOAM 分支。前后端无需 `npm install` 或 `pip install`。

```bash
source /usr/lib/openfoam/openfoam2512/etc/bashrc
python3 --version
node --version
command -v blockMesh snappyHexMesh extrudeMesh createPatch checkMesh rhoSimpleFoam foamToVTK
```

安装路径不同，请设置 `FOAM_BASHRC` 指向实际文件。启动脚本会尝试寻找当前用户 NVM 下的 Node；系统安装 Node 也可使用。

## 2. 启动、停止与重启

### 前台启动（首次使用推荐）

```bash
# templates/pritchard-cascade-2d 已存在时跳过生成
test -f aeroblade/templates/pritchard-cascade-2d/aeroblade-template.json || \
  python3 aeroblade/bridge/create_pritchard_cascade.py
bash scripts/start.sh --max-parallel 2 --max-pending 16 --case-threads 1
```

仅一个逻辑 CPU 时将 `--max-parallel` 改为 `1`。不同 OpenFOAM 安装位置：

```bash
FOAM_BASHRC=/实际路径/etc/bashrc bash scripts/start.sh
```

浏览器打开 [本地工作台](http://127.0.0.1:8787/)，切换“CFD 仿真”，服务地址填 `http://127.0.0.1:8787`，填入下一节的令牌后连接。页面和 API 由同一个服务提供。

- **停止服务**：在运行服务的终端按 `Ctrl+C`，等待清理结束、终端提示符返回。
- **重启服务**：先停止，再执行相同启动命令。不要重复启动占用同一端口的进程。
- **只停止一个算例**：网页选中任务后点击“停止任务”；其他任务继续运行。
- 关闭网页或点击“断开连接”不会停止计算。停止服务会取消其未完成任务；异常退出后重启会将遗留未完成任务标记为中断，不会自动续算。
- 历史记录和结果保存在 `aeroblade/jobs/`；停止服务不删除它们。并发设置在网页调整后仅对当前进程生效，重启以命令行配置为准。

### 保持终端会话运行（可选 tmux）

已安装 tmux 时，可在仓库根目录执行：

```bash
tmux new -s aeroblade
bash scripts/start.sh --max-parallel 2 --max-pending 16
```

按 `Ctrl+B`，松开后按 `D` 分离会话。之后用 `tmux attach -t aeroblade` 回到会话，按 `Ctrl+C` 停止服务，再用 `exit` 退出该 shell。不要用结束整个 tmux 服务的方式停止其他人的会话。WSL 关闭或系统重启仍会结束进程；当前项目没有安装开机自启动服务。

若旧服务的终端已丢失，先定位监听进程：

```bash
ss -ltnp 'sport = :8787'
# 将下面的 12345 替换为已查到的 PID，检查确实属于本项目
ps -p 12345 -o pid,user,args
readlink -f /proc/12345/cwd
# 确认后发送正常停止信号
kill -TERM 12345
```

确认端口释放后再启动；不要用 `pkill python` 或 `kill -9` 作为常规停止方式。

## 3. 本地和远程 API token

**这是 AeroBlade 桥接服务的访问令牌，不是 OpenFOAM 官方账号、许可证或 SSH 密码。** OpenFOAM 本身没有本平台的 API token。

### 本地自动生成的令牌

第一次使用启动脚本时，如果没有设置 `AEROBLADE_API_TOKEN`，脚本自动创建并复用私有令牌文件。在启动服务的 **同一 WSL/Linux 用户** 的另一个终端读取：

```bash
cat "${XDG_STATE_HOME:-$HOME/.local/state}/aeroblade/api-token"
```

默认路径为 `~/.local/state/aeroblade/api-token`。复制内容到网页令牌输入框；不要连同换行、引号或 `Bearer ` 前缀一起粘贴。令牌无需提交到 Git、截图或发送到聊天中。

- 文件不存在：先用启动脚本启动一次；核对 Linux 用户及 `XDG_STATE_HOME`。
- 设置过 `AEROBLADE_API_TOKEN`：服务优先使用该环境变量，不读取/更新上述文件。应使用部署者配置的值，不能假设文件内容就是当前令牌。
- 直接运行 `python3 bridge/server.py`：不会自动生成令牌，需自行注入至少 24 个字符的随机 `AEROBLADE_API_TOKEN`。
- 更换令牌后必须重启服务，网页重新连接；重启前先处理正在执行的任务。

### 远程求解机

在远程 Linux 上克隆本仓库、安装依赖，并执行同样的启动命令。另开 SSH 终端登录远程主机，使用 **运行桥接服务的账号** 执行：

```bash
cat "${XDG_STATE_HOME:-$HOME/.local/state}/aeroblade/api-token"
```

如果由管理员通过 systemd、容器或环境变量配置令牌，请由管理员提供访问凭据；本地电脑的令牌不一定能访问远程服务。无权读取其他用户令牌时不要绕过文件权限。

推荐先用 SSH 隧道连接。下面命令在自己的电脑执行，并保持运行：

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8787:127.0.0.1:8787 your-user@your-compute-host
```

浏览器仍打开 `http://127.0.0.1:8787/`，API 地址填同一地址，令牌填写 **远程服务** 的令牌。此时网页和计算均由远程主机提供，本地无需安装 OpenFOAM。按 `Ctrl+C` 只关闭隧道，不会停止远程计算。

若本地 8787 已占用，可改用 `-L 8788:127.0.0.1:8787`，浏览器和 API 地址都改为 `http://127.0.0.1:8788`。远程服务启动前需加入这个网页源：

```bash
export AEROBLADE_ALLOWED_ORIGINS='http://127.0.0.1:8788,http://localhost:8788'
bash scripts/start.sh
```

长期远程访问可由管理员配置有效证书的 HTTPS 反向代理。将外部网页源加入 `AEROBLADE_ALLOWED_ORIGINS`（协议、主机和端口精确匹配，多个用逗号分隔），代理保留 Authorization 并转发 OPTIONS。API 地址填写 HTTPS 根地址，不是 SSH 地址，也不要附加 `/api`。默认 HTTP 监听保持在 `127.0.0.1`；不要为解决连接问题直接暴露公网或关闭认证。

## 4. 导入单份设计参数

在“叶片设计”中导出“参数文件 JSON”，修改后通过“导入”载入。当前页面 **一次导入一个 JSON**，不支持一次选择多文件、JSON 数组、Excel 或 CSV 参数表。截面 CSV 是坐标导出文件，不是设计参数输入格式；STL 也不能反推出十一参数。

Pritchard 设计文件示例：

```json
{
  "schema": "aeroblade-pritchard-v1",
  "units": {"length": "mm", "angle": "deg"},
  "parameters": {
    "model": "pritchard-1985",
    "radius": 139.7,
    "bladeCount": 51,
    "axialChord": 27.9908,
    "tangentialChord": 15.0114,
    "throat": 8.560982297224456,
    "leadingRadius": 0.7874,
    "trailingRadius": 0.4064,
    "inletAngle": 35,
    "outletAngle": -57,
    "inletHalfWedge": 9,
    "unguidedTurning": 6.5,
    "height": 60
  }
}
```

长度单位 mm，角度 deg，bladeCount 为整数；height 为附加拉伸高度，不属于 Pritchard 十一参数。保留完整字段，文件不超过 100000 字节。旧设计格式为 `aeroblade-v1`，不能仅改 schema 就转成 Pritchard。

导入后检查截面与三维形状，再选择匹配的 CFD 模板。单个参数在范围内仍可能组成无效几何，平台会检查组合约束。导入自定义设计后不要再点击“应用模板推荐叶片”，否则会替换当前设计。

## 5. 批量参数与多 case 提交

目前的批量途径是 **为每份设计构建请求，逐个调用 API，服务器按计算槽位并行运行**；网页尚无参数表批量导入界面。批量提交不会把所有设计同时载入设计面板。

1. 准备多份上节格式的设计 JSON，放入 `aeroblade/runtime/batch/designs/`，一文件一设计。
2. 网页连接服务，选择匹配模板并设定工况，导出“请求 JSON”，保存为 `aeroblade/runtime/batch/base-request.json`。该文件 schema 是 `aeroblade-cfd-v1`，必须包含有效 template_id 和 conditions；未连接服务导出的空模板请求不能求解。
3. 下例使用同一套工况、逐份替换 parameters，以文件名命名任务。若需要不同工况，可另外准备各自的请求。每次提交都是独立网格与求解，不是对已有场简单更换标签。

先创建目录，再放入上述文件：

```bash
mkdir -p aeroblade/runtime/batch/designs
```

将下面代码保存为 `aeroblade/runtime/batch/submit.py`。它先检查全部文件格式，再逐个提交，记录已接受的任务 ID；队列满时退出，稍后可重新执行跳过已记录文件。网络错误不会自动重发，避免产生重复计算。

```python
import copy
import getpass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

root = Path(__file__).resolve().parent
base = json.loads((root / "base-request.json").read_text(encoding="utf-8-sig"))
if base.get("schema") != "aeroblade-cfd-v1" or not base.get("template_id") or not base.get("conditions"):
    raise SystemExit("请先导出已选择模板和工况的请求 JSON")
files = sorted((root / "designs").glob("*.json"))
if not files:
    raise SystemExit("designs 目录没有 JSON 文件")
requests = []
for file in files:
    d = json.loads(file.read_text(encoding="utf-8-sig"))
    if d.get("schema") != "aeroblade-pritchard-v1" or d.get("units") != {"length": "mm", "angle": "deg"}:
        raise SystemExit(f"{file.name}: 本示例仅接收 mm/deg 的 Pritchard 设计")
    if d.get("parameters", {}).get("model") != "pritchard-1985":
        raise SystemExit(f"{file.name}: 模型不匹配")
    payload = copy.deepcopy(base)
    payload.update(parameters=d["parameters"], geometry_model="pritchard-1985",
                   name=file.stem[:80], design_units="mm", geometry_export_units="m")
    requests.append((file.name, payload))

journal = root / "submitted.jsonl"
done = {json.loads(line)["file"] for line in journal.read_text(encoding="utf-8").splitlines()} if journal.exists() else set()
url = os.environ.get("AEROBLADE_URL", "http://127.0.0.1:8787").rstrip("/")
token = getpass.getpass("输入目标桥接服务令牌（不回显）: ").strip()
for name, payload in requests:
    if name in done:
        print("跳过已记录文件:", name)
        continue
    request = urllib.request.Request(
        url + "/api/jobs",
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            job = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{name}: HTTP {error.code}，停止提交；检查服务日志/队列后处理")
    except (urllib.error.URLError, TimeoutError):
        raise SystemExit(f"{name}: 响应未确认，先在网页按名称核对是否已创建任务，再决定是否重试")
    with journal.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"file": name, "id": job["id"]}, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())
    print(name, job["id"], job["status"])
```

运行：

```bash
python3 aeroblade/runtime/batch/submit.py
# 其他服务地址（令牌仍通过不回显输入提供）
AEROBLADE_URL=https://your-compute.example \
  python3 aeroblade/runtime/batch/submit.py
```

该示例不执行完整几何预检；服务在接收/准备阶段继续校验参数、模板及实际几何。已提交不等于已完成或已收敛，后续在网页任务列表查看每个任务。

`submitted.jsonl` 按文件名跳过已记录项，因此不要改动已提交文件后沿用同名再次运行；新一轮使用新目录或新文件名。HTTP 429 表示队列容量已满，该请求未被接受；等待空位后重跑。连接中断、服务端错误或写入记录前退出时，服务可能已经接受请求，必须先核对任务列表；API 没有幂等键，不能盲目重发。此示例不支持多个提交脚本同时写同一记录文件。

从 Excel/CSV 批量生成时，应先将每一行转换为上述 JSON：列名使用 parameters 中的英文键，单元格为数值，不带“mm/°”等单位字符串，固定添加 model/schema/units。建议从网页导出的有效设计复制，先小批量验证。具体参数定义见 [Pritchard 模型说明](PRITCHARD.md)，并行限制见 [多算例并行计算](PARALLEL_CASES.md)。

## 6. 连接和运行排错

| 现象 | 检查与处理 |
|---|---|
| 网页无法打开 / connection refused | 确认服务终端仍在运行，查看启动错误与 8787 监听；Windows 检查 WSL 是否正常运行。 |
| “无法访问服务，请检查 HTTPS、允许的网页来源和网络连接” | 这是浏览器请求失败的通用提示，不能仅据此判断 CORS。依次检查服务、端口/隧道、代理、地址协议、证书及允许来源。 |
| HTTP 401 | 核对目标服务实际使用的令牌，尤其是本地/远程和环境变量覆盖。 |
| HTTP 403 / Origin is not allowed | 在服务端加入实际网页源并重启；localhost 与 127.0.0.1、不同端口是不同源。 |
| HTTP 502 | 检查反向代理能否访问上游；本地请求检查代理是否错误接管 loopback。不能当作 token 错误处理。 |
| ready: false | 查看缺失命令、模板错误；确认已加载正确 OpenFOAM 环境和可用 Node。 |
| Address already in use | 已有进程占用端口，确认身份后使用原服务或正常停止，不要重复启动。 |
| HTTP 429 | 运行加排队达到容量；等任务结束后再提交。 |
| 网格失败 / 几何无效 | 查看所选任务日志，检查参数组合与模板，不要把所有范围内参数组合当成可求解几何。 |

检查主页连接（不验证认证与 OpenFOAM 就绪）：

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8787/
```

返回 200 说明主页可达；完整就绪状态仍以网页“连接并检测”或带 Bearer 认证的 `GET /api/health` 为准。Windows PowerShell 使用 `curl.exe`，避免旧版 PowerShell 的同名别名。服务日志可能显示环境健康摘要，但不会打印 API token。
