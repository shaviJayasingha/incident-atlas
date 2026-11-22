import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const baseUrl = process.env.INCIDENT_ATLAS_WEB_URL ?? 'http://127.0.0.1:5173'
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const pageErrors = []
  page.on('pageerror', error => pageErrors.push(error.message))

  await page.goto(baseUrl)
  await page.getByRole('heading', { name: /Follow the evidence/ }).waitFor()
  await page.getByRole('link', { name: /Explore incidents/ }).click()
  await page.getByRole('heading', { name: 'Choose an incident' }).waitFor()
  await page.getByRole('link', { name: /Catalog latency after cache key change/ }).click()
  await page.getByRole('heading', { name: 'Incident timeline' }).waitFor()
  await page.getByRole('heading', { name: 'Telemetry explorer' }).waitFor()
  await page.getByRole('button', { name: 'View stored replay' }).click()
  await page.getByText('PROVENANCE · STORED REPLAY').waitFor()
  assert.equal(await page.locator('.report-banner-stamp strong').innerText(), 'NO')
  await page.getByRole('link', { name: /ev-deploy-catalog-042/ }).click()
  await page.waitForURL(/evidence=ev-deploy-catalog-042/)
  await page.getByText('ev-deploy-catalog-042', { exact: true }).first().waitFor()
  await page.goBack()
  await page.getByRole('button', { name: /Review simulated mitigation/ }).click()
  await page.getByRole('heading', { name: 'Review proposed mitigation' }).waitFor()
  await page.getByRole('button', { name: 'Approve simulated mitigation' }).click()
  await page.getByLabel(/I understand this is a simulation/).check()
  await page.getByRole('button', { name: /Confirm simulation/ }).click()
  await page.getByText('SIMULATION RECORDED').waitFor()
  await page.getByText(/simulation_only=true/).waitFor()
  await page.getByText(/external_action_performed=false/).waitFor()

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await mobilePage.goto(baseUrl)
  await mobilePage.getByRole('heading', { name: /Follow the evidence/ }).waitFor()
  const mobileOverflow = await mobilePage.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  assert.equal(mobileOverflow, 0, 'mobile home should not overflow horizontally')
  await mobilePage.getByRole('link', { name: /Explore incidents/ }).focus()
  assert.equal(await mobilePage.evaluate(() => document.activeElement?.textContent?.includes('Explore incidents')), true)

  assert.deepEqual(pageErrors, [], 'the visitor journey should not emit browser exceptions')
  console.log('Browser smoke passed: desktop replay, evidence, persisted approval, mobile layout and keyboard focus.')
  await mobilePage.close()
} finally {
  await browser.close()
}
