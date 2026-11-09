# Lacre — contrato entre o motor (Python) e a interface (Tauri)

O **motor** (`engine/`, Python 3.12 + `pymobiledevice3==11.50.2`, congelado com PyInstaller em modo
`onedir`) é um processo de longa duração que fala **JSON Lines** em stdin/stdout. A **interface**
(`src-tauri/` Rust + `ui/` TypeScript) inicia o motor uma vez, envia pedidos e recebe respostas e eventos.
Nada de texto para humanos sai do motor: ele emite **códigos + parâmetros**; a interface traduz (pt-BR/en).

Regras invariáveis:
- **Somente leitura no iPhone.** O motor nunca chama serviço que grave no aparelho (instalar perfil,
  apagar, supervisionar, etc.). A única exceção é apagar o sysdiagnose que ele mesmo pediu (`erase`).
- stdout só carrega JSON Lines do protocolo (uma mensagem por linha, UTF-8). Logs vão para stderr.
- Toda mensagem tem `"v": 1`.

## Pedidos (interface → motor)

```json
{"v":1,"id":"<string única>","cmd":"<comando>","args":{...}}
```

| cmd | args | resposta (`data`) |
| --- | --- | --- |
| `hello` | `{}` | `{"engine_version":"x.y.z","pymobiledevice3":"11.50.2","platform":"win32"}` |
| `prereq` | `{}` | `{"usbmux_ok":bool,"hint":"apple_devices_missing"\|"usbmuxd_missing"\|null}` |
| `devices` | `{}` | `[{"udid":..,"name":..,"product_type":..,"ios":..,"connection":"USB"}]` (só USB) |
| `read` | `{"udid":..}` | `RawRead` (abaixo); emite eventos `progress` |
| `fdr` | `{"udid":..,"timeout_s":900}` | `RawFdr`; emite eventos `fdr` |
| `cancel` | `{"target_id":..}` | `{}` (cancela `fdr` em espera) |
| `analyze` | `{"raw":RawRead,"fdr":RawFdr\|null,"today":"YYYY-MM-DD"}` | `Analysis` (abaixo). Puro, sem aparelho. |
| `shutdown` | `{}` | `{}` e o processo sai |

## Respostas e eventos (motor → interface)

```json
{"v":1,"id":"<id do pedido>","ok":true,"data":{...}}
{"v":1,"id":"<id do pedido>","ok":false,"error":{"code":"<código>","detail":"<texto técnico curto>"}}
{"v":1,"id":"<id do pedido>","event":"progress","step":"identity|battery|hardware|parts|platform|mdm","done":3,"total":6}
{"v":1,"id":"<id do pedido>","event":"fdr","stage":"waiting_trigger|generating|downloading|extracting|cleaning|done"}
```

Códigos de erro: `no_device`, `not_trusted` (desbloquear e tocar em Confiar), `passcode_required`,
`usbmux_unavailable`, `device_gone`, `timeout`, `fdr_no_archive`, `fdr_missing_report`, `cancelled`,
`internal`.

## `RawRead` (dados brutos, o mesmo formato do `.json` do protótipo `conferir-iphone`)

`{"collected_at", "info" (lockdown all_values), "battery" (diagnostics battery), "classes":
{"camera":[...],"display":[...]}, "cameras":{classe:props}, "display":{classe:props}, "platform"
(IOPlatformExpertDevice), "cloud" (cloud configuration), "profiles" (profile list)}`. Valores binários
como `{"$hex":"..."}`.

## `RawFdr`

`{"has_fdr":bool, "fdr": <FDRDiagnosticReport.plist como JSON, bytes em hex>, "battery_health_percent": int|null,
"seal_date": str|null}`. O pacote sysdiagnose é baixado para pasta temporária, só
`logs/FDR/FDRDiagnosticReport.plist` e `logs/BatteryHealth/BatteryHealth.log` são lidos, e o pacote é
apagado no PC e no iPhone antes de responder.

## `Analysis`

```json
{
 "verdict": {"status":"ok|warn|alert","code":"<código de veredito>","params":{}},
 "device": {"model_name":..,"product_type":..,"ios":..,"name":..,"serial":..,"imei":[..],
            "model_number":..,"region":..,"assembly":"YYYY-MM"|null,"assembly_source":"serial|board"|null},
 "sections": [
   {"id":"purchase","items":[Item...]},
   {"id":"factory","items":[Item...],"seal_date":..,"verified_count":int,"failed_count":int}|null,
   {"id":"parts","items":[Item...]},
   {"id":"battery","items":[Item...]}
 ],
 "notices": [{"code":..,"params":{}}]
}
```

`Item = {"code":"<código>","status":"ok|warn|alert|na","params":{...}}`. `na` = não verificado.

### Códigos de item (a interface tem título e descrição para cada um, em pt-BR e en)

Compra (`purchase`):
- `findmy_on` (alert, `account_masked`) · `findmy_off` (ok) · `findmy_unknown` (warn)
- `mdm_supervised` (alert, `org`) · `mdm_cloud_config` (warn, `source`) · `mdm_none` (ok) · `mdm_unknown` (warn)
- `profiles_installed` (warn, `count`,`names`) · `profiles_none` (ok) · `profiles_unknown` (warn)
- `activation_state` (ok se `Activated`, senão warn; `state`)
- `origin_prefix` (`prefix`, `kind`: `new_retail`\|`apple_replacement`\|`apple_refurb`\|`engraved`\|`demo_or_thirdparty_refurb`\|`unknown`; ok para new_retail/engraved, warn no resto)

