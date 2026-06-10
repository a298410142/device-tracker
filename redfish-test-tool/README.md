# Redfish Test Tool — BMC Redfish API 自動化測試工具

在 Windows 上執行的 BMC(Baseboard Management Controller)Redfish API 自動化測試工具。
透過標準 Redfish API 對伺服器 BMC 進行功能驗證,即時顯示 PASS/FAIL,並產出 HTML 測試報告。

支援 Dell iDRAC、HPE iLO、OpenBMC 等實作:工具不寫死任何廠商路徑,
而是從 `/redfish/v1/` Service Root 順著 `@odata.id` 連結自動探索資源。

## 功能特色

- **四大測試套件**:基本資訊查詢、感測器與健康狀態、電源控制、帳號/Session/SEL
- **HTML 測試報告**(繁中/英文)+ JSON 結果檔 + HTTP trace log(自動遮蔽密碼/token)
- **安全閘門**:會改變機器狀態的測試(開關機、清除 SEL)必須明確加旗標才會執行
- **Session 認證**:預設使用 Redfish Session(X-Auth-Token),結束必定登出,不留殘留 session
- **可打包成單一 `redfish-test.exe`**,免安裝 Python 即可在測試站使用
- Exit code 支援 CI 整合:`0` 全過 / `1` 有失敗 / `2` 設定或連線錯誤

## 安裝

### 方式一:Python 環境執行(開發/除錯)

需要 Python 3.9+:

```bat
cd redfish-test-tool
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m redfish_test_tool version
```

### 方式二:打包成 Windows 執行檔

在 Windows 上執行一鍵打包(PyInstaller 不支援跨平台編譯):

```bat
build_exe.bat
```

完成後輸出 `dist\redfish-test.exe`,單檔即可帶到測試站使用。

## 快速開始

```bat
:: 1. 先探索 BMC 資源樹,確認連線與相容性
redfish-test discover -H 192.168.0.120 -u admin

:: 2. 執行非破壞性套件(basic + sensors + accounts)
redfish-test run -H 192.168.0.120 -u admin

:: 3. 確認無誤後,在「允許開關機的測試機」上跑完整測試
redfish-test run -H 192.168.0.120 -u admin --suites all --include-power-tests
```

密碼建議不要打在指令列上(會留在歷史紀錄),三種較安全的方式:

```bat
:: 互動式輸入(不加 -p 即自動提示)
redfish-test run -H 192.168.0.120 -u admin

:: 環境變數
set REDFISH_PASSWORD=yourpassword
redfish-test run -H 192.168.0.120 -u admin

:: 設定檔
redfish-test run -c config.yaml
```

設定檔格式請參考 [`config.example.yaml`](config.example.yaml),CLI 參數優先於設定檔。

## 測試套件與案例

用 `redfish-test list-suites` 可隨時列出完整清單。

### basic — 基本資訊查詢

| 編號 | 內容 |
|------|------|
| BI-01 | Service Root 可連線,含 RedfishVersion 與 Systems/Chassis/Managers 連結 |
| BI-02 | Systems collection 至少一個成員且可解析 |
| BI-03 | System 必要屬性:Manufacturer / Model / SerialNumber / PowerState / Status |
| BI-04 | BiosVersion 存在且非空 |
| BI-05 | Chassis 識別屬性(Model/SerialNumber 缺漏列為提示不算失敗) |
| BI-06 | Manager(BMC)FirmwareVersion 與 Health 可讀 |
| BI-07 | OData 合理性:@odata.id 與請求 URI 一致、@odata.type/Id/Name 存在 |
| BI-08 | 負向測試:不存在的資源回 404 |

### sensors — 感測器與健康狀態

| 編號 | 內容 |
|------|------|
| SH-01 | 傳統 Thermal:溫度讀值存在且在 Critical 閾值內 |
| SH-02 | 傳統 Thermal:風扇轉速 > 0 且健康 |
| SH-03 | 傳統 Power:電壓在 Critical 閾值內 |
| SH-04 | 傳統 Power:啟用中的 PSU 健康(回報輸入瓦數) |
| SH-05 | 新式 ThermalSubsystem 風扇(無此資源則 SKIP) |
| SH-06 | 新式 PowerSubsystem 電源供應器(無此資源則 SKIP) |
| SH-07 | Sensors collection 讀值型別合理、無 Critical |
| SH-08 | Chassis/Manager 各元件 Health 為 OK/Warning |
| SH-09 | System HealthRollup 為 OK/Warning |

### power — 電源控制(⚠ 需 `--include-power-tests`)

**警告:此套件會實際開關受測機器,請只在允許斷電的測試機上執行。**
工具會記錄初始電源狀態,測試結束(或中途失敗)時盡力還原;任一轉換失敗即中止後續電源測試。

