import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const screenshotDir = resolve('../docs/screenshots')

test.describe('P1-1 real material ingest loop', () => {
  test.skip(process.env.RUN_E2E !== '1', 'requires Docker PostgreSQL, Redis, API, publisher and worker')

  test('operator creates, approves, observes and downloads a verified manifest', async ({ page }) => {
    mkdirSync(screenshotDir, { recursive: true })
    const title = `实验室设备管理系统-${Date.now()}`

    await page.goto('/tasks/new')
    await page.getByTestId('task-title').fill(title)
    await page.screenshot({ path: resolve(screenshotDir, '01-new-task.png'), fullPage: true })
    await page.getByRole('button', { name: '创建并提交启动审批' }).click()

    const approval = page.locator('article').filter({ hasText: title })
    await expect(approval).toBeVisible()
    await page.screenshot({ path: resolve(screenshotDir, '02-pending-approval.png'), fullPage: true })
    await approval.getByTestId('approve-task').click()
    await approval.getByRole('link', { name: '查看工作流' }).click()

    const ingestNode = page.getByTestId('node-material_ingest')
    await expect(ingestNode).toContainText('运行中', { timeout: 60_000 })
    await ingestNode.click()
    await page.screenshot({ path: resolve(screenshotDir, '03-ingest-running.png'), fullPage: true })

    await expect(ingestNode).toContainText('已完成', { timeout: 120_000 })
    await expect(page.getByTestId('node-project_fact_review')).toContainText('待审批')
    await page.screenshot({ path: resolve(screenshotDir, '04-ingest-succeeded.png'), fullPage: true })

    const taskNav = page.getByRole('navigation', { name: '任务区域导航' })
    await taskNav.getByRole('link', { name: '项目与材料' }).click()
    await expect(page.getByText('INGEST_MANIFEST', { exact: true })).toBeVisible()
    await page.screenshot({ path: resolve(screenshotDir, '05-material-artifacts.png'), fullPage: true })

    const manifestRow = page.getByRole('row').filter({ hasText: 'INGEST_MANIFEST' })
    const downloadPromise = page.waitForEvent('download')
    await manifestRow.getByRole('link', { name: '下载' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('ingest-manifest.json')

    await page.reload()
    await expect(page.getByText('INGEST_MANIFEST', { exact: true })).toBeVisible()
    await page.goto('/system/workers')
    await expect(page.getByText('PostgreSQL')).toBeVisible()
    await expect(page.getByText('Redis')).toBeVisible()
    await page.screenshot({ path: resolve(screenshotDir, '06-system-workers.png'), fullPage: true })
  })
})
