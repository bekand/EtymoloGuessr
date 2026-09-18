import { expect, test } from '@playwright/test'

test('medium mode pairs leaves and shows ancestors without graphs', async ({ page }) => {
  const random = page.waitForResponse(
    (res) =>
      res.url().includes('/puzzles/random') &&
      res.url().includes('mode=medium') &&
      res.request().method() === 'GET' &&
      res.ok(),
  )

  await page.goto('/')
  await expect(page.getByText('EtymoloGuessr')).toBeVisible()
  await page.getByRole('button', { name: 'Play Medium mode' }).click()

  const response = await random
  const body = (await response.json()) as {
    correctChoice?: unknown
    leafA?: unknown
    leafB?: unknown
    leaves?: { id: string; lang: string; term: string }[]
    id: string
  }
  expect(body.correctChoice).toBeUndefined()
  expect(body.leafA).toBeUndefined()
  expect(body.leafB).toBeUndefined()
  expect(body.leaves).toHaveLength(8)

  await expect(page.getByLabel('Word tiles')).toBeVisible()
  await expect(page.locator('.modeLabel')).toHaveText('Medium')
  await expect(page.getByText('|Streak: 0')).toBeVisible()
  await expect(page.getByLabel('Word tiles').getByRole('button')).toHaveCount(8)

  const notes = page.getByLabel('Word tiles').getByRole('button')
  // Pair notes 0-1, 2-3, 4-5, 6-7 — may be wrong, but must submit four pairs.
  for (let i = 0; i < 8; i += 2) {
    await notes.nth(i).click()
    await notes.nth(i + 1).click()
  }

  const nextRandom = page.waitForResponse(
    (res) =>
      res.url().includes('/puzzles/random') &&
      res.url().includes('mode=medium') &&
      res.request().method() === 'GET' &&
      res.ok(),
  )
  await page.getByRole('button', { name: 'Submit pairs' }).click()

  await expect(page.getByText(/Correct!|Unfortunately, that's not correct/)).toBeVisible()
  await expect(page.getByLabel('Shared ancestors')).toBeVisible()
  await expect(page.locator('.react-flow')).toHaveCount(0)
  await nextRandom
})
