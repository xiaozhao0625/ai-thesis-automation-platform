# UI/UX v1.2.4-P0-r3 复审候选

这是 ProjectFact r2 专项复审后仅修四项 P0 的受控候选，不是已冻结的 v1.2.4。页面通过本地 API 消费 `../project-fact-p0-r3/` 从冻结夹具生成的事实、启动确认、冲突、依赖传播和版本快照数据。

## r3 范围

- 启动闸门先展示 `PROPOSED` 项目事实；只有 `POST /api/project-facts/confirm-intake` 成功后才展示锁定版本与 ACTIVE Snapshot。
- 启动确认 API 返回 ProjectFactVersion、Snapshot Hash、HumanApproval 和审计事件；前端不再自行写入锁定状态。
- 当前 Snapshot 中全部硬件与模块型号均参与机器一致性检查，包含 STM32F103C8T6、DHT11、ESP8266-01S 和 SSD1306。
- 检索分类在 Schema 与运行时共同校验证据角色、支持布尔值和别名范围。
- 冲突、依赖 BFS、失效传播、新目录 READY 与所有既有 DAG/导航能力保持不变。
- 不新增页面，不扩展其他功能。

`68c5c50` 与 `91e1b51` 继续作为失败候选追溯点，不修改、不冻结、不推送。

## 本地预览

```powershell
node prototype.server.cjs
```

访问 `http://127.0.0.1:4173/tasks/task-001/new-task`。预览服务提供 SPA 深链接回退，以及启动确认、冲突、影响分析与冲突确认 API。

## 本地验证

```powershell
Push-Location ..\project-fact-p0-r3
python -m unittest discover -s tests -v
Pop-Location

node prototype.contract.test.mjs

$env:NODE_PATH=Join-Path (Join-Path $env:TEMP 'codex-playwright-check') 'node_modules'
node --test prototype.interaction.test.cjs
```
