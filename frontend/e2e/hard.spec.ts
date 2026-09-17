import { expect, test } from '@playwright/test'

test('hard mode places cards and reveals gold after submit', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Play Hard mode' }).click()

  await expect(page.getByLabel('Word cards')).toBeVisible()
  await expect(page.locator('.modeLabel')).toHaveText('Hard')
  await expect(page.getByText('[ Streak 0 ]')).toBeVisible()
  await expect(page.getByRole('button', { name: /^Place / }).first()).toBeVisible()

  while ((await page.getByRole('button', { name: /^Place / }).count()) > 0) {
    await page.getByRole('button', { name: /^Place / }).first().click()
  }

  await expect(page.getByRole('button', { name: 'Submit graph' })).toBeEnabled()
  await page.getByRole('button', { name: 'Submit graph' }).click()

  await expect(page.getByText(/Correct!|Unfortunately, that's not correct/)).toBeVisible()
  await expect(page.locator('.react-flow')).toBeVisible()
})
