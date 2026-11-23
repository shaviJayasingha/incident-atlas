import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'

const baseUrl = process.env.INCIDENT_ATLAS_WEB_URL ?? 'http://127.0.0.1:5173'
const screenshotDir = process.env.SCREENSHOT_DIR
if (screenshotDir) await mkdir(screenshotDir, { recursive: true })
const capture = async (page, name) => {
  if (screenshotDir) {
    await page.screenshot({ path: path.join(screenshotDir, name), fullPage: true, animations: 'disabled' })
  }
}
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
})
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  await page.goto(baseUrl)
  await page.getByRole('heading', { name: /Follow the evidence/ }).waitFor()
  await capture(page, '01-dashboard-desktop.png')
  await page.getByRole('link', { name: /Explore incidents/ }).click()
  await page.getByRole('heading', { name: 'Choose an incident' }).waitFor()
  await page.getByRole('link', { name: /Catalog latency after cache key change/ }).click()
  await page.getByRole('heading', { name: 'Incident timeline' }).waitFor()
  await page.getByRole('heading', { name: 'Telemetry explorer' }).waitFor()
  await capture(page, '02-incident-detail-desktop.png')
  await page.getByRole('button', { name: 'View stored replay' }).click()
  await page.getByText('PROVENANCE · STORED REPLAY').waitFor()
  assert.equal(await page.locator('.report-banner-stamp strong').innerText(), 'NO')
  await capture(page, '03-stored-replay-desktop.png')
const desktopCitations = await page.locator('.evidence-link').evaluateAll(links => links.map(link => ({ href: link.href, id: link.querySelector('b')?.textContent })))
assert.ok(desktopCitations.length > 0, 'the replay should include linked evidence')
for (const citation of desktopCitations) {
  await page.goto(citation.href)
  await page.getByText(citation.id, { exact: true }).last().waitFor()
}
await page.goto(`${baseUrl.replace(/\/$/, '')}/investigations/replay-cache-v1?source=stored_replay`)
await page.getByText('PROVENANCE · STORED REPLAY').waitFor()
  await page.getByRole('button', { name: /Review simulated mitigation/ }).click()
  await page.getByRole('heading', { name: 'Review proposed mitigation' }).waitFor()
  await page.getByRole('button', { name: 'Approve simulated mitigation' }).click()
  await page.getByLabel(/I understand this is a simulation/).check()
  await page.getByRole('button', { name: /Confirm simulation/ }).click()
  const approvalResult = page.locator('.approval-success').filter({ hasText: 'simulation_only=true' }).last()
  await approvalResult.locator('.eyebrow').filter({ hasText: 'SIMULATION RECORDED' }).waitFor()
  await approvalResult.getByText(/simulation_only=true/).first().waitFor()
  await approvalResult.getByText(/external_action_performed=false/).first().waitFor()
  await capture(page, '04-simulated-approval-desktop.png')
await page.reload()
await page.locator('.approval-success').getByText(/simulation_only=true/).waitFor()
await page.locator('.approval-success').getByText(/external_action_performed=false/).waitFor()

// A separate browser context shares the API client IP but gets a different
// anonymous visitor ID, so NAT-shared guests can record their own simulation.
const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 } })
const mobilePage = await mobileContext.newPage()
const mobilePageErrors = []
mobilePage.on('pageerror', error => mobilePageErrors.push(error.message))
const assertMobileFits = async () => {
  const overflow = await mobilePage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  assert.equal(overflow, 0, 'mobile page should not overflow horizontally')
}
  await mobilePage.goto(baseUrl)
  await mobilePage.getByRole('heading', { name: /Follow the evidence/ }).waitFor()
  await capture(mobilePage, '05-dashboard-mobile.png')
await assertMobileFits()
  await mobilePage.getByRole('link', { name: /Explore incidents/ }).focus()
  assert.equal(await mobilePage.evaluate(() => document.activeElement?.textContent?.includes('Explore incidents')), true)
await mobilePage.getByRole('link', { name: /Explore incidents/ }).click()
await mobilePage.getByRole('link', { name: /Catalog latency after cache key change/ }).click()
await mobilePage.getByRole('heading', { name: 'Incident timeline' }).waitFor()
await assertMobileFits()
await mobilePage.getByRole('button', { name: 'View stored replay' }).click()
await mobilePage.getByText('PROVENANCE · STORED REPLAY').waitFor()
await assertMobileFits()
const mobileCitations = await mobilePage.locator('.evidence-link').evaluateAll(links => links.map(link => ({ href: link.href, id: link.querySelector('b')?.textContent })))
assert.ok(mobileCitations.length > 0)
for (const citation of mobileCitations) {
  await mobilePage.goto(citation.href)
  await mobilePage.getByText(citation.id, { exact: true }).last().waitFor()
  await assertMobileFits()
}
await mobilePage.goto(`${baseUrl.replace(/\/$/, '')}/investigations/replay-cache-v1/mitigation?source=stored_replay`)
await mobilePage.getByRole('heading', { name: 'Review proposed mitigation' }).waitFor()
await assertMobileFits()
await mobilePage.getByRole('button', { name: 'Approve simulated mitigation' }).click()
await mobilePage.getByLabel(/I understand this is a simulation/).check()
await mobilePage.getByRole('button', { name: /Confirm simulation/ }).click()
const mobileApproval = mobilePage.locator('.approval-success').filter({ hasText: 'simulation_only=true' }).last()
await mobileApproval.getByText(/external_action_performed=false/).waitFor()
assert.notEqual(await mobileApproval.locator('p').innerText(), await approvalResult.locator('p').innerText(), 'a second visitor sharing the IP should receive a separate approval record')
assert.deepEqual(mobilePageErrors, [])

  assert.deepEqual(pageErrors, [], 'the visitor journey should not emit browser exceptions')
console.log('Browser smoke passed: desktop and mobile replay, all citations, refresh-persisted approval, separate same-IP visitor approval, and keyboard focus.')
  await mobilePage.close()
await mobileContext.close()
} finally {
  await browser.close()
}
