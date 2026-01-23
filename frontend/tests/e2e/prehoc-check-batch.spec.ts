/**
 * @fileoverview E2E: Prehoc check-batch flow.
 * Ensures UI can trigger /api/codes/check-batch and renders the modal.
 */

import { test, expect } from '@playwright/test';

async function registerUser(request: any) {
  const email = `e2e_${Date.now()}_${Math.random().toString(16).slice(2)}@example.com`;
  const password = 'Passw0rd!12345';

  const response = await request.post('/api/auth/register', {
    data: {
      email,
      password,
      full_name: 'E2E Tester',
      organization_id: 'default_org',
    },
  });

  if (!response.ok()) {
    const body = await response.text().catch(() => '');
    throw new Error(`E2E auth failed: ${response.status()} ${body}`);
  }

  const data = await response.json();

  // Some environments may create the user but fail token generation.
  // In that case, do an explicit login to retrieve tokens.
  let accessToken = data.access_token as string | undefined;
  let refreshToken = (data.refresh_token as string | null | undefined) ?? null;
  let userPayload = data.user;

  if (!accessToken) {
    const loginResp = await request.post('/api/auth/login', {
      data: { email, password },
    });
    if (!loginResp.ok()) {
      const body = await loginResp.text().catch(() => '');
      throw new Error(`E2E login failed after register: ${loginResp.status()} ${body}`);
    }
    const loginData = await loginResp.json();
    accessToken = loginData.access_token;
    refreshToken = loginData.refresh_token ?? null;
    userPayload = loginData.user;
  }

  const user = {
    id: userPayload?.id,
    email: userPayload?.email,
    name: userPayload?.full_name ?? null,
    org_id: userPayload?.organization_id,
    role: userPayload?.role ?? 'viewer',
  };

  return {
    accessToken: accessToken as string,
    refreshToken: refreshToken as string | null,
    user,
  };
}

test.describe('Prehoc check-batch', () => {
  test('can run Prehoc and opens modal', async ({ page, request }) => {
    const auth = await registerUser(request);
    const bearerHeaders = { Authorization: `Bearer ${auth.accessToken}` };

    // Create a project owned by this test user so candidate listing is authorized.
    const projectResp = await request.post('/api/projects', {
      headers: bearerHeaders,
      data: {
        name: `e2e_prehoc_${Date.now()}`,
        description: 'E2E project for Prehoc check-batch',
      },
    });
    expect(projectResp.ok(), await projectResp.text().catch(() => '')).toBeTruthy();
    const projectData = await projectResp.json();
    const projectId = projectData?.project?.id || projectData?.id || projectData?.project_id;
    expect(projectId, `Unexpected project create response: ${JSON.stringify(projectData)}`).toBeTruthy();

    // Seed candidates into that project.
    for (const codigo of ['Organización social', 'organizacion_social', 'organización de base']) {
      const r = await request.post('/api/codes/candidates', {
        headers: bearerHeaders,
        data: {
          project: projectId,
          codigo,
          fuente_origen: 'manual',
          memo: 'seed e2e prehoc-check-batch',
        },
      });
      expect(r.ok(), await r.text().catch(() => '')).toBeTruthy();
    }

    // Set localStorage before loading the UI.
    await page.addInitScript(
      ({ accessToken, refreshToken, userJson, project }) => {
        window.localStorage.setItem('access_token', accessToken);
        if (refreshToken) {
          window.localStorage.setItem('refresh_token', refreshToken);
        }
        window.localStorage.setItem('qualy-auth-user', userJson);
        window.localStorage.setItem('qualy-dashboard-view', 'investigacion');
        window.localStorage.setItem('qualy-dashboard-investigation-view', 'abierta');
        window.localStorage.setItem('qualy-dashboard-project', project);
      },
      {
        accessToken: auth.accessToken,
        refreshToken: auth.refreshToken,
        userJson: JSON.stringify(auth.user),
        project: projectId,
      }
    );

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Scroll to the CodeValidationPanel.
    await page.evaluate(() => window.scrollTo(0, 1500));
    await expect(page.locator('.validation-panel')).toBeVisible({ timeout: 10000 });

    // Select first candidate row checkbox.
    const firstRowCheckbox = page.locator('.validation-panel__table tbody tr input[type="checkbox"]').first();
    await expect(firstRowCheckbox).toBeVisible({ timeout: 10000 });
    await firstRowCheckbox.check();

    const button = page.locator('button:has-text("Detectar Duplicados Prehoc")');
    await expect(button).toBeEnabled({ timeout: 10000 });

    const waitApi = page.waitForResponse((resp) => {
      try {
        const url = new URL(resp.url());
        return url.pathname.endsWith('/api/codes/check-batch') && resp.status() === 200;
      } catch {
        return resp.url().includes('/api/codes/check-batch') && resp.status() === 200;
      }
    });

    await button.click();

    await waitApi;

    // Modal should open and show summary.
    await expect(page.locator('text=Duplicados Prehoc (Batch Check)')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Resumen:')).toBeVisible({ timeout: 10000 });
  });
});