Fábrica (`factory`, só se houve FDR):
- `fdr_summary` (ok se 0 falhas, senão alert; `verified`,`failed`)
- `fdr_part_mismatch` (alert; `key`,`part`,`sealed`,`live`) — `part` é um de `battery`,`display`,`display_touch`,`display_panel`,`board`,`serial`,`imei`,`wifi`,`bluetooth`,`other`
- `fdr_unverified` (warn; `key`,`part`,`message`)
- `fdr_data_failed_to_report` (warn; `detail`) · `fdr_apticket` (warn; `value`)
- `fdr_not_available` (warn) — o sysdiagnose veio sem o registro

Peças (`parts`), com `part` = `camera_back`,`camera_ultrawide`,`camera_tele`,`camera_front`,`faceid_ir`,`faceid_projector`,`lidar`,`display_component`,`battery`, mais `index`/`count` em `display_component`:
- `part_date_ok` (ok; `part`,`serial`,`made`) · `part_date_late` (warn, 10–26 semanas depois; `weeks`) ·
  `part_date_much_later` (alert, >26 semanas; `months`) · `part_date_much_older` (warn; `months`)
- `part_no_serial` (na) · `part_undecodable` (na) · `part_no_anchor` (na; `made`)
- `cameras_unreadable` (warn) · `display_unreadable` (warn) · `display_no_dates` (warn)
- `faceid_pairing_ok` (ok) · `faceid_pairing_unexpected` (warn; `value`) · `touchid_not_checked` (na)

Bateria (`battery`):
- `battery_health_official` (ok ≥85, warn 80–84, alert <80; `percent`) — só com FDR
- `battery_health_estimate` (na; `nominal_pct`,`raw_pct`,`design_mah`)
- `battery_cycles` (na; `cycles`,`design_cycles`: 500 ou 1000)
- `battery_age_ok` (ok; `years_on`,`device_years`) · `battery_age_younger` (warn; idem)

Avisos (`notices`): `board_serial_date_gap` (`board`,`serial`) · `no_assembly_date` ·
`low_cycles_old_device` · `screenshot_left_in_photos` (sempre que houve FDR).

Veredito (`verdict.code`): `alert_items` · `factory_ok` · `factory_ok_with_warnings` ·
`incomplete` (`missing`: lista de `cameras`,`display`,`battery`) · `warnings` · `dates_ok`.
A lógica é a de `veredito()` em `conferir-iphone/conferir.py` (fonte de verdade das regras).

## Adições do motor (09/11/2026, só acréscimos; tudo acima continua valendo)

Campos extras (a interface pode ignorar o que não usar):
- `hello`: `"protocol": 1`.
- `devices`: cada item tem também `"error": null | <código de erro>` (ex.: `not_trusted` quando o lockdown
  recusou; nesse caso `name`/`product_type`/`ios` vêm `null`).
- `cancel`: responde `{"found": bool}` (`false` = o pedido já terminou ou não existe). O pedido cancelado
  responde `ok:false` com `cancelled`. Qualquer pedido em andamento pode ser cancelado, não só `fdr`.
- `analyze`: `today` é obrigatório (sem ele: erro `internal`). `fdr` que não seja objeto = `null`.
- Linha que não é JSON, `cmd` desconhecido ou `id` repetido em andamento: `ok:false`, `internal`
  (linha ilegível responde com `"id": null`).
- `RawFdr`: `"device_archive_removed": bool` (o motor confirmou que o pacote sumiu do iPhone).
  Pacote baixado sem o registro vira `has_fdr:false` (item `fdr_not_available`), não erro; o código
  `fdr_missing_report` fica reservado e hoje não é emitido. Cancelar depois que o iPhone começou a gerar
  o pacote agenda uma limpeza em segundo plano: espera o iPhone terminar (até 15 min) e apaga o pacote.
  Cancelar ainda em `waiting_trigger` não deixa nada (o iPhone ainda não gerou nada).
- `Analysis.device`: `"build"` (BuildVersion do iOS).
- Itens de data de peça (`part_date_*`, `part_undecodable`, `part_no_anchor`) levam sempre `part`,
  `serial`, `made` ("YYYY-MM"); `part_no_serial` leva `part`. `display_component` leva `index`/`count`.

Códigos e parâmetros novos:
- Peças: `part` = `camera_other` (módulo de câmera com nome desconhecido) com o parâmetro `module`
  (nome técnico, ex.: `BackMacroCameraModule`). Regra do protótipo: o nome cru aparecia na tabela.
- `fdr_summary`: `named_parts` (lista de `part` reconhecidos entre os verificados; o protótipo listava
  "Inclui: Bateria, Tela...").
- `origin_prefix`: `model_number` (o modelo de venda inteiro, ex.: `MHDH3`).
- `battery_health_estimate`: `nominal_mah`, `raw_mah` (o protótipo mostrava os mAh); `nominal_pct` ou
  `raw_pct` podem vir `null`.
- `faceid_pairing_ok`: `value` (o texto lido, ex.: `Valid`).
- `low_cycles_old_device`: `cycles`.
- Veredito: só os avisos `board_serial_date_gap`, `no_assembly_date` e `low_cycles_old_device` pesam como
  atenção; `screenshot_left_in_photos` é informativo e não impede `factory_ok`.
- `model_name` é nome próprio, igual nos dois idiomas (`iPhone SE (2nd generation)` /
  `iPhone SE (3rd generation)` para os SE).

## Testes manuais (só na interface)

Lista de itens com `id`, título, como testar e resultado `pass|fail|skip`, guardada no estado da sessão
e incluída na exportação. Ver `ui/src/checklist.ts`.
