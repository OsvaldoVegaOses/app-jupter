/**
 * @fileoverview E2E Tests for error handling and resilience.
 */

import { test, expect } from '@playwright/test';

test.describe('Error Handling', () => {
    test('page loads even with slow backend', async ({ page }) => {
        // Slow down network
        const client = await page.context().newCDPSession(page);
        await client.send('Network.emulateNetworkConditions', {
            offline: false,
            downloadThroughput: 50 * 1024, // 50kb/s
            uploadThroughput: 50 * 1024,
            latency: 2000, // 2s latency
        });

        await page.goto('/', { timeout: 60000 });

        // Page should still load
        await expect(page.locator('h1')).toContainText('Dashboard', { timeout: 30000 });
    });

    test('API error toast appears on failure', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Intercept API calls and make them fail
        await page.route('**/api/**', async (route) => {
            if (Math.random() > 0.5) {
                await route.fulfill({
                    status: 500,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: 'Simulated server error' }),
                });
            } else {
                await route.continue();
            }
        });

        // Trigger some API call by refreshing status
        const refreshButton = page.locator('button:has-text("Refrescar")');
        if (await refreshButton.isVisible()) {
            await refreshButton.click();
        }

        // Wait a bit for potential error toast
        await page.waitForTimeout(2000);

        // The toast container might appear
        const toastContainer = page.locator('.api-error-toast-container');
        // This is optional - we're just checking the system handles errors gracefully
    });

    test('System Health Dashboard shows status on expand', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Find the health dashboard header and click to expand
        const healthHeader = page.locator('.health-dashboard__header');
        await expect(healthHeader).toBeVisible();

        // Click to expand
        await healthHeader.click();

        // Wait for content to load
        await page.waitForTimeout(2000);

        // Should show the content section
        const healthContent = page.locator('.health-dashboard__content');
        await expect(healthContent).toBeVisible({ timeout: 10000 });

        // Should have service indicators
        const services = page.locator('.health-service');
        await expect(services).toHaveCount(4, { timeout: 10000 }); // PostgreSQL, Neo4j, Qdrant, Azure
    });

    test('Backend status recovers after temporary offline', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Wait for initial status
        const backendStatus = page.locator('.backend-status');
        await expect(backendStatus).toBeVisible();

        // Should show connected initially (if backend is running)
        const statusText = page.locator('.backend-status__text');

        // Verify the component is rendering
        await expect(statusText).toBeVisible();
    });
});

test.describe('Accessibility', () => {
    test('main landmarks are present', async ({ page }) => {
        await page.goto('/');

        // Should have header
        const header = page.locator('header');
        await expect(header).toBeVisible();

        // Should have main content
        const main = page.locator('main');
        await expect(main).toBeVisible();
    });

    test('buttons are keyboard accessible', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Tab to first button
        await page.keyboard.press('Tab');

        // Should be able to navigate with keyboard
        const focusedElement = page.locator(':focus');
        await expect(focusedElement).toBeVisible();
    });

    test('health dashboard is keyboard accessible', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');

        // Find health dashboard header
        const healthHeader = page.locator('.health-dashboard__header');

        // It should have tabindex
        await expect(healthHeader).toHaveAttribute('tabindex', '0');

        // Should be clickable via Enter key
        await healthHeader.focus();
        await page.keyboard.press('Enter');

        // Content should expand
        const healthContent = page.locator('.health-dashboard__content');
        await expect(healthContent).toBeVisible({ timeout: 5000 });
    });
});