| 編號 | 內容 |
|------|------|
| PC-01 | Reset action 探索 + AllowableValues |
| PC-02 | 記錄初始狀態;若為 Off 先開機 |
| PC-03 | GracefulShutdown → 輪詢至 Off(與 OS 設定相關) |
| PC-04 | On → 輪詢至 On |
| PC-05 | ForceOff → 輪詢至 Off |
| PC-06 | On(還原)→ 輪詢至 On,等待 `--boot-wait` 秒 |
| PC-07 | ForceRestart 被接受,狀態回到 On |
| PC-08 | GracefulRestart 被接受,狀態回到 On(不支援則 SKIP) |
| PC-09 | 負向測試:無效 ResetType 回 4xx |
| PC-10 | 還原並驗證初始電源狀態 |

### accounts — 帳號 / Session / SEL

測試用 session 與帳號(`rf_test_user`)皆為次要物件,與工具自身連線分離,
無論成功失敗都會在 teardown 清除。

| 編號 | 內容 |
|------|------|
| AS-01 | 建立 Session 取得 X-Auth-Token 與 Location |
| AS-02 | 僅憑新 token 可存取受保護資源 |
| AS-03 | 刪除 Session 後 token 失效(401) |
| AS-04 | 負向測試:錯誤密碼回 401 且不發 token |
| AS-05 | 帳號列舉(UserName/RoleId/Enabled) |
| AS-06 | 建立測試帳號(支援 Dell 式 PATCH 空 slot 後備) |
| AS-07 | 測試帳號可登入 |
| AS-08 | 刪除測試帳號並確認消失 |
| AS-09 | SEL 讀取:LogServices 探索、Entries 欄位驗證 |
| AS-10 | SEL ClearLog(⚠ 需 `--include-destructive`,會清除事件記錄) |

## 指令參考

```
redfish-test run         執行測試
redfish-test discover    傾印探索到的資源樹(JSON),用於除錯廠商差異
redfish-test list-suites 列出所有套件與測試案例
redfish-test version     顯示版本
```

`run` 常用參數:

| 參數 | 說明 |
|------|------|
| `-H, --host` / `--port` | BMC IP 與連接埠(預設 443) |
| `-u, --username` / `-p, --password` | 帳號密碼(密碼建議用環境變數或互動輸入) |
| `-c, --config` | YAML/JSON 設定檔 |
| `--suites basic,sensors,power,accounts` | 選擇套件;`all` 為全部(預設不含 power) |
| `--tests BI-01,SH-03` | 只跑指定編號 |
| `--include-power-tests` | 允許電源測試實際執行 |
| `--include-destructive` | 允許破壞性測試(SEL ClearLog) |
| `--power-timeout` / `--boot-wait` | 電源轉換逾時(300s)/ 開機後等待(60s) |
| `--auth session\|basic` | 認證模式(預設 session) |
| `--verify-ssl` | 啟用 TLS 憑證驗證(預設關閉,BMC 多為自簽) |
| `--system-id <Id>` | 多 System 機型時指定受測 System |
| `--output-dir` / `--lang zh-TW\|en` | 報告目錄與語言 |
| `-v, --verbose` | HTTP trace 同步輸出到主控台 |

每次執行會在輸出目錄建立時間戳記資料夾:

```
reports/20260610-153000/
├── report.html      ← 測試報告(自包含單檔,可直接寄出)
├── results.json     ← 機器可讀結果(CI 整合用)
└── http_trace.log   ← 全部 HTTP 往來記錄(密碼/token 已遮蔽)
```

## 無硬體驗證(模擬環境)

開發或驗收本工具時不需要實體 BMC:

1. **單元測試**(本 repo 內建,模擬含電源狀態轉換的 BMC):

   ```bat
   pip install -r requirements-dev.txt
   pytest
   ```

2. **DMTF Redfish-Mockup-Server**(靜態資源樹,適合驗證 basic/sensors):

   ```bat
   git clone https://github.com/DMTF/Redfish-Mockup-Server
   git clone https://github.com/DMTF/Redfish-Mockup-Data
   python Redfish-Mockup-Server/redfishMockupServer.py -D Redfish-Mockup-Data/public-rackmount1 -p 8443 --ssl
   redfish-test run -H localhost --port 8443 -u root -p pass --suites basic,sensors
   ```

   注意:Mockup Server 只回應 GET,session/電源相關測試會失敗或略過。

3. **DMTF Redfish Interface Emulator**(有狀態,可測 power/accounts):
   <https://github.com/DMTF/Redfish-Interface-Emulator>

## 首次實機測試建議流程

1. `discover` 確認資源樹探索正常
2. 只跑 `--suites basic`
3. 加入 `sensors`、`accounts`
4. 最後才在**允許斷電的測試機**上加 `--include-power-tests`

## 專案結構

```
redfish_test_tool/
├── cli.py          指令列入口與流程編排
├── config.py       設定合併(CLI > 設定檔 > 預設值)
├── client.py       Redfish HTTP client(session 認證、trace、重試)
├── discovery.py    資源探索(廠商中立的連結走訪)
├── runner.py       測試模型與循序執行器
├── suites/         四大測試套件
├── reporting/      主控台 / JSON / HTML(Jinja2)報告
└── utils/          輪詢、敏感資訊遮蔽
```
