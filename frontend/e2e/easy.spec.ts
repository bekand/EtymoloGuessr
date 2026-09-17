import { expect, test } from '@playwright/test'

test('easy mode plays a round without leaking gold on GET', async ({ page }) => {
  const random = page.waitForResponse(
    (res) =>
      res.url().includes('/puzzles/random') &&
      res.request().method() === 'GET' &&
      res.ok(),
  )

  await page.goto('/')
  await page.getByRole('button', { name: 'Play Easy mode' }).click()

  const response = await random
  const body = (await response.json()) as { correctChoice?: unknown; id: string }
  expect(body.correctChoice).toBeUndefined()

  await expect(page.getByLabel('Word pair')).toBeVisible()
  await expect(page.getByLabel('Meaning choices').getByRole('button')).toHaveCount(4)

  await page.getByLabel('Meaning choices').getByRole('button').first().click()
  await page.getByRole('button', { name: 'Submit answer' }).click()

  await expect(page.getByText(/Correct!|Unfortunately, that's not correct/)).toBeVisible()
  await expect(page.locator('.react-flow')).toBeVisible()

  await page.getByRole('button', { name: 'Load the next puzzle' }).click()
  await expect(page.getByLabel('Word pair')).toBeVisible()
  await expect(page.getByText(/Correct!|Unfortunately, that's not correct/)).toHaveCount(0)
})
